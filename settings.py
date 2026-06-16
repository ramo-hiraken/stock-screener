import yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


_config = load_config()


class Screening:
    high_lookback_days: int = _config["screening"]["high_lookback_days"]
    continuation_days: int = _config["screening"]["continuation_days"]
    continuation_max_drop_pct: float = _config["screening"]["continuation_max_drop_pct"]
    false_breakout_drop_pct: float = _config["screening"]["false_breakout_drop_pct"]
    false_breakout_check_days: int = _config["screening"]["false_breakout_check_days"]
    volume_spike_ratio: float = _config["screening"]["volume_spike_ratio"]
    volume_avg_days: int = _config["screening"]["volume_avg_days"]
    roe_min_pct: float = _config["screening"]["roe_min_pct"]
    stop_loss_pct: float = _config["screening"]["stop_loss_pct"]


class MarketFilter:
    nikkei_drop_threshold_pct: float = _config["market_filter"]["nikkei_drop_threshold_pct"]
    nikkei_ticker: str = _config["market_filter"]["nikkei_ticker"]


class Disclosure:
    tdnet_rss_url: str = _config["disclosure"]["tdnet_rss_url"]
    keywords: list[str] = _config["disclosure"]["keywords"]


class Output:
    csv_dir: str = _config["output"]["csv_dir"]
    csv_filename_format: str = _config["output"]["csv_filename_format"]


class Database:
    path: str = _config["database"]["path"]
    cache_hours: int = _config["database"]["cache_hours"]


DATA_SOURCE = _config["data_source"]
