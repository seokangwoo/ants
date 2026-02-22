import yfinance as yf
import pandas as pd
import numpy as np
import ta
from itertools import product
import time

def get_lr_slope_and_forecast(series, window):
    # Optimized rolling linear regression
    # Using numpy as it is faster for large loops
    arr = series.values
    slopes = np.full(len(arr), np.nan)
    forecasts = np.full(len(arr), np.nan)
    x = np.arange(window)
    
    # Pre-calculate sums for polyfit speedup
    x_sum = np.sum(x)
    x2_sum = np.sum(x**2)
    denom = (window * x2_sum - x_sum**2)
    
    for i in range(window, len(arr)):
        y = arr[i-window:i]
        y_sum = np.sum(y)
        xy_sum = np.sum(x * y)
        m = (window * xy_sum - x_sum * y_sum) / denom
        b = (y_sum - m * x_sum) / window
        slopes[i] = m
        forecasts[i] = m * (window - 1) + b
    return slopes, forecasts

def run_deep_optimization():
    print("Fetching KOSPI 200 Data...")
    df_signal = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df_signal = df_signal.loc[common]; df_long = df_long.loc[common]; df_short = df_short.loc[common]
    
    close = df_signal['Close']; high = df_signal['High']; low = df_signal['Low']; volume = df_signal['Volume']
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values
    
    # 67.22% Champion Base Engine
    adx = ta.trend.ADXIndicator(high, low, close).adx().values / 10.0
    A, B, C = 0.6, -35, 170
    vwma_lengths = (A * (adx**2) + B * adx + C).astype(int).clip(20, 300)
    
    # Pre-calculate necessary VWMA series for all possibly used lengths (optional, but complicates)
    # Instead, we will slice on the fly but optimize it.
    pv_vals = (close * volume).values
    vol_vals = volume.values
    close_vals = close.values
    
    # GRID PARAMS
    rsi_lens = [10, 14, 20]
    stoch_lens = [10, 14, 20]
    natr_lens = [15, 20, 25]
    modes = [0, 1, 2] # 0=Std, 1=Slope, 2=Forecast
    
    # combinations = list(product(rsi_lens, stoch_lens, natr_lens, modes, modes, modes))
    # Too many? 3*3*3 * 3*3*3 = 27 * 27 = 729. 
    # Let's run it.
    
    best_cagr = -999; best_params = None
    
    # Pre-calculate indicator variants for each length to save time
    print("Pre-calculating Indicators...")
    rsi_cache = {}; stoch_cache = {}; natr_cache = {}
    
    for l in rsi_lens:
        r = ta.momentum.RSIIndicator(close, window=l).rsi().fillna(50)
        s, f = get_lr_slope_and_forecast(r, window=l)
        rsi_cache[l] = (r.values, s, f)
    
    for l in stoch_lens:
        s_raw = ta.momentum.StochRSIIndicator(close, window=l).stochrsi_k().fillna(0.5)
        s, f = get_lr_slope_and_forecast(s_raw, window=l)
        stoch_cache[l] = (s_raw.values, s, f)
        
    for l in natr_lens:
        tr = pd.concat([high-low, abs(high-close.shift(1)), abs(low-close.shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(window=l).mean()
        n = (atr / close * 100).fillna(2.0)
        s, f = get_lr_slope_and_forecast(n, window=l)
        natr_cache[l] = (n.values, s, f)

    combos = list(product(rsi_lens, stoch_lens, natr_lens, modes, modes, modes))
    total = len(combos)
    print(f"Starting Deep Grid Search ({total} combinations)...")
    
    start_time = time.time()
    for idx, (rl, sl, nl, rm, sm, nm) in enumerate(combos):
        r_vals, r_slope, r_fc = rsi_cache[rl]
        s_vals, s_slope, s_fc = stoch_cache[sl]
        n_vals, n_slope, n_fc = natr_cache[nl]
        
        portfolio = 1.0; current = None; fee = 0.002
        
        # Performance optimization: use local variables
        for i in range(250, len(close_vals)-1):
            # 1. NATR
            is_risk_on = True
            nv = n_vals[i]
            if nm == 0: is_risk_on = (nv <= 5.0)
            elif nm == 1: is_risk_on = (n_slope[i] <= 0)
            elif nm == 2: is_risk_on = (nv <= n_fc[i])
            
            if not is_risk_on:
                target = 'Cash'
            else:
                w = vwma_lengths[i]
                ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(vol_vals[i-w+1:i+1])
                
                if close_vals[i] > ma:
                    # Profit Take
                    r_over = False; rv = r_vals[i]
                    if rm == 0: r_over = (rv > 85)
                    elif rm == 1: r_over = (r_slope[i] > 0 and rv > 70)
                    elif rm == 2: r_over = (rv > r_fc[i] and rv > 70)
                    
                    s_over = False; sv = s_vals[i]
                    if sm == 0: s_over = (sv > 0.9)
                    elif sm == 1: s_over = (s_slope[i] > 0 and sv > 0.8)
                    elif sm == 2: s_over = (sv > s_fc[i] and sv > 0.8)
                    
                    if r_over and s_over: target = 'Cash'
                    else: target = 'Long'
                else:
                    target = 'Short'
            
            if target != current:
                portfolio *= (1 - fee)
                current = target
            
            ret = long_rets[i+1] if current == 'Long' else (short_rets[i+1] if current == 'Short' else 0.0)
            portfolio *= (1 + ret)
            
        years = (df_signal.index[-1] - df_signal.index[250]).days / 365.25
        cagr = (portfolio**(1/years) - 1) * 100
        
        if cagr > best_cagr:
            best_cagr = cagr
            best_params = (rl, sl, nl, rm, sm, nm)
            
        if (idx+1) % 100 == 0:
            print(f" Progress: {idx+1}/{total} (Best: {best_cagr:.2f}%)")

    end_time = time.time()
    print(f"\nOptimization Finished in {end_time - start_time:.1f}s")
    print(f"=== Best Result ===")
    print(f"CAGR: {best_cagr:.2f}%")
    print(f"Params: RSI(Len={best_params[0]}, Mode={best_params[3]}), Stoch(Len={best_params[1]}, Mode={best_params[4]}), NATR(Len={best_params[2]}, Mode={best_params[5]})")
    print(f"Champion CAGR: 67.22%")

if __name__ == "__main__":
    run_deep_optimization()
