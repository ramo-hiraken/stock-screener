"""新高値ブレイク投資スクリーニング — 高速版

初回: yf.download()バッチ取得 → SQLiteキャッシュ保存（〜30-40秒）
2回目以降: キャッシュから即時読み込み → フィルタ（〜3秒）
"""

import pandas as pd
import numpy as np
import yfinance as yf
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from data_source import get_data_source, DataSourceBase
from db import get_fresh_codes, load_ohlcv_batch, save_ohlcv_batch
from settings import Screening, MarketFilter
from config import SCREEN_CODES

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


# ---------------------------------------------------------------------------
# バッチダウンロード（チャンク200、最大10並列）
# ---------------------------------------------------------------------------

def _download_chunk(chunk: list[str]) -> dict[str, pd.DataFrame]:
    result = {}
    try:
        tickers_str = " ".join(f"{c}.T" for c in chunk)
        raw = yf.download(
            tickers_str, period="1y", group_by="ticker",
            progress=False, threads=True, timeout=30,
        )
    except Exception:
        return result

    if raw.empty:
        return result

    for code in chunk:
        ticker = f"{code}.T"
        try:
            if len(chunk) == 1:
                df = raw.copy()
            else:
                df = raw[ticker].copy()
            df = df.dropna(subset=["Close"])
            if len(df) >= 20:
                result[code] = df
        except (KeyError, TypeError):
            continue

    return result


def _batch_download_and_cache(
    codes: list[str],
    progress_callback=None,
) -> dict[str, pd.DataFrame]:
    """キャッシュ活用バッチ取得。staleな銘柄のみダウンロード。"""

    # キャッシュ仕分け
    fresh_codes, stale_codes = get_fresh_codes(codes)

    all_data = {}

    # キャッシュから読み込み
    if fresh_codes:
        if progress_callback:
            progress_callback(0.05, f"キャッシュから{len(fresh_codes)}銘柄読み込み中...")
        cached = load_ohlcv_batch(fresh_codes, days=400)
        all_data.update(cached)

    if not stale_codes:
        if progress_callback:
            progress_callback(0.70, f"全{len(all_data)}銘柄キャッシュヒット")
        return all_data

    # staleな銘柄をダウンロード
    chunk_size = 200
    chunks = [stale_codes[i:i + chunk_size] for i in range(0, len(stale_codes), chunk_size)]

    if progress_callback:
        progress_callback(0.10, f"{len(stale_codes)}銘柄をダウンロード中... ({len(chunks)}チャンク)")

    done = 0
    lock = threading.Lock()

    def on_chunk_done(_):
        nonlocal done
        with lock:
            done += 1
            if progress_callback:
                p = 0.10 + (done / len(chunks)) * 0.55
                progress_callback(p, f"ダウンロード中... ({done}/{len(chunks)}チャンク完了)")

    downloaded = {}
    with ThreadPoolExecutor(max_workers=min(len(chunks), 10)) as executor:
        futures = [executor.submit(_download_chunk, chunk) for chunk in chunks]
        for f in futures:
            f.add_done_callback(on_chunk_done)
        for future in as_completed(futures):
            downloaded.update(future.result())

    # キャッシュに保存
    if downloaded:
        if progress_callback:
            progress_callback(0.68, f"{len(downloaded)}銘柄をキャッシュに保存中...")
        save_ohlcv_batch(downloaded)

    all_data.update(downloaded)

    if progress_callback:
        progress_callback(0.70, f"合計{len(all_data)}銘柄のデータ準備完了")

    return all_data


# ---------------------------------------------------------------------------
# 個別フィルタ関数
# ---------------------------------------------------------------------------

def detect_new_high(hist: pd.DataFrame) -> dict:
    n = Screening.high_lookback_days
    if hist.empty or len(hist) < 20:
        return {"is_new_high": False}

    close = hist["Close"]
    high = hist["High"]
    current_price = float(close.iloc[-1])

    lookback = high.iloc[-n:] if len(high) >= n else high
    period_high = float(lookback.max())
    period_high_date = lookback.idxmax()

    recent_high = float(high.iloc[-5:].max())
    is_new_high = recent_high >= period_high * 0.995

    return {
        "is_new_high": is_new_high,
        "current_price": round(current_price, 1),
        "period_high": round(period_high, 1),
        "period_high_date": str(period_high_date)[:10],
    }


def check_continuation(hist: pd.DataFrame, high_info: dict) -> dict:
    if not high_info.get("is_new_high") or hist.empty:
        return {"continuation": False}

    x_days = Screening.continuation_days
    y_pct = Screening.continuation_max_drop_pct

    recent = hist.iloc[-x_days:]
    recent_high = float(recent["High"].max())
    current = float(hist["Close"].iloc[-1])
    drop_from_high = (1 - current / recent_high) * 100

    return {
        "continuation": drop_from_high <= y_pct,
        "recent_high": round(recent_high, 1),
        "drop_from_high_pct": round(drop_from_high, 2),
    }


def check_false_breakout(hist: pd.DataFrame, high_info: dict) -> dict:
    if not high_info.get("is_new_high") or hist.empty:
        return {"false_breakout": False}

    z_days = Screening.false_breakout_check_days
    threshold = Screening.false_breakout_drop_pct

    recent = hist.iloc[-z_days:]
    peak = float(recent["High"].max())
    trough = float(recent["Low"].min())
    max_drawdown = (1 - trough / peak) * 100 if peak > 0 else 0

    return {
        "false_breakout": max_drawdown > threshold,
        "max_drawdown_pct": round(max_drawdown, 2),
    }


def check_volume_spike(hist: pd.DataFrame) -> dict:
    avg_days = Screening.volume_avg_days
    ratio_threshold = Screening.volume_spike_ratio

    if hist.empty or len(hist) < avg_days + 1:
        return {"volume_spike": False, "volume_ratio": 0}

    vol = hist["Volume"]
    latest_vol = float(vol.iloc[-1])
    avg_vol = float(vol.iloc[-(avg_days + 1):-1].mean())
    ratio = latest_vol / avg_vol if avg_vol > 0 else 0

    return {
        "volume_spike": ratio >= ratio_threshold,
        "volume_ratio": round(ratio, 2),
    }


def check_market_environment(source: DataSourceBase | None = None) -> dict:
    if source is None:
        source = get_data_source()

    threshold = MarketFilter.nikkei_drop_threshold_pct
    ticker = MarketFilter.nikkei_ticker

    nikkei = source.fetch_index_history(ticker, period_days=10)
    if nikkei.empty or len(nikkei) < 2:
        return {"market_caution": False, "nikkei_change_pct": None}

    prev_close = float(nikkei["Close"].iloc[-2])
    last_close = float(nikkei["Close"].iloc[-1])
    change_pct = ((last_close / prev_close) - 1) * 100

    return {
        "market_caution": change_pct <= threshold,
        "nikkei_change_pct": round(change_pct, 2),
    }


def analyze_momentum(hist: pd.DataFrame) -> dict:
    if hist.empty or len(hist) < 50:
        return {"momentum_score": 0, "trend": "不明"}

    close = hist["Close"]
    ma5 = float(close.rolling(5).mean().iloc[-1])
    ma25 = float(close.rolling(25).mean().iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1])
    current = float(close.iloc[-1])

    score = 0
    if current > ma5:
        score += 1
    if current > ma25:
        score += 1
    if current > ma50:
        score += 1
    if ma5 > ma25:
        score += 1
    if ma25 > ma50:
        score += 1

    vol_recent = float(hist["Volume"].iloc[-5:].mean())
    vol_avg = float(hist["Volume"].iloc[-25:].mean())
    vol_ratio = vol_recent / vol_avg if vol_avg > 0 else 1
    if vol_ratio > 1.5:
        score += 1

    trend = "上昇" if score >= 4 else "横ばい" if score >= 2 else "下降"

    return {
        "momentum_score": score,
        "ma5": round(ma5, 1),
        "ma25": round(ma25, 1),
        "ma50": round(ma50, 1),
        "volume_ratio": round(vol_ratio, 2),
        "trend": trend,
    }


def check_roe(info: dict) -> dict:
    roe = info.get("returnOnEquity")
    if roe is not None:
        roe_pct = roe * 100
        return {"roe": round(roe_pct, 2), "passes_roe": roe_pct >= Screening.roe_min_pct}
    return {"roe": None, "passes_roe": False}


# ---------------------------------------------------------------------------
# フル分析
# ---------------------------------------------------------------------------

def _full_analysis(ohlcv_map: dict[str, pd.DataFrame], market: dict, name_map: dict) -> pd.DataFrame:
    results = []
    now = pd.Timestamp.now()

    for code, hist in ohlcv_map.items():
        if len(hist) < 20:
            continue

        # 上場廃止チェック: 直近2営業日以内に取引がなければ除外
        last_trade = hist.index[-1]
        cal_days = (now - last_trade).days
        if cal_days > 5:
            continue
        biz_days = len(pd.bdate_range(last_trade, now)) - 1
        if biz_days >= 2:
            continue

        # TOB/上場廃止予定: 直近10日の値幅が0.5%未満なら除外
        recent = hist.iloc[-10:]
        if len(recent) >= 3:
            rng_pct = (float(recent["High"].max()) - float(recent["Low"].min())) / float(recent["Low"].min()) * 100
            if rng_pct < 0.5:
                continue

        high_info = detect_new_high(hist)
        cont = check_continuation(hist, high_info)
        false_bk = check_false_breakout(hist, high_info)
        vol = check_volume_spike(hist)
        momentum = analyze_momentum(hist)

        is_candidate = (
            high_info["is_new_high"]
            and cont.get("continuation", False)
            and not false_bk.get("false_breakout", False)
        )

        priority = 0
        if is_candidate:
            priority += 3
        if vol.get("volume_spike"):
            priority += 2
        if momentum["momentum_score"] >= 4:
            priority += 1

        results.append({
            "コード": code,
            "銘柄名": name_map.get(code, code),
            "現在値": high_info.get("current_price", 0),
            "直近高値": high_info.get("period_high", 0),
            "高値日付": high_info.get("period_high_date", ""),
            "高値乖離率(%)": cont.get("drop_from_high_pct", None),
            "新高値": high_info["is_new_high"],
            "初動継続": cont.get("continuation", False),
            "だまし疑い": false_bk.get("false_breakout", False),
            "最大DD(%)": false_bk.get("max_drawdown_pct", 0),
            "出来高倍率": vol.get("volume_ratio", 0),
            "出来高急増": vol.get("volume_spike", False),
            "ROE(%)": None,
            "モメンタム": momentum["momentum_score"],
            "トレンド": momentum["trend"],
            "時価総額(億)": None,
            "セクター": "",
            "候補": is_candidate,
            "優先度": priority,
            "材料": "",
            "相場環境": "⚠️注意" if market.get("market_caution") else "通常",
            "日経変動(%)": market.get("nikkei_change_pct"),
            "損切ライン": round(high_info.get("current_price", 0) * (1 - Screening.stop_loss_pct / 100), 1),
        })

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# 候補銘柄のみ詳細情報取得
# ---------------------------------------------------------------------------

def _enrich_candidates(df: pd.DataFrame, progress_callback=None) -> pd.DataFrame:
    if df.empty:
        return df

    target = df[df["新高値"]].copy()
    if target.empty:
        return df

    codes = target["コード"].tolist()

    if progress_callback:
        progress_callback(0.85, f"候補{len(codes)}銘柄の詳細取得中...")

    def fetch_info(code):
        try:
            ticker = yf.Ticker(f"{code}.T")
            info = ticker.info
            roe_info = check_roe(info)
            market_cap = info.get("marketCap", 0)
            cap_oku = round(market_cap / 1e8, 1) if market_cap else None
            return code, roe_info.get("roe"), roe_info.get("passes_roe", False), cap_oku, info.get("sector", "")
        except Exception:
            return code, None, False, None, ""

    info_map = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_info, c) for c in codes]
        for future in as_completed(futures):
            code, roe, passes_roe, cap, sector = future.result()
            info_map[code] = (roe, passes_roe, cap, sector)

    for idx, row in df.iterrows():
        code = row["コード"]
        if code in info_map:
            roe, passes_roe, cap, sector = info_map[code]
            df.at[idx, "ROE(%)"] = roe
            df.at[idx, "時価総額(億)"] = cap
            df.at[idx, "セクター"] = sector
            if passes_roe:
                df.at[idx, "優先度"] = row["優先度"] + 1

    return df


# ---------------------------------------------------------------------------
# 統合スクリーニング
# ---------------------------------------------------------------------------

def screen_breakout(
    codes: list[str] | None = None,
    progress_callback=None,
    max_workers: int = 10,
) -> pd.DataFrame:
    if codes is None:
        codes = SCREEN_CODES

    source = get_data_source()
    market = check_market_environment(source)
    name_map = _get_name_map()

    # Phase 1: OHLCV取得（キャッシュ活用）
    ohlcv_map = _batch_download_and_cache(codes, progress_callback)

    if progress_callback:
        progress_callback(0.75, f"{len(ohlcv_map)}銘柄のフィルタ中...")

    # Phase 2: フル分析
    df = _full_analysis(ohlcv_map, market, name_map)

    # Phase 3: 候補のみ詳細取得
    df = _enrich_candidates(df, progress_callback)

    if not df.empty:
        df = df.sort_values(["候補", "優先度", "モメンタム"], ascending=[False, False, False])

    if progress_callback:
        progress_callback(1.0, "完了")

    return df


def get_candidates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df[df["候補"]].copy()


# 旧APIとの互換性
def fetch_stock_data(code: str, period: str = "1y") -> dict | None:
    source = get_data_source()
    days = 730 if period == "2y" else 365
    hist = source.fetch_ohlcv(code, period_days=days)
    if hist.empty:
        return None
    info = source.fetch_info(code)
    name_map = _get_name_map()
    name = name_map.get(code, info.get("shortName", info.get("longName", code)))
    return {"code": code, "name": name, "history": hist, "info": info}


def check_new_high(hist: pd.DataFrame, lookback_days: int = 5) -> dict:
    return detect_new_high(hist)


def screen_stocks(codes=None, progress_callback=None):
    return screen_breakout(codes=codes, progress_callback=progress_callback)
