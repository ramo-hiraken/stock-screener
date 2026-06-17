"""JPX上場銘柄一覧の取得・キャッシュ・フィルタリング。

東証の公開データから市場区分別の銘柄コード・銘柄名を取得する。
"""

import io
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

_CACHE_DIR = Path(__file__).parent / "data"
_CACHE_FILE = _CACHE_DIR / "jpx_listed.csv"
_CACHE_TTL_HOURS = 24 * 7

JPX_DATA_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"


def _fetch_jpx_list() -> pd.DataFrame:
    """JPXから上場銘柄一覧をダウンロードしてDataFrameで返す。"""
    import urllib.request

    _CACHE_DIR.mkdir(exist_ok=True)

    req = urllib.request.Request(JPX_DATA_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()

    df = pd.read_excel(io.BytesIO(data))
    df.to_csv(_CACHE_FILE, index=False, encoding="utf-8-sig")
    return df


def _load_cached() -> pd.DataFrame | None:
    """キャッシュが新鮮ならCSVから読み込む。"""
    if not _CACHE_FILE.exists():
        return None
    mtime = datetime.fromtimestamp(_CACHE_FILE.stat().st_mtime)
    if datetime.now() - mtime > timedelta(hours=_CACHE_TTL_HOURS):
        return None
    return pd.read_csv(_CACHE_FILE, dtype={"コード": str})


def get_jpx_list() -> pd.DataFrame:
    """上場銘柄一覧を取得（キャッシュ優先）。"""
    cached = _load_cached()
    if cached is not None:
        return cached
    try:
        return _fetch_jpx_list()
    except Exception as e:
        if _CACHE_FILE.exists():
            return pd.read_csv(_CACHE_FILE, dtype={"コード": str})
        raise RuntimeError(f"JPX銘柄一覧の取得に失敗: {e}")


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """JPXのExcel列名を正規化。"""
    col_map = {}
    for col in df.columns:
        c = str(col).strip()
        if "市場・商品区分" in c:
            col_map[col] = "市場区分"
        elif "33業種区分" == c:
            col_map[col] = "業種"
    df = df.rename(columns=col_map)
    if "コード" in df.columns:
        df["コード"] = df["コード"].astype(str).str.strip()
    return df


def get_growth_codes() -> list[str]:
    """グロース市場の全銘柄コードを返す。"""
    df = _normalize_df(get_jpx_list())
    if "市場区分" not in df.columns:
        return []
    growth = df[df["市場区分"].str.contains("グロース", na=False)]
    codes = growth["コード"].tolist()
    return [c for c in codes if c.isdigit() and len(c) == 4]


def get_standard_codes() -> list[str]:
    """スタンダード市場の全銘柄コードを返す。"""
    df = _normalize_df(get_jpx_list())
    if "市場区分" not in df.columns:
        return []
    std = df[df["市場区分"].str.contains("スタンダード", na=False)]
    codes = std["コード"].tolist()
    return [c for c in codes if c.isdigit() and len(c) == 4]


def get_codes_by_market(market: str = "グロース") -> list[str]:
    """指定した市場区分の銘柄コードを返す。"""
    df = _normalize_df(get_jpx_list())
    if "市場区分" not in df.columns:
        return []
    filtered = df[df["市場区分"].str.contains(market, na=False)]
    codes = filtered["コード"].tolist()
    return [c for c in codes if c.isdigit() and len(c) == 4]


def build_name_map() -> dict[str, str]:
    """コード→銘柄名の辞書を返す（全市場）。"""
    df = _normalize_df(get_jpx_list())
    if "コード" not in df.columns or "銘柄名" not in df.columns:
        return {}
    name_map = {}
    for _, row in df.iterrows():
        code = str(row["コード"]).strip()
        name = str(row["銘柄名"]).strip()
        if code.isdigit() and len(code) == 4 and name:
            name_map[code] = name
    return name_map
