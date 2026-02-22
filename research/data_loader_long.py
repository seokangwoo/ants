import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime

def fetch_etf_data(ticker, start_date="2014-01-01", end_date=None):
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
        
    df = fdr.DataReader(ticker, start_date, end_date)
    return df

def get_etf_universe():
    return {
        'KODEX 200': '069500',          # Korea Market
        'TIGER S&P500': '143850',       # US Market (KRW Hedged/Unhedged? usually unhedged captures FX too)
        'TIGER NASDAQ100': '133690',    # US Tech
        'KODEX 10Y Bond': '152380',     # Safe Asset (KR Bond)
        'KODEX Gold': '132030',         # Safe Asset (Gold)
        'KODEX Dollar': '138230'        # Safe Asset (Dollar Defense)
    }

def fetch_all_etfs():
    universe = get_etf_universe()
    data = {}
    print("Fetching 10-Year Data for Dual Momentum...")
    for name, ticker in universe.items():
        print(f"  Fetching {name} ({ticker})...")
        df = fetch_etf_data(ticker)
        data[name] = df
    return data
