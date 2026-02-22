import yfinance as yf
import pandas as pd
import numpy as np

def run_vwma_boosted():
    print("Fetching Data...")
    df_signal = yf.download('069500.KS', start='2010-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2010-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-09-01', progress=False)
    
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df = pd.DataFrame({
        'Close': df_signal.loc[common]['Close'],
        'High': df_signal.loc[common]['High'],
        'Low': df_signal.loc[common]['Low'],
        'Volume': df_signal.loc[common]['Volume'],
        'Long': df_long.loc[common]['Close'],
        'Short': df_short.loc[common]['Close']
    }).dropna()
    
    high = df['High']
    low = df['Low']
    close = df['Close']
    volume = df['Volume']
    prev_close = close.shift(1)
    
    # NATR
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsis = rsi.values
    
    # Pre-calc VWMA
    # VWMA = Sum(Price*Vol) / Sum(Vol) over N days
    # Since N varies, we might need to pre-calc ALL VWMA lengths 20-250.
    print("Pre-calculating VWMA Universe...")
    vwmas = {}
    pv = close * volume
    for w in range(20, 251):
        vwmas[w] = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
    dates = df.index
    prices = close.values
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    # Parameters (From Grid Search + Previous Boosters)
    intercept = 140
    slope = 25
    rsi_limit = 85
    vol_limit = 5.0
    
    portfolio = [1.0]
    current_asset = 'Cash'
    fee = 0.002
    
    start_idx = 250
    
    print("Running Backtest...")
    
    for i in range(start_idx, len(dates)-1):
        curr_natr = natrs[i]
        curr_rsi = rsis[i]
        price = prices[i]
        
        target = 'Cash'
        
        # 1. Vol Filter
        if not pd.isna(curr_natr) and curr_natr > vol_limit:
            target = 'Cash'
        else:
            # 2. Dynamic VWMA
            if pd.isna(curr_natr): ma_len = intercept
            else: ma_len = int(intercept - (slope * curr_natr))
            
            ma_len = max(20, min(ma_len, 250))
            
            ma_val = vwmas[ma_len].iloc[i]
            
            if pd.isna(ma_val): target = 'Cash'
            elif price > ma_val:
                # Bull
                if not pd.isna(curr_rsi) and curr_rsi > rsi_limit:
                    target = 'Cash' # Profit Take
                else:
                    target = 'Long'
            else:
                target = 'Short'
                
        # Trade
        if target != current_asset:
            if current_asset != 'Cash': portfolio[-1] *= (1 - fee)
            current_asset = target
            
        # Return
        next_date = dates[i+1]
        r = 0.0
        if current_asset == 'Long': r = long_rets.get(next_date, 0)
        elif current_asset == 'Short': r = short_rets.get(next_date, 0)
        portfolio.append(portfolio[-1]*(1+r))
        
    final_val = portfolio[-1]
    years = (dates[-1] - dates[start_idx]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    print(f"=== VWMA Boosted Result ===")
    print(f"Final Value: {final_val:.2f}x")
    print(f"CAGR: {cagr*100:.2f}%")
    
if __name__ == "__main__":
    run_vwma_boosted()
