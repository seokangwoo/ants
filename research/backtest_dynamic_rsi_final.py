import yfinance as yf
import pandas as pd
import numpy as np

def calculate_dynamic_rsi_series(close, vol_series, base_period=14, ref_vol=1.5):
    # RSI = 100 - 100 / (1 + RS)
    # RS = AvgGain / AvgLoss
    # Window varies per day.
    
    rsi_out = np.zeros(len(close))
    rsi_out[:] = np.nan
    
    delta = close.diff().values
    vol_vals = vol_series.values
    
    # We need to compute RSI per day based on that day's window.
    # To make it faster, we can't fully vectorize dynamic window rolling.
    # Loop is necessary.
    
    for i in range(50, len(close)):
        vol = vol_vals[i]
        if pd.isna(vol) or vol == 0:
            w = base_period
        else:
            # Formula: Higher Vol -> Shorter Period (Faster reaction)
            # Window = Base * (Ref / Vol)
            w = int(base_period * (ref_vol / vol))
            
        w = max(4, min(w, 60)) # Bounds
        
        # Calculate RSI for window w
        # Slice: delta[i-w+1 : i+1]
        
        subset = delta[i-w+1 : i+1]
        if len(subset) == 0: continue
        
        gains = subset[subset > 0]
        losses = -subset[subset < 0]
        
        avg_gain = gains.mean() if len(gains) > 0 else 0.0
        avg_loss = losses.mean() if len(losses) > 0 else 0.0
        
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
            
        rsi_out[i] = rsi
        
    return rsi_out

def run_dynamic_rsi_test():
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
    
    # 1. NATR (Volatility)
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    # 2. Base Engines (SMA & VWMA)
    print("Pre-calculating Trend Engines (SMA & VWMA)...")
    # Both use Int=140, Slope=25
    intercept = 140
    slope = 25
    
    # Needs to be dynamic length per day.
    # sma_series = [calc_ma(i) for i...]
    # vwma_series = [calc_vwma(i) for i...]
    
    sma_vals = np.zeros(len(close))
    vwma_vals = np.zeros(len(close))
    sma_vals[:] = np.nan
    vwma_vals[:] = np.nan
    
    # Pre-calc Universe for fast lookup
    # Lengths 20 to 250
    sma_universe = {}
    vwma_universe = {}
    
    pv = close * volume
    for w in range(20, 251):
        sma_universe[w] = close.rolling(window=w).mean()
        vwma_universe[w] = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
    print("Generating Strategy Signals...")
    
    dates = df.index
    prices = close.values
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    # Grid Search Parameters
    base_periods = [14, 21]
    ref_vols = [1.0, 1.5, 2.0]
    thresholds = [80, 85, 90]
    engines = ['SMA', 'VWMA']
    
    print(f"Grid: {len(base_periods)*len(ref_vols)*len(thresholds)*2} configs.")
    
    results = []
    
    # Optimization Loop
    for engine in engines:
        for base in base_periods:
            for ref in ref_vols:
                # Calculate Dynamic RSI Series for this config
                # (Takes ~1-2 sec)
                dyn_rsi = calculate_dynamic_rsi_series(close, natr, base, ref)
                
                for thresh in thresholds:
                    portfolio = [1.0]
                    current_asset = 'Cash'
                    fee = 0.002
                    
                    start_idx = 250
                    
                    for i in range(start_idx, len(dates)-1):
                        curr_natr = natrs[i]
                        curr_rsi = dyn_rsi[i]
                        price = prices[i]
                        
                        target = 'Cash'
                        
                        # Vol Filter (Fixed)
                        if not pd.isna(curr_natr) and curr_natr > 5.0:
                            target = 'Cash'
                        else:
                            # MA Logic
                            if pd.isna(curr_natr): ma_len = intercept
                            else: ma_len = int(intercept - (slope * curr_natr))
                            ma_len = max(20, min(ma_len, 250))
                            
                            if engine == 'SMA':
                                ma_val = sma_universe[ma_len].iloc[i]
                            else:
                                ma_val = vwma_universe[ma_len].iloc[i]
                                
                            if pd.isna(ma_val): target = 'Cash'
                            elif price > ma_val: # Bull
                                # RSI Check
                                if not pd.isna(curr_rsi) and curr_rsi > thresh:
                                    target = 'Cash' # Profit Take
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
                    
                    # Store Result
                    cfg_str = f"{engine} Base{base} Ref{ref} Thresh{thresh}"
                    if cagr > 0.50: # Only print notable results
                        print(f"  {cfg_str}: {cagr*100:.2f}%")
                    
                    results.append({'Config': cfg_str, 'CAGR': cagr, 'Engine': engine})
                    
    # Sort
    results.sort(key=lambda x: x['CAGR'], reverse=True)
    
    print("\n=== TOP 5 DYNAMIC RSI CONFIGS ===")
    for r in results[:5]:
        print(f"{r['Config']}: {r['CAGR']*100:.2f}%")
        
    print(f"\nBest SMA: {max([r['CAGR'] for r in results if r['Engine']=='SMA'])*100:.2f}%")
    print(f"Best VWMA: {max([r['CAGR'] for r in results if r['Engine']=='VWMA'])*100:.2f}%")

if __name__ == "__main__":
    run_dynamic_rsi_test()
