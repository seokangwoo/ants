import yfinance as yf
import pandas as pd
import numpy as np

def calculate_adx(high, low, close, window=14):
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    
    tr1 = pd.DataFrame(high - low)
    tr2 = pd.DataFrame(abs(high - close.shift(1)))
    tr3 = pd.DataFrame(abs(low - close.shift(1)))
    frames = [tr1, tr2, tr3]
    tr = pd.concat(frames, axis=1, join='inner').max(axis=1)
    atr = tr.rolling(window).mean()
    
    plus_di = 100 * (plus_dm.ewm(alpha=1/window).mean() / atr)
    minus_di = abs(100 * (minus_dm.ewm(alpha=1/window).mean() / atr))
    dx = (abs(plus_di - minus_di) / abs(plus_di + minus_di)) * 100
    adx = dx.rolling(window).mean()
    return adx

def run_adx_optimization():
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
        'Long': df_long.loc[common]['Close'],
        'Short': df_short.loc[common]['Close']
    }).dropna()
    
    high = df['High']
    low = df['Low']
    close = df['Close']
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
    
    # ADX
    print("Calculating ADX...")
    adx_series = calculate_adx(high, low, close, window=14)
    adxs = adx_series.values
    
    mas = {}
    for w in range(20, 251):
        mas[w] = close.rolling(window=w).mean()
        
    dates = df.index
    prices = close.values
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    # Grid Search applied to bad years
    # ADX Thresholds: [0 (None), 15, 20, 25, 30]
    adx_thresholds = [0, 15, 20, 25, 30]
    target_years = [2017, 2019, 2023]
    
    print("\n=== ADX FILTER OPTIMIZATION ===")
    
    for thresh in adx_thresholds:
        print(f"\nTesting ADX Threshold: {thresh}")
        
        # Check Bad Years
        for year in target_years:
            mask = (dates.year == year)
            if not any(mask): continue
            
            indices = np.where(mask)[0]
            start_i = indices[0]
            end_i = indices[-1]
            
            port_val = 1.0
            current_asset = 'Cash'
            fee = 0.002
            
            for i in range(start_i, end_i):
                curr_natr = natrs[i]
                curr_rsi = rsis[i]
                curr_adx = adxs[i]
                price = prices[i]
                
                if pd.isna(curr_natr) or curr_natr > 5.0: target = 'Cash'
                elif pd.isna(curr_adx) or curr_adx < thresh: target = 'Cash' # ADX Filter!
                else:
                    ma_len = int(140 - 25 * curr_natr)
                    ma_len = max(20, min(ma_len, 250))
                    ma_val = mas[ma_len].iloc[i]
                    
                    if pd.isna(ma_val): target = 'Cash'
                    elif price > ma_val:
                        if curr_rsi > 85: target = 'Cash'
                        else: target = 'Long'
                    else:
                        target = 'Short'
                        
                if target != current_asset:
                    if current_asset != 'Cash': port_val *= (1 - fee)
                    current_asset = target
                    
                if i+1 < len(dates):
                    nd = dates[i+1]
                    r = 0.0
                    if current_asset == 'Long': r = long_rets.get(nd, 0)
                    elif current_asset == 'Short': r = short_rets.get(nd, 0)
                    port_val *= (1+r)
                    
            print(f"  Year {year}: {(port_val-1)*100:.2f}%")
            
        # Full Period Check
        port_val = 1.0
        current_asset = 'Cash'
        start_full = 250
        
        for i in range(start_full, len(dates)-1):
            curr_natr = natrs[i]
            curr_rsi = rsis[i]
            curr_adx = adxs[i]
            price = prices[i]
            
            if pd.isna(curr_natr) or curr_natr > 5.0: target = 'Cash'
            elif pd.isna(curr_adx) or curr_adx < thresh: target = 'Cash'
            else:
                ma_len = int(140 - 25 * curr_natr)
                ma_len = max(20, min(ma_len, 250))
                ma_val = mas[ma_len].iloc[i]
                
                if pd.isna(ma_val): target = 'Cash'
                elif price > ma_val:
                    if curr_rsi > 85: target = 'Cash'
                    else: target = 'Long'
                else:
                    target = 'Short'
                    
            if target != current_asset:
                if current_asset != 'Cash': port_val *= (1 - fee)
                current_asset = target
                
            if i+1 < len(dates):
                nd = dates[i+1]
                r = 0.0
                if current_asset == 'Long': r = long_rets.get(nd, 0)
                elif current_asset == 'Short': r = short_rets.get(nd, 0)
                port_val *= (1+r)
        
        years = (dates[-1] - dates[start_full]).days / 365.25
        cagr = port_val ** (1/years) - 1
        print(f"  -> Full Period CAGR: {cagr*100:.2f}%")

if __name__ == "__main__":
    run_adx_optimization()
