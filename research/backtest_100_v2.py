import yfinance as yf
import pandas as pd
import numpy as np
import quantstats as qs

def calculate_dynamic_rsi(close, vol_series, base_period=14, ref_vol=0.01):
    # RSI with dynamic period is tricky to vectorize.
    # We must loop or use a clever rolling apply?
    # Rolling apply with variable window is not supported easily in pandas.
    # We will use a loop for calculation. It's slow but accurate.
    
    rsi_values = []
    close_vals = close.values
    vol_vals = vol_series.values
    
    # Pre-calculate changes
    delta = close.diff().values
    
    # We need a history buffer
    # But window length changes.
    
    for i in range(len(close)):
        if i < 50: 
            rsi_values.append(50)
            continue
            
        # Determine Period
        vol = vol_vals[i]
        if pd.isna(vol) or vol == 0:
            window = base_period
        else:
            # Formula: Higher Vol -> Shorter Window
            # Window = Base * (Ref / Vol)
            # Example: Base=14, Ref=1.0 (Average NATR), Vol=2.0 -> Window=7
            window = int(base_period * (ref_vol / vol))
            
        window = max(2, min(window, 50))
        
        # Calculate RSI for this specific window ending at i
        # Slice delta[i-window+1 : i+1]
        
        subset = delta[i-window+1 : i+1]
        
        gains = subset[subset > 0]
        losses = -subset[subset < 0]
        
        avg_gain = gains.mean() if len(gains) > 0 else 0
        avg_loss = losses.mean() if len(losses) > 0 else 0
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
        rsi_values.append(rsi)
        
    return np.array(rsi_values)

def run_100_v2():
    print("Fetching Data...")
    df_signal = yf.download('069500.KS', start='2010-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2010-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-09-01', progress=False)
    
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
    
    # NATR (For MA)
    high = df['High']
    low = df['Low']
    close = df['Close']
    prev_close = close.shift(1)
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100 # This is our Vol metric
    
    # Dynamic RSI
    # Ref Vol? Average NATR is approx 1.5%.
    print("Calculating Dynamic RSI...")
    dyn_rsi = calculate_dynamic_rsi(close, natr, base_period=14, ref_vol=1.5)
    
    # Pre-calc MAs (SMA is Champion)
    mas = {}
    for w in range(10, 251):
        mas[w] = close.rolling(window=w).mean()
        
    dates = df.index
    prices = close.values
    natrs = natr.values
    
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    # Grid Search
    # We trust our MA Engine (140, 25).
    # We optimize the RSI Trigger.
    
    rsi_limits = [80, 85, 90, 95]
    
    best_cagr = -999
    
    start_idx = 250
    
    print("Optimization Loop...")
    
    for rsi_limit in rsi_limits:
        portfolio = [1.0]
        fee = 0.002
        current_asset = 'Cash'
        
        for i in range(start_idx, len(dates)-1):
            curr_natr = natrs[i]
            curr_rsi = dyn_rsi[i]
            price = prices[i]
            
            # 1. Crash Guard
            if curr_natr > 5.0:
                target = 'Cash'
            else:
                # 2. MA Logic
                if pd.isna(curr_natr): ma_len = 140
                else: ma_len = int(140 - (25 * curr_natr))
                ma_len = max(20, min(ma_len, 250))
                
                ma_val = mas[ma_len].iloc[i]
                
                if pd.isna(ma_val): target = 'Cash'
                elif price > ma_val:
                    # Bull
                    # 3. Dynamic RSI Check
                    if curr_rsi > rsi_limit:
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
            if current_asset == 'Long':
                r = long_rets.loc[next_date] if next_date in long_rets.index else 0
            elif current_asset == 'Short':
                r = short_rets.loc[next_date] if next_date in short_rets.index else 0
                
            if pd.isna(r): r=0
            portfolio.append(portfolio[-1]*(1+r))
            
        final_val = portfolio[-1]
        years = (dates[-1] - dates[start_idx]).days / 365.25
        cagr = final_val ** (1/years) - 1
        
        if cagr > best_cagr:
            best_cagr = cagr
            print(f"New Best! RSI_Limit{rsi_limit}: {final_val:.1f}x (CAGR {cagr*100:.2f}%)")
            
    print(f"Best Dynamic RSI Result: {best_cagr*100:.2f}%")
    
if __name__ == "__main__":
    run_100_v2()
