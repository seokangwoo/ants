import yfinance as yf
import pandas as pd
import numpy as np
import ta
from itertools import product
import time

def get_zl_val(arr, window):
    res = np.full(len(arr), np.nan)
    lag = int((window - 1) / 2)
    for i in range(lag, len(arr)):
        res[i] = arr[i] + (arr[i] - arr[i-lag])
    return res

def calculate_vhf(close, window=28):
    # Vertical Horizontal Filter
    high_w = pd.Series(close).rolling(window).max()
    low_w = pd.Series(close).rolling(window).min()
    diff = abs(pd.Series(close).diff())
    sum_diff = diff.rolling(window).sum()
    vhf = abs(high_w - low_w) / sum_diff
    return vhf.fillna(0).values * 100.0 # Scale to 0-100ish

def calculate_er(close, window=10):
    # Efficiency Ratio (Kaufman)
    change = abs(pd.Series(close).diff(window))
    volatility = abs(pd.Series(close).diff()).rolling(window).sum()
    er = change / volatility
    return er.fillna(0).values * 100.0 # Scale to 0-100

def run_engine_battle():
    print("Fetching KOSPI 200 Data for Engine Battle...")
    df = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df.index.intersection(df_long.index).intersection(df_short.index)
    df = df.loc[common]; df_long = df_long.loc[common]; df_short = df_short.loc[common]
    
    close = df['Close'].values; high = df['High'].values
    low = df['Low'].values; volume = df['Volume'].values
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values
    
    # Pre-calculate Indicators
    print("Calculating Candidate Metrics...")
    metrics = {
        'ADX': ta.trend.ADXIndicator(df['High'], df['Low'], df['Close']).adx().values / 10.0,
        'VHF': calculate_vhf(close) / 10.0,
        'ER': calculate_er(close) / 10.0
    }
    
    # Common Components
    natr = (ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close']).average_true_range() / df['Close'] * 100).values
    rsi = ta.momentum.RSIIndicator(df['Close']).rsi().values
    stoch_k = ta.momentum.StochRSIIndicator(df['Close'], window=10).stochrsi_k()
    stoch_zl = (stoch_k + (stoch_k - stoch_k.shift(4))).values
    pv_vals = close * volume
    
    # Search Optimization (Greedy for A, B, C)
    A_list = [0.4, 0.6, 0.8]
    B_list = [-30, -35, -40]
    C_list = [150, 170, 190]
    
    best_overall_cagr = -999; best_overall_params = None
    
    for m_name, m_vals in metrics.items():
        print(f"\nEvaluating Engine Metric: {m_name}")
        best_metric_cagr = -999
        
        for a, b, c_val in product(A_list, B_list, C_list):
            p = 1.0; cur = None; fee = 0.002
            # Length = a*x^2 + b*x + c
            lengths = (a * (m_vals**2) + b * m_vals + c_val).astype(int).clip(20, 300)
            
            for i in range(300, len(close)-1):
                if natr[i] > 5.0: target = 'Cash'
                else:
                    w = lengths[i]
                    ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
                    if close[i] > ma:
                        if rsi[i] > 85 and stoch_zl[i] > 0.9: target = 'Cash'
                        else: target = 'Long'
                    else: target = 'Short'
                
                if target != cur:
                    p *= (1 - fee); cur = target
                p *= (1 + (long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)))
                
            years = (len(close) - 300) / 252
            cagr = (p**(1/years) - 1) * 100
            if cagr > best_metric_cagr:
                best_metric_cagr = cagr
                if cagr > best_overall_cagr:
                    best_overall_cagr = cagr
                    best_overall_params = (m_name, a, b, c_val)
                    
        print(f" -> Best for {m_name}: {best_metric_cagr:.2f}%")

    print(f"\n=== ENGINE WAR WINNER ===")
    print(f"Global Winner: {best_overall_params[0]}")
    print(f"Top CAGR: {best_overall_cagr:.2f}%")
    print(f"Params: A={best_overall_params[1]}, B={best_overall_params[2]}, C={best_overall_params[3]}")
    print(f"Previous Champion (ADX): 72.14%")

if __name__ == "__main__":
    run_engine_battle()
