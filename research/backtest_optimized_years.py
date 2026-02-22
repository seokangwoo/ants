import yfinance as yf
import pandas as pd
import numpy as np

def run_optimization():
    print("Fetching Data...")
    df_signal = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
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
    
    mas = {}
    for w in range(20, 251):
        mas[w] = close.rolling(window=w).mean()
        
    dates = df.index
    prices = close.values
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    # Benchmarking Years: 2019, 2023 mainly (2017 is fine)
    target_years = [2019, 2023]
    
    # Try Thresholds for Short Entry
    # 0.00 (Current) -> 0.03
    short_thresholds = [0.0, 0.01, 0.02, 0.03, 0.05]
    
    print("\n=== OPTIMIZATION FOR 2019/2023 ===")
    
    for threshold in short_thresholds:
        total_cagr = 0
        print(f"\nTesting Short Threshold: {threshold*100}% (Below MA)")
        
        for year in target_years:
            year_mask = (dates.year == year)
            if not any(year_mask): continue
            
            indices = np.where(year_mask)[0]
            start_i = indices[0]
            end_i = indices[-1]
            
            port_val = 1.0
            current_asset = 'Cash'
            fee = 0.002
            
            for i in range(start_i, end_i):
                curr_natr = natrs[i]
                curr_rsi = rsis[i]
                price = prices[i]
                
                # Logic
                if pd.isna(curr_natr) or curr_natr > 5.0:
                    target = 'Cash'
                else:
                    ma_len = int(140 - 25 * curr_natr)
                    ma_len = max(20, min(ma_len, 250))
                    ma_val = mas[ma_len].iloc[i]
                    
                    if pd.isna(ma_val): target = 'Cash'
                    elif price > ma_val: # Bull
                        if curr_rsi > 85: target = 'Cash'
                        else: target = 'Long'
                    elif price < ma_val * (1 - threshold): # Bear (Modified)
                        target = 'Short'
                    else: # Ambiguity Zone
                        target = 'Cash' 
                        # Or target = 'Hold Previous'? 
                        # Let's say Cash to be safe in chop.
                
                # Trade
                if target != current_asset:
                    if current_asset != 'Cash': port_val *= (1 - fee)
                    current_asset = target
                    
                # Return
                if i+1 < len(dates):
                    next_date = dates[i+1]
                    r = 0.0
                    if current_asset == 'Long':
                        r = long_rets.loc[next_date] if next_date in long_rets.index else 0
                    elif current_asset == 'Short':
                        r = short_rets.loc[next_date] if next_date in short_rets.index else 0
                    port_val *= (1 + r)
                    
            print(f"  Year {year} Return: {(port_val-1)*100:.2f}%")
            
        # Also run Full Backtest to ensure we didn't break the good years
        # Quick CAGR check
        port_val = 1.0
        current_asset = 'Cash'
        start_full = 250
        for i in range(start_full, len(dates)-1):
            curr_natr = natrs[i]
            curr_rsi = rsis[i]
            price = prices[i]
            
            if pd.isna(curr_natr) or curr_natr > 5.0: target = 'Cash'
            else:
                ma_len = int(140 - 25 * curr_natr)
                ma_len = max(20, min(ma_len, 250))
                ma_val = mas[ma_len].iloc[i]
                
                if pd.isna(ma_val): target = 'Cash'
                elif price > ma_val:
                    if curr_rsi > 85: target = 'Cash'
                    else: target = 'Long'
                elif price < ma_val * (1 - threshold): target = 'Short'
                else: target = 'Cash'
                
            if target != current_asset:
                if current_asset != 'Cash': port_val *= (1 - fee)
                current_asset = target
                
            if i+1 < len(dates):
                nd = dates[i+1]
                r=0
                if current_asset == 'Long': r = long_rets.get(nd, 0)
                elif current_asset == 'Short': r = short_rets.get(nd, 0)
                port_val *= (1+r)
                
        years = (dates[-1] - dates[start_full]).days / 365.25
        cagr = port_val ** (1/years) - 1
        print(f"  -> Full Period CAGR: {cagr*100:.2f}%")

if __name__ == "__main__":
    run_optimization()
