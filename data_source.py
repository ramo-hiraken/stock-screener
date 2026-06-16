"""データソースアダプタ。yfinance を既定とし、将来 J-Quants 等に差し替え可能。"""

from abc import ABC, abstractmethod
import pandas as pd
import yfinance as yf

from db import is_cache_fresh, save_ohlcv, load_ohlcv
from settings import DATA_SOURCE


class DataSourceBase(ABC):
    @abstractmethod
    def fetch_ohlcv(self, code: str, period_days: int = 365) -> pd.DataFrame:
        """OHLCV DataFrame (index=DatetimeIndex, columns=Open/High/Low/Close/Volume) を返す"""
        ...

    @abstractmethod
    def fetch_info(self, code: str) -> dict:
        """銘柄基本情報（ROE, marketCap 等）を返す"""
        ...

    @abstractmethod
    def fetch_index_history(self, ticker: str, period_days: int = 30) -> pd.DataFrame:
        """指数のOHLCVを返す（相場環境フィルタ用）"""
        ...


class YFinanceSource(DataSourceBase):
    def fetch_ohlcv(self, code: str, period_days: int = 365) -> pd.DataFrame:
        if is_cache_fresh(code):
            cached = load_ohlcv(code, days=period_days)
            if not cached.empty:
                return cached

        ticker = yf.Ticker(f"{code}.T")
        period = "2y" if period_days > 365 else "1y"
        try:
            hist = ticker.history(period=period)
        except Exception:
            return load_ohlcv(code, days=period_days)

        if hist.empty:
            return load_ohlcv(code, days=period_days)

        save_ohlcv(code, hist)
        return hist

    def fetch_info(self, code: str) -> dict:
        ticker = yf.Ticker(f"{code}.T")
        try:
            return ticker.info
        except Exception:
            return {}

    def fetch_index_history(self, ticker: str, period_days: int = 30) -> pd.DataFrame:
        t = yf.Ticker(ticker)
        try:
            return t.history(period=f"{period_days}d")
        except Exception:
            return pd.DataFrame()


class JQuantsSource(DataSourceBase):
    """将来実装用のスタブ。J-Quants Light以上で利用可能。"""

    def fetch_ohlcv(self, code: str, period_days: int = 365) -> pd.DataFrame:
        raise NotImplementedError("J-Quants adapter not yet implemented")

    def fetch_info(self, code: str) -> dict:
        raise NotImplementedError("J-Quants adapter not yet implemented")

    def fetch_index_history(self, ticker: str, period_days: int = 30) -> pd.DataFrame:
        raise NotImplementedError("J-Quants adapter not yet implemented")


def get_data_source() -> DataSourceBase:
    if DATA_SOURCE == "jquants":
        return JQuantsSource()
    return YFinanceSource()
