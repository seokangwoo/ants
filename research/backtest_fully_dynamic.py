import yfinance as yf
import pandas as pd
import numpy as np

def calculate_dynamic_wilder_rsi(series, natr, base_period=14, ref_vol=2.0):
    # RSI with dynamic period.
    # We must loop because Wilder's Smoothing depends on previous value,
    # and the Alpha (1/Period) changes every step.
    
    vals = series.values
    natrs = natr.values
    rsi_out = np.zeros(len(vals))
    rsi_out[:] = np.nan
    
    # Initialize
    avg_gain = 0.0
    avg_loss = 0.0
    
    # Warmup with base period
    # To be precise, we just start loop.
    
    for i in range(1, len(vals)):
        # Determine Period
        curr_natr = natrs[i]
        if pd.isna(curr_natr) or curr_natr == 0:
            period = base_period
        else:
            # Inverse Relationship: Higher Vol -> Lower Period (Faster)
            period = int(base_period * (ref_vol / curr_natr))
            
        period = max(4, min(period, 60))
        alpha = 1.0 / period
        
        change = vals[i] - vals[i-1]
        
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        
        if i == 1:
            avg_gain = gain
            avg_loss = loss
        else:
            avg_gain = (avg_gain * (1 - alpha)) + (gain * alpha)
            avg_loss = (avg_loss * (1 - alpha)) + (loss * alpha)
            
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
            
        rsi_out[i] = rsi
        
    return rsi_out

def calculate_dynamic_stoch_rsi(rsi_series, natr, base_period=14, ref_vol=2.0):
    # StochRSI = (RSI - MinRSI) / (MaxRSI - MinRSI)
    # Window for Min/Max is also Dynamic!
    
    stoch_k_out = np.zeros(len(rsi_series))
    stoch_k_out[:] = np.nan
    
    natrs = natr.values
    
    # We need a history buffer for Min/Max
    # But window size changes.
    # Vectorized Rolling with variable window is hard.
    # Loop again.
    
    for i in range(len(rsi_series)):
        curr_natr = natrs[i]
        if pd.isna(curr_natr) or curr_natr == 0:
            period = base_period
        else:
            period = int(base_period * (ref_vol / curr_natr))
        
        period = max(4, min(period, 60))
        
        if i < period: continue
        
        # Slice RSI history
        # rsi_series is np array
        window = rsi_series[i-period+1 : i+1]
        
        min_val = np.min(window)
        max_val = np.max(window)
        
        current_val = rsi_series[i]
        
        if max_val == min_val:
            stoch = 0.5 # Default?
        else:
            stoch = (current_val - min_val) / (max_val - min_val)
            
        stoch_k_out[i] = stoch
        
    # Smooth K? Usually 3. Fixed or Dynamic? 
    # User said "ALL indicators dynamic". 
    # But 3 is smoothing. Let's keep smooth-K static (3) or it gets too noisy.
    # Actually, Pandas rolling mean is fast.
    
    s_series = pd.Series(stoch_k_out)
    k_series = s_series.rolling(3).mean()
    
    return k_series.values

def run_fully_dynamic():
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
    
    # NATR
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    prices = close.values
    dates = df.index
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    # VWMA Universe (Base Engine)
    # Still Dynamic.
    vwmas = {}
    pv = close * volume
    for w in range(20, 251):
        vwmas[w] = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
    updated_ma_len = 140 - (25 * natr)
    updated_ma_len = updated_ma_len.fillna(140).astype(int).clip(20, 250)
    
    # Grid Search for Dynamic Indicators
    # Ref Vol: [1.5, 2.0, 2.5]
    # RSI Limit: [80, 85, 90]
    # Stoch Limit: [0.8, 0.9]
    
    ref_vols = [1.5, 2.0, 2.5]
    
    print("Optimization Loop...")
    
    results = []
    
    for ref_vol in ref_vols:
        # Calculate Indicators ONCE per RefVol (Expensive)
        print(f"  Calculating Dynamic Indicators (RefVol={ref_vol})...")
        dyn_rsi = calculate_dynamic_wilder_rsi(close, natr, base_period=14, ref_vol=ref_vol)
        dyn_stoch_k = calculate_dynamic_stoch_rsi(dyn_rsi, natr, base_period=14, ref_vol=ref_vol)
        
        for rsi_lim in [85, 90]:
            for stoch_lim in [0.8]:
                
                portfolio = [1.0]
                current_asset = 'Cash'
                fee = 0.002
                start_idx = 250
                
                for i in range(start_idx, len(dates)-1):
                    # Logic
                    curr_natr = natrs[i]
                    if pd.isna(curr_natr) or curr_natr > 5.0:
                        target = 'Cash'
                    else:
                        ma_len = int(updated_ma_len.iloc[i])
                        ma_val = vwmas[ma_len].iloc[i]
                        
                        price = prices[i]
                        
                        if pd.isna(ma_val): target = 'Cash'
                        elif price > ma_val: # Bull
                            # Dynamic Exit?
                            d_rsi = dyn_rsi[i]
                            d_stoch = dyn_stoch_k[i]
                            
                            if (d_rsi > rsi_lim) and (d_stoch > stoch_lim):
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
                
                results.append({'Ref': ref_vol, 'Lim': rsi_lim, 'CAGR': cagr})
                print(f"    Ref{ref_vol} RSI{rsi_lim}: {cagr*100:.2f}%")
                
    results.sort(key=lambda x: x['CAGR'], reverse=True)
    print("\n=== FULLY DYNAMIC RESULTS ===")
    print(f"Best: Ref{results[0]['Ref']} RSI{results[0]['Lim']} => {results[0]['CAGR']*100:.2f}%")

if __name__ == "__main__":
    run_fully_dynamic()
