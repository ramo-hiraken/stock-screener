import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"

ROE_THRESHOLD = 10.0
STOP_LOSS_PERCENT = 8.0


def _load_screen_codes() -> list[str]:
    """config.yamlのtarget_marketに基づいてスクリーニング対象コードを返す。"""
    from settings import load_config
    cfg = load_config()
    market = cfg.get("target_market", "グロース")

    try:
        from jpx_list import get_codes_by_market
        if "+" in market:
            codes = []
            for m in market.split("+"):
                codes.extend(get_codes_by_market(m.strip()))
            return sorted(set(codes))
        return get_codes_by_market(market)
    except Exception:
        return _FALLBACK_CODES


_FALLBACK_CODES = [
    "3150", "3182", "3491", "3662", "3697", "3923", "3966", "3993",
    "4175", "4180", "4194", "4344", "4381", "4478", "4485", "4488",
    "4883", "4892", "5765", "5765", "6027", "6030", "6033", "6095",
    "6532", "6544", "6552", "6560", "7068", "7342", "7352", "7370",
    "9211", "9229", "9246", "9247", "9340", "9341", "9345", "9348",
]

SCREEN_CODES = _load_screen_codes()


def load_json(path: Path, default=None):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default if default is not None else []


def save_json(path: Path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
