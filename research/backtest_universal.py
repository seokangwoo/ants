import yfinance as yf
import pandas as pd
import numpy as np
import ta
import quantstats as qs

def run_universal_backtest(ticker_symbol, long_ticker, short_ticker, name):
    print(f"\n--- Testing Universal Engine on: {name} ({ticker_symbol}) ---")
    
    # Data Fetching
    df_signal = yf.download(ticker_symbol, start='2016-01-01', progress=False)
    df_long = yf.download(long_ticker, start='2016-01-01', progress=False)
    df_short = yf.download(short_ticker, start='2016-01-01', progress=False)
    
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df_signal = df_signal.loc[common]
    df_long = df_long.loc[common]
    df_short = df_short.loc[common]
    
    close = df_signal['Close']
    high = df_signal['High']
    low = df_signal['Low']
    volume = df_signal['Volume']
    
    # 1. ADX calculation
    adx_obj = ta.trend.ADXIndicator(high, low, close, window=14)
    adx = adx_obj.adx()
    
    # 2. UNIVERSAL NORMALIZATION (The "Secret Sauce")
    # Instead of raw values, we use Rolling Percentile Rank (0.0 to 1.0)
    # This makes the strategy "Unit-less" and "Asset-agnostic".
    lookback = 250 # 1 year history
    adx_rank = adx.rolling(window=lookback).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1])
    
    # 3. Dynamic Length Mapping
    # Strongest Trend (Rank 1.0) -> 30 days
    # Weakest Trend (Rank 0.0) -> 200 days
    fastest_len = 30
    slowest_len = 200
    dynamic_len = slowest_len - (adx_rank * (slowest_len - fastest_len))
    dynamic_len = dynamic_len.fillna(140).astype(int).clip(20, 250)
    
    # 4. NATR (Universal Exit Filter)
    tr = pd.concat([high-low, abs(high-close.shift(1)), abs(low-close.shift(1))], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    
    # 5. Dynamic Indicators (RSI/Stoch)
    # We use the same percentile logic or keep it relative.
    # Standard Wilder RSI is already 0-100, so it's somewhat universal.
    rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
    
    # Portfolio Sim
    portfolio = [1.0]
    current_asset = 'Cash'
    fee = 0.002
    
    long_rets = df_long['Close'].pct_change()
    short_rets = df_short['Close'].pct_change()
    
    dates = df_signal.index
    start_idx = lookback + 20 # Wait for Rank normalization
    
    for i in range(start_idx, len(dates)-1):
        price = close.iloc[i]
        c_natr = natr.iloc[i]
        target = 'Cash'
        
        # Self-Adapting Signal Logic
        # 1. Vol Panic Check (Normalizing NATR might be too slow for crash, keep 5.0 absolute as it's a percentage)
        if not pd.isna(c_natr) and c_natr > 5.0:
            target = 'Cash'
        else:
            mlen = dynamic_len.iloc[i]
            # VWMA
            pv = (close * volume).iloc[i-mlen+1:i+1].sum()
            v_sum = volume.iloc[i-mlen+1:i+1].sum()
            ma_val = pv / v_sum if v_sum > 0 else np.nan
            
            if pd.isna(ma_val): target = 'Cash'
            elif price > ma_val: target = 'Long'
            else: target = 'Short'
            
        if target != current_asset:
            portfolio[-1] *= (1 - fee)
            current_asset = target
            
        r = long_rets.iloc[i+1] if current_asset == 'Long' else (short_rets.iloc[i+1] if current_asset == 'Short' else 0.0)
        portfolio.append(portfolio[-1] * (1 + r))
        
    final_p = portfolio[-1]
    years = (dates[-1] - dates[start_idx]).days / 365.25
    cagr = (final_p**(1/years) - 1) * 100
    print(f"[{name}] Final Capital: {final_p:.2f}x, CAGR: {cagr:.2f}%")
    return cagr

if __name__ == "__main__":
    # Test on KOSPI
    run_universal_backtest('069500.KS', '122630.KS', '252670.KS', 'KOSPI 200 Universal')
    
    # Test on KOSDAQ (Using SAME CODE)
    run_universal_backtest('229200.KS', '233740.KS', '251340.KS', 'KOSDAQ 150 Universal')
