import yfinance as yf
import pandas as pd
import numpy as np
import quantstats as qs
import matplotlib.pyplot as plt

# --- 1. Re-Run The Strategy Logic (Exact Match force-fed to QuantStats) ---
def run_strategy_and_viz():
    print("Fetching Data (via yfinance)...")
    
    # KODEX 200 (Signal)
    df_signal = yf.download('069500.KS', start='2010-01-01', progress=False)
    
    # KODEX Leverage (Long)
    df_long = yf.download('122630.KS', start='2010-01-01', progress=False)
    
    # KODEX Inverse 2X (Short)
    df_short = yf.download('252670.KS', start='2016-09-01', progress=False) 
    # Note: 252670 started late 2016.
    
    # Clean up YF data (Drop MultiIndex if present, usually not for single download)
    # Ensure columns are simple
    if isinstance(df_signal.columns, pd.MultiIndex):
        df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex):
        df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex):
        df_short.columns = df_short.columns.get_level_values(0)
        
    # Align
    # We need to intersection index
    common_index = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    
    df_signal = df_signal.loc[common_index]
    df_long = df_long.loc[common_index]
    df_short = df_short.loc[common_index]
    
    df = pd.DataFrame({
        'Close': df_signal['Close'], 
        'High': df_signal['High'], 
        'Low': df_signal['Low'],
        'Long': df_long['Close'], 
        'Short': df_short['Close']
    }).dropna()
    
    dates = df.index
    
    # Indicators (FinalBoostedStrategy)
    high = df['High']
    low = df['Low']
    close = df['Close']
    prev_close = close.shift(1)
    
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    
    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # Pre-calc MAs
    mas = {}
    for w in range(20, 251):
        mas[w] = close.rolling(window=w).mean()
        
    print(f"Data Range: {dates[0]} ~ {dates[-1]}")
    
    # Backtest Loop
    portfolio = [1.0]
    fee = 0.002
    current_asset = 'Cash'
    
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    prices = close.values
    natrs = natr.values
    rsis = rsi.values
    
    # Parameters (Holy Grail)
    base_int = 140
    base_slope = 25
    rsi_limit = 85
    vol_limit = 5.0
    
    start_idx = 250
    
    for i in range(start_idx, len(dates)-1):
        next_date = dates[i+1]
        price = prices[i]
        curr_natr = natrs[i]
        curr_rsi = rsis[i]
        
        # Logic
        if pd.isna(curr_natr) or pd.isna(curr_rsi):
            target = 'Cash'
        elif curr_natr > vol_limit:
            target = 'Cash' # Crash Guard
        else:
            # Dynamic MA
            ma_len = int(base_int - (base_slope * curr_natr))
            ma_len = max(20, min(ma_len, 250))
            ma_val = mas[ma_len].iloc[i]
            
            if pd.isna(ma_val): target = 'Cash'
            elif price > ma_val:
                # Bull
                if curr_rsi > rsi_limit:
                    target = 'Cash' # Profit Take
                else:
                    target = 'Long'
            else:
                target = 'Short'
                
        # Trade
        if target != current_asset:
            if current_asset != 'Cash':
                 portfolio[-1] *= (1 - fee)
            current_asset = target
            
        # Return
        r = 0.0
        if current_asset == 'Long':
            if next_date in long_rets.index: r = long_rets.loc[next_date]
        elif current_asset == 'Short':
            if next_date in short_rets.index: r = short_rets.loc[next_date]
            
        if pd.isna(r): r = 0.0
        portfolio.append(portfolio[-1] * (1 + r))
        
    # Create Series for QuantStats
    # Result index is dates from start_idx to end
    result_index = dates[start_idx:]
    
    val_series = pd.Series(portfolio, index=result_index)
    
    # Remove timezone if present
    if val_series.index.tz is not None:
        val_series.index = val_series.index.tz_localize(None)
        
    ret_series = val_series.pct_change().dropna()
    
    # Run QuantStats
    print("Generating QuantStats Report (Professional Tear Sheet)...")
    # Benchmark: SPY is default, but let's try '069500.KS' or '^KS11' for local context?
    # Actually SPY is good global benchmark. Or we can disable if it fails.
    try:
        qs.reports.html(ret_series, benchmark='^KS11', output='strategy_report.html', title='ANTS Final Strategy (>50% CAGR)')
    except Exception as e:
        print(f"Benchmark failed ({e}), trying 069500.KS...")
        try:
             qs.reports.html(ret_series, benchmark='069500.KS', output='strategy_report.html', title='ANTS Final Strategy (>50% CAGR)')
        except:
             qs.reports.html(ret_series, benchmark=None, output='strategy_report.html', title='ANTS Final Strategy (>50% CAGR)')
    
    print("Report generated: 'strategy_report.html'")
    print(f"Final CAGR: {qs.stats.cagr(ret_series) * 100:.2f}%")
    print(f"Sharpe Ratio: {qs.stats.sharpe(ret_series):.2f}")
    
if __name__ == "__main__":
    run_strategy_and_viz()
