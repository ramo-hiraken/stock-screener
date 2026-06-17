"""新高値ブレイク投資スクリーニング — 判定ロジック"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from data_source import get_data_source, DataSourceBase
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
# 1. 新高値判定
# ---------------------------------------------------------------------------

def detect_new_high(hist: pd.DataFrame) -> dict:
    """過去 N 日の最高値を更新したか判定する。"""
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


# ---------------------------------------------------------------------------
# 2. 初動継続フィルタ
# ---------------------------------------------------------------------------

def check_continuation(hist: pd.DataFrame, high_info: dict) -> dict:
    """高値更新が直近X営業日以内かつ、現値が直近高値からY%以内。"""
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


# ---------------------------------------------------------------------------
# 3. だまし（ブレイク失敗）除外
# ---------------------------------------------------------------------------

def check_false_breakout(hist: pd.DataFrame, high_info: dict) -> dict:
    """ブレイク後Z日以内に高値から8%超下落した場合フラグを立てる。"""
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


# ---------------------------------------------------------------------------
# 4. 出来高フィルタ
# ---------------------------------------------------------------------------

def check_volume_spike(hist: pd.DataFrame) -> dict:
    """直近の出来高が20日平均のW倍以上か。"""
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


# ---------------------------------------------------------------------------
# 5. 相場環境フィルタ
# ---------------------------------------------------------------------------

def check_market_environment(source: DataSourceBase | None = None) -> dict:
    """日経平均の当日変動率をチェックし、大幅下落日はフラグ。"""
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


# ---------------------------------------------------------------------------
# モメンタム分析（既存を維持）
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ROEチェック（既存を維持）
# ---------------------------------------------------------------------------

def check_roe(info: dict) -> dict:
    roe = info.get("returnOnEquity")
    if roe is not None:
        roe_pct = roe * 100
        return {"roe": round(roe_pct, 2), "passes_roe": roe_pct >= Screening.roe_min_pct}
    return {"roe": None, "passes_roe": False}


# ---------------------------------------------------------------------------
# 統合スクリーニング
# ---------------------------------------------------------------------------

def screen_breakout(
    codes: list[str] | None = None,
    progress_callback=None,
) -> pd.DataFrame:
    """全フィルタを適用した新高値ブレイクスクリーニング。"""
    if codes is None:
        codes = SCREEN_CODES

    source = get_data_source()
    market = check_market_environment(source)
    name_map = _get_name_map()
    results = []
    total = len(codes)

    for i, code in enumerate(codes):
        if progress_callback:
            progress_callback(i / total, f"分析中: {code} ({i + 1}/{total})")

        hist = source.fetch_ohlcv(code, period_days=max(Screening.high_lookback_days + 30, 400))
        if hist.empty or len(hist) < 20:
            continue

        info = source.fetch_info(code)

        high_info = detect_new_high(hist)
        cont = check_continuation(hist, high_info)
        false_bk = check_false_breakout(hist, high_info)
        vol = check_volume_spike(hist)
        roe_info = check_roe(info)
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
        if roe_info.get("passes_roe"):
            priority += 1
        if momentum["momentum_score"] >= 4:
            priority += 1

        market_cap = info.get("marketCap", 0)
        cap_oku = round(market_cap / 1e8, 1) if market_cap else None

        results.append({
            "コード": code,
            "銘柄名": name_map.get(code, info.get("shortName", info.get("longName", code))),
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
            "ROE(%)": roe_info.get("roe"),
            "モメンタム": momentum["momentum_score"],
            "トレンド": momentum["trend"],
            "時価総額(億)": cap_oku,
            "セクター": info.get("sector", ""),
            "候補": is_candidate,
            "優先度": priority,
            "材料": "",  # 材料突合層で埋める
            "相場環境": "⚠️注意" if market.get("market_caution") else "通常",
            "日経変動(%)": market.get("nikkei_change_pct"),
            "損切ライン": round(high_info.get("current_price", 0) * (1 - Screening.stop_loss_pct / 100), 1),
        })

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values(["候補", "優先度", "モメンタム"], ascending=[False, False, False])
    return df


def get_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """候補フラグが立っている銘柄のみ抽出。"""
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
