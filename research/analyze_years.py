import yfinance as yf
import pandas as pd
import numpy as np

def run_analysis():
    print("Fetching Data...")
    df_signal = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
    # Clean Columns
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    # Align
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df = pd.DataFrame({
        'Close': df_signal.loc[common]['Close'],
        'High': df_signal.loc[common]['High'],
        'Low': df_signal.loc[common]['Low'],
        'Long': df_long.loc[common]['Close'],
        'Short': df_short.loc[common]['Close']
    }).dropna()
    
    # Indicators
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
    
    # MAs
    mas = {}
    for w in range(20, 251):
        mas[w] = close.rolling(window=w).mean()
        
    dates = df.index
    prices = close.values
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    bench_rets = df['Close'].pct_change()
    
    years_to_analyze = [2017, 2019, 2023]
    
    # Strategy Logic
    intercept = 140
    slope = 25
    rsi_limit = 85
    vol_limit = 5.0
    
    print("\n=== YEARLY ANALYSIS ===")
    
    for target_year in years_to_analyze:
        print(f"\nEvaluating Year: {target_year}")
        
        # Filter for this year
        year_mask = (dates.year == target_year)
        if not any(year_mask):
            print("No data.")
            continue
            
        indices = np.where(year_mask)[0]
        start_i = indices[0]
        end_i = indices[-1]
        
        # Run Simulation for this year
        port_val = 1.0
        bench_val = 1.0
        current_asset = 'Cash'
        fee = 0.002
        trades = 0
        whipsaws = 0 # Bought then Sold with loss shortly?
        
        # Debug Logs
        cash_days = 0
        long_days = 0
        short_days = 0
        
        missed_rally_days = []
        
        for i in range(start_i, end_i): # Don't go out of bounds
            # Index i corresponds to Signal Date
            # Trade happens at close of i (or next open), Return is realized at i+1
            
            curr_natr = natrs[i]
            curr_rsi = rsis[i]
            price = prices[i]
            date = dates[i]
            
            # Logic
            reason = ""
            target = 'Cash'
            
            if pd.isna(curr_natr) or pd.isna(curr_rsi):
                target = 'Cash'
            elif curr_natr > vol_limit:
                target = 'Cash'
                reason = "VolFilter"
            else:
                ma_len = int(intercept - (slope * curr_natr))
                ma_len = max(20, min(ma_len, 250))
                ma_val = mas[ma_len].iloc[i]
                
                if pd.isna(ma_val): target = 'Cash'
                elif price > ma_val:
                    if curr_rsi > rsi_limit:
                        target = 'Cash'
                        reason = f"RSI_Exit({curr_rsi:.1f})"
                    else:
                        target = 'Long'
                else:
                    target = 'Short'
            
            # Trade
            if target != current_asset:
                if current_asset != 'Cash': port_val *= (1 - fee)
                current_asset = target
                trades += 1
                # print(f"  {date.date()}: Switch to {target} ({reason})")
                
            # Count States
            if current_asset == 'Long': long_days += 1
            elif current_asset == 'Short': short_days += 1
            else: cash_days += 1
            
            # Returns for Next Day
            if i+1 < len(dates):
                next_date = dates[i+1]
                
                # Bench
                br = bench_rets.loc[next_date] if next_date in bench_rets.index else 0
                bench_val *= (1 + br)
                
                # Strategy
                sr = 0.0
                if current_asset == 'Long':
                    sr = long_rets.loc[next_date] if next_date in long_rets.index else 0
                elif current_asset == 'Short':
                    sr = short_rets.loc[next_date] if next_date in short_rets.index else 0
                
                port_val *= (1 + sr)
                
                # Check for "Missed Rally"
                # If Market went up > 1% and we were in Cash or Short
                if br > 0.01 and current_asset != 'Long':
                    missed_rally_days.append(f"{next_date.date()} (+{br*100:.1f}%) Asset: {current_asset} Reason: {reason}")
                    
        print(f"Strategy Return: {(port_val-1)*100:.2f}%")
        print(f"Benchmark Return: {(bench_val-1)*100:.2f}%")
        print(f"Trades: {trades}")
        print(f"Days: Long({long_days}) Short({short_days}) Cash({cash_days})")
        print(f"Missed Rallies (>1% days missed): {len(missed_rally_days)}")
        if len(missed_rally_days) > 0:
            print(f"Top 3 Missed: {missed_rally_days[:3]}")

if __name__ == "__main__":
    run_analysis()
