"""決算スクリーニング — ROE・売上成長・利益率成長フィルタ"""

import pandas as pd
import yfinance as yf
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from jpx_list import build_name_map as _build_name_map
    _NAME_MAP: dict[str, str] | None = None

    def _get_name_map() -> dict[str, str]:
        global _NAME_MAP
        if _NAME_MAP is None:
            _NAME_MAP = _build_name_map()
        return _NAME_MAP
except ImportError:
    def _get_name_map() -> dict[str, str]:
        return {}


def _download_chunk(chunk: list[str]) -> dict[str, pd.DataFrame]:
    result = {}
    try:
        tickers_str = " ".join(f"{c}.T" for c in chunk)
        raw = yf.download(
            tickers_str, period="5d", group_by="ticker",
            progress=False, threads=True, timeout=30,
        )
    except Exception:
        return result
    if raw.empty:
        return result
    for code in chunk:
        ticker = f"{code}.T"
        try:
            df = raw.copy() if len(chunk) == 1 else raw[ticker].copy()
            df = df.dropna(subset=["Close"])
            if not df.empty:
                result[code] = df
        except (KeyError, TypeError):
            continue
    return result


def _price_prefilter(
    codes: list[str],
    max_unit_price: int = 1_000_000,
    progress_callback=None,
) -> dict[str, float]:
    """yf.downloadバッチで直近株価を取得し、1単元が上限以下の銘柄を抽出。"""
    chunk_size = 200
    chunks = [codes[i:i + chunk_size] for i in range(0, len(codes), chunk_size)]

    if progress_callback:
        progress_callback(0.05, f"{len(codes)}銘柄の価格取得中... ({len(chunks)}チャンク)")

    done = 0
    lock = threading.Lock()

    def on_done(_):
        nonlocal done
        with lock:
            done += 1
            if progress_callback:
                p = 0.05 + (done / len(chunks)) * 0.35
                progress_callback(p, f"価格取得中... ({done}/{len(chunks)}チャンク)")

    ohlcv = {}
    with ThreadPoolExecutor(max_workers=min(len(chunks), 10)) as executor:
        futures = [executor.submit(_download_chunk, chunk) for chunk in chunks]
        for f in futures:
            f.add_done_callback(on_done)
        for future in as_completed(futures):
            ohlcv.update(future.result())

    result = {}
    max_price = max_unit_price / 100
    dead_count = 0
    for code, df in ohlcv.items():
        if df.empty:
            continue
        price = float(df["Close"].iloc[-1])
        if price <= max_price:
            # TOB/上場廃止予定銘柄の除外: 直近の値幅が極端に小さい銘柄はスキップ
            if len(df) >= 3:
                period_high = float(df["High"].max())
                period_low = float(df["Low"].min())
                price_range_pct = (period_high - period_low) / period_low * 100 if period_low > 0 else 0
                if price_range_pct < 0.5:
                    dead_count += 1
                    continue
            result[code] = price

    if progress_callback:
        msg = f"価格フィルタ: {len(result)}/{len(codes)}銘柄が対象"
        if dead_count:
            msg += f" (値動きなし{dead_count}銘柄除外)"
        progress_callback(0.45, msg)

    return result


def _fetch_fundamentals(code: str) -> dict | None:
    """1銘柄の決算データを取得。"""
    try:
        t = yf.Ticker(f"{code}.T")
        info = t.info

        roe_raw = info.get("returnOnEquity")
        roe = round(roe_raw * 100, 2) if roe_raw is not None else None

        rev_growth_raw = info.get("revenueGrowth")
        rev_growth = round(rev_growth_raw * 100, 2) if rev_growth_raw is not None else None

        earnings_growth_raw = info.get("earningsGrowth")
        earnings_growth = round(earnings_growth_raw * 100, 2) if earnings_growth_raw is not None else None

        profit_margins = info.get("profitMargins")
        pm_pct = round(profit_margins * 100, 2) if profit_margins is not None else None

        operating_margins = info.get("operatingMargins")
        om_pct = round(operating_margins * 100, 2) if operating_margins is not None else None

        market_cap = info.get("marketCap", 0)
        cap_oku = round(market_cap / 1e8, 1) if market_cap else None

        trailing_pe = info.get("trailingPE")
        forward_pe = info.get("forwardPE")

        sector = info.get("sector", "")
        industry = info.get("industry", "")

        return {
            "code": code,
            "roe": roe,
            "rev_growth": rev_growth,
            "earnings_growth": earnings_growth,
            "profit_margin": pm_pct,
            "operating_margin": om_pct,
            "market_cap_oku": cap_oku,
            "trailing_pe": round(trailing_pe, 1) if trailing_pe else None,
            "forward_pe": round(forward_pe, 1) if forward_pe else None,
            "sector": sector,
            "industry": industry,
        }
    except Exception:
        return None


def screen_fundamentals(
    codes: list[str],
    roe_min: float = 10.0,
    rev_growth_min: float = 10.0,
    earnings_growth_min: float = 20.0,
    max_unit_price: int = 1_000_000,
    progress_callback=None,
) -> pd.DataFrame:
    """決算スクリーニング: 価格→財務データの2段階フィルタ。"""
    name_map = _get_name_map()

    # Phase 1: 価格プレフィルタ
    price_map = _price_prefilter(codes, max_unit_price, progress_callback)

    if not price_map:
        if progress_callback:
            progress_callback(1.0, "対象銘柄なし")
        return pd.DataFrame()

    target_codes = list(price_map.keys())

    # Phase 2: 財務データ取得（並列）
    if progress_callback:
        progress_callback(0.50, f"{len(target_codes)}銘柄の決算データ取得中...")

    done = 0
    lock = threading.Lock()
    total = len(target_codes)

    fundamentals = {}

    def on_done(_):
        nonlocal done
        with lock:
            done += 1
            if progress_callback and done % 50 == 0:
                p = 0.50 + (done / total) * 0.40
                progress_callback(p, f"決算データ取得中... ({done}/{total})")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_fundamentals, c): c for c in target_codes}
        for f in futures:
            f.add_done_callback(on_done)
        for future in as_completed(futures):
            result = future.result()
            if result:
                fundamentals[result["code"]] = result

    if progress_callback:
        progress_callback(0.92, f"{len(fundamentals)}銘柄の決算データ取得完了。フィルタ中...")

    # Phase 3: 結果構築
    rows = []
    for code, fund in fundamentals.items():
        price = price_map.get(code, 0)
        unit_cost = int(price * 100)

        passes_roe = fund["roe"] is not None and fund["roe"] >= roe_min
        passes_rev = fund["rev_growth"] is not None and fund["rev_growth"] >= rev_growth_min
        passes_earn = fund["earnings_growth"] is not None and fund["earnings_growth"] >= earnings_growth_min

        is_candidate = passes_roe and passes_rev and passes_earn
        is_ideal_price = unit_cost <= 500_000

        priority = 0
        if is_candidate:
            priority += 3
        if is_ideal_price:
            priority += 1
        if fund["roe"] and fund["roe"] >= 15:
            priority += 1
        if fund["rev_growth"] and fund["rev_growth"] >= 20:
            priority += 1

        rows.append({
            "コード": code,
            "銘柄名": name_map.get(code, code),
            "株価": round(price, 1),
            "1単元(円)": unit_cost,
            "ROE(%)": fund["roe"],
            "売上成長率(%)": fund["rev_growth"],
            "利益成長率(%)": fund["earnings_growth"],
            "利益率(%)": fund["profit_margin"],
            "営業利益率(%)": fund["operating_margin"],
            "時価総額(億)": fund["market_cap_oku"],
            "PER(実績)": fund["trailing_pe"],
            "PER(予想)": fund["forward_pe"],
            "セクター": fund["sector"],
            "業種": fund["industry"],
            "ROE✓": passes_roe,
            "売上✓": passes_rev,
            "利益✓": passes_earn,
            "候補": is_candidate,
            "優先度": priority,
            "価格帯": "◎ 50万以内" if is_ideal_price else "○ 100万以内",
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["候補", "優先度", "ROE(%)"], ascending=[False, False, False])

    if progress_callback:
        progress_callback(1.0, "完了")

    return df
