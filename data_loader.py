import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta

def fetch_daily_data(ticker, start_date, end_date=None):
    """
    Fetch daily OHLCV data for a given ticker.
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
        
    df = fdr.DataReader(ticker, start_date, end_date)
    return df

def get_top_liquid_tickers(limit=5):
    """
    Returns a list of top liquid KOSPI/KOSDAQ stocks.
    For simplicity, checking specific known liquid stocks.
    """
    # 005930: Samsung Electronics
    # 000660: SK Hynix
    # 005380: Hyundai Motor
    # 035420: NAVER
    # 051910: LG Chem
    # 086520: Ecopro (High Volatility)
    # 003670: Posco Future M
    # 196170: Alteogen (Bio Growth)
    return ['005930', '000660', '005380', '035420', '051910', '086520', '003670', '196170']
