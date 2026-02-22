import yfinance as yf
import pandas as pd
import numpy as np
import ta
import quantstats as qs
import os

def get_zl_val(arr, window):
    res = np.full(len(arr), np.nan)
    lag = int((window - 1) / 2)
    for i in range(lag, len(arr)):
        res[i] = arr[i] + (arr[i] - arr[i-lag])
    return res

def run_recent_backtest():
    print("Fetching KOSPI 200 Data (2016-Present for warming up indicators)...")
    # Fetch full data to ensure indicators like ADX and MA are warmed up
    df_signal = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df_signal = df_signal.loc[common]; df_long = df_long.loc[common]; df_short = df_short.loc[common]
    
    close = df_signal['Close'].values; high = df_signal['High'].values
    low = df_signal['Low'].values; volume = df_signal['Volume'].values
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values
    
    # 72.14% Champion Engine
    adx_obj = ta.trend.ADXIndicator(df_signal['High'], df_signal['Low'], df_signal['Close'])
    adx = adx_obj.adx().values / 10.0
    A, B, C = 0.6, -35, 170
    vwma_lens = (A * (adx**2) + B * adx + C).astype(int).clip(20, 300)
    pv_vals = close * volume
    
    # NATR
    tr = pd.concat([df_signal['High']-df_signal['Low'], 
                   abs(df_signal['High']-df_signal['Close'].shift(1)), 
                   abs(df_signal['Low']-df_signal['Close'].shift(1))], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natrs = (atr / df_signal['Close'] * 100).fillna(2.0).values
    
    # RSI (Common)
    rsi = ta.momentum.RSIIndicator(df_signal['Close'], window=14).rsi().fillna(50).values
    
    # Stochastic Zero-Lag
    stoch_src = ta.momentum.StochRSIIndicator(df_signal['Close'], window=10).stochrsi_k().fillna(0.5).values
    stoch_zl = get_zl_val(stoch_src, 10)
    
    # Simulation
    p = 1.0; cur = None; fee = 0.002
    rets = [0.0] * len(close)
    for i in range(300, len(close)-1):
        if natrs[i] > 5.0: target = 'Cash'
        else:
            w = vwma_lens[i]
            ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
            if close[i] > ma:
                if rsi[i] > 85 and (stoch_zl[i] > 0.9 or np.isnan(stoch_zl[i])): target = 'Cash'
                else: target = 'Long'
            else: target = 'Short'
        
        if target != cur:
            p *= (1 - fee)
            cur = target
        r = long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)
        p *= (1 + r)
        rets[i+1] = r
    
    full_rets = pd.Series(rets, index=df_signal.index)
    
    # Filter for 2025 onwards
    recent_rets = full_rets.loc['2025-01-01':]
    recent_rets.index = pd.to_datetime(recent_rets.index).tz_localize(None)
    
    benchmark = df_signal['Close'].pct_change().loc['2025-01-01':]
    benchmark.index = pd.to_datetime(benchmark.index).tz_localize(None)
    
    output_path = 'reports/recent_performance_2025.html'
    print(f"Generating Recent Performance Report: {output_path}...")
    qs.reports.html(recent_rets, benchmark=benchmark, output=output_path, title='Recent Performance (2025-2026): 72.14% Strategy')
    
    print("\n=== 2025+ Performance Summary ===")
    total_ret = (recent_rets + 1).prod() - 1
    print(f"Cumulative Return (2025-01-01 to Present): {total_ret*100:.2f}%")

if __name__ == "__main__":
    run_recent_backtest()
