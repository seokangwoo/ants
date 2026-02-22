import yfinance as yf
import pandas as pd
import numpy as np

def calculate_wilder_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_stoch_rsi(series, period=14, smooth_k=3, smooth_d=3):
    rsi = calculate_wilder_rsi(series, period)
    stoch_rsi = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min())
    stoch_rsi_k = stoch_rsi.rolling(smooth_k).mean()
    return stoch_rsi, stoch_rsi_k

def run_final_check():
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
    
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']
    prev_close = close.shift(1)
    
    # 1. Base Engine (VWMA NATR)
    print("Calculating Base Engine (VWMA)...")
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    # VWMA Universe
    vwmas = {}
    pv = close * volume
    for w in range(20, 251):
        vwmas[w] = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
    prices = close.values
    dates = df.index
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    # 2. Indicators (Wilder's RSI + StochRSI)
    print("Calculating Indicators (Wilder's RSI)...")
    rsi = calculate_wilder_rsi(close, 14)
    stoch_rsi_raw, stoch_rsi_k = calculate_stoch_rsi(close, 14, 3, 3)
    
    rsis = rsi.values
    stoch_ks = stoch_rsi_k.values
    
    # 3. Strategy Loop
    portfolio = [1.0]
    current_asset = 'Cash'
    fee = 0.002
    
    start_idx = 250
    
    # Logic:
    # Entry: Price > VWMA (Dynamic Length)
    # Exit 1 (Profit): RSI > 85 AND StochRSI_K > 0.8
    # Exit 2 (Crash): NATR > 5.0
    
    intercept = 140
    slope = 25
    
    for i in range(start_idx, len(dates)-1):
        curr_natr = natrs[i]
        curr_rsi = rsis[i]
        curr_stoch = stoch_ks[i]
        price = prices[i]
        
        target = 'Cash'
        
        if pd.isna(curr_natr) or curr_natr > 5.0:
            target = 'Cash'
        else:
            ma_len = int(intercept - (slope * curr_natr))
            ma_len = max(20, min(ma_len, 250))
            
            ma_val = vwmas[ma_len].iloc[i]
            
            if pd.isna(ma_val): target = 'Cash'
            elif price > ma_val: # Bull
                # EXTREME PROFIT TAKE
                if (curr_rsi > 85) and (curr_stoch > 0.8):
                    target = 'Cash'
                else:
                    target = 'Long'
            else:
                target = 'Short'
                
        if target != current_asset:
            if current_asset != 'Cash': portfolio[-1] *= (1 - fee)
            current_asset = target
            
        next_date = dates[i+1]
        r = 0.0
        if current_asset == 'Long': r = long_rets.get(next_date, 0)
        elif current_asset == 'Short': r = short_rets.get(next_date, 0)
        portfolio.append(portfolio[-1]*(1+r))
        
    final_val = portfolio[-1]
    years = (dates[-1] - dates[start_idx]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    print(f"=== FINAL CHECK ===")
    print(f"Strategy: VWMA + Wilder's RSI(85) + StochRSI(0.8)")
    print(f"Final Value: {final_val:.2f}x")
    print(f"CAGR: {cagr*100:.2f}%")

if __name__ == "__main__":
    run_final_check()
