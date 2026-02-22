import yfinance as yf
import pandas as pd
import numpy as np
import ta
from itertools import product
import time

# --- Optimization Functions ---
def get_lr_val(arr, window):
    res = np.full(len(arr), np.nan)
    if window < 2: return res
    x = np.arange(window)
    x_sum = np.sum(x); x2_sum = np.sum(x**2)
    denom = (window * x2_sum - x_sum**2)
    for i in range(window, len(arr)):
        y = arr[i-window:i]
        y_sum = np.sum(y); xy_sum = np.sum(x * y)
        m = (window * xy_sum - x_sum * y_sum) / denom
        b = (y_sum - m * x_sum) / window
        res[i] = m * (window - 1) + b
    return res

def get_zl_val(arr, window):
    res = np.full(len(arr), np.nan)
    lag = int((window - 1) / 2)
    if lag < 1: return arr
    for i in range(lag, len(arr)):
        res[i] = arr[i] + (arr[i] - arr[i-lag])
    return res

def calculate_ema(arr, window):
    res = np.full(len(arr), np.nan)
    if len(arr) < window: return res
    alpha = 2.0 / (window + 1)
    res[window-1] = np.mean(arr[:window])
    for i in range(window, len(arr)):
        res[i] = (arr[i] - res[i-1]) * alpha + res[i-1]
    return res

def run_nuclear_optimization():
    print("Fetching KOSPI 200 Data for THE NUCLEAR BATTLE...")
    df_signal = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df_signal = df_signal.loc[common]; df_long = df_long.loc[common]; df_short = df_short.loc[common]
    
    close = df_signal['Close'].values; high = df_signal['High'].values
    low = df_signal['Low'].values; volume = df_signal['Volume'].values
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values
    
    # 1. ADX-Quadratic (Fixed Engine Framework)
    adx_obj = ta.trend.ADXIndicator(df_signal['High'], df_signal['Low'], df_signal['Close'])
    adx = adx_obj.adx().values / 10.0
    A, B, C = 0.6, -35, 170
    dyn_lens = (A * (adx**2) + B * adx + C).astype(int).clip(20, 300)
    
    # 2. Indicator Search Space
    lengths = [10, 20] # reduced to keep search space sane
    indi_types = ['RSI', 'Stoch', 'NATR', 'PPO']
    modes = ['None', 'Std', 'LR', 'ZL']
    
    print("Pre-calculating Matrix Components...")
    matrix = {} # {indi: {len: {mode: values}}}
    
    for indi in indi_types:
        matrix[indi] = {}
        for l in lengths:
            matrix[indi][l] = {'None': np.full(len(close), -999.0)} # Using -999 for inactive
            
            if indi == 'RSI':
                base = ta.momentum.RSIIndicator(df_signal['Close'], window=l).rsi().fillna(50).values
            elif indi == 'Stoch':
                base = ta.momentum.StochRSIIndicator(df_signal['Close'], window=l).stochrsi_k().fillna(0.5).values
            elif indi == 'NATR':
                tr = pd.concat([df_signal['High']-df_signal['Low'], 
                               abs(df_signal['High']-df_signal['Close'].shift(1)), 
                               abs(df_signal['Low']-df_signal['Close'].shift(1))], axis=1).max(axis=1)
                atr = tr.rolling(window=l).mean()
                base = (atr / df_signal['Close'] * 100).fillna(2.0).values
            elif indi == 'PPO':
                # PPO is slow-fast 26-12 usually. We vary 'fast' based on 'l'
                ppo_obj = ta.momentum.PercentagePriceOscillator(df_signal['Close'], window_fast=l, window_slow=l*2, window_sign=9)
                base = ppo_obj.ppo().fillna(0).values
            
            matrix[indi][l]['Std'] = base
            matrix[indi][l]['LR'] = get_lr_val(base, l)
            matrix[indi][l]['ZL'] = get_zl_val(base, l)

    # 3. Engines: [VWMA, LR, ZL-VWMA, EMA, ZL-EMA]
    engines = ['VWMA', 'LR', 'ZL-VWMA', 'EMA', 'ZL-EMA']
    pv_vals = close * volume
    zl_close = get_zl_val(close, 20)
    zl_pv = zl_close * volume

    # Optimization: Pre-calculate EMA and ZL-EMA
    ema_20_250 = {} # pre-calc for common dynamic lengths is hard, but we can do it on the fly with a fast function
    
    indicator_combos = list(product(lengths, modes, lengths, modes, lengths, modes, lengths, modes))
    total_variants = len(engines) * len(indicator_combos)
    print(f"Starting The Nuclear Battle Royale ({total_variants} combinations)...")
    
    best_cagr = -999; best_params = None
    start_time = time.time()
    
    # Simulation Loop
    for eng in engines:
        for rl, rm, sl, sm, nl, nm, pl, pm in indicator_combos:
            r_v = matrix['RSI'][rl][rm]
            s_v = matrix['Stoch'][sl][sm]
            n_v = matrix['NATR'][nl][nm]
            p_v = matrix['PPO'][pl][pm]
            
            p = 1.0; cur = None; fee = 0.002
            
            for i in range(300, len(close)-1):
                # NATR Filter (Universal Risk)
                if nm != 'None' and n_v[i] > 5.0:
                    target = 'Cash'
                else:
                    # Engine Logic
                    w = dyn_lens[i]
                    if eng == 'VWMA':
                        ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
                        t_p = close[i]
                    elif eng == 'LR':
                        # Fast LR Forecast Approximation
                        y = close[i-w:i]
                        m, b = np.polyfit(np.arange(w), y, 1)
                        ma = m * (w-1) + b
                        t_p = close[i]
                    elif eng == 'ZL-VWMA':
                        ma = np.sum(zl_pv[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
                        t_p = close[i]
                    elif eng == 'EMA':
                        # Simple EMA approximation for the point
                        ma = np.mean(close[i-w:i]) # baseline approx for speed
                        t_p = close[i]
                    elif eng == 'ZL-EMA':
                        ma = np.mean(close[i-w:i])
                        t_p = zl_close[i]
                    
                    if t_p > ma:
                        # Indicator Checks
                        r_ok = (rm == 'None' or r_v[i] <= 85)
                        s_ok = (sm == 'None' or s_v[i] <= 0.9)
                        # PPO helps trend (PPO > 0 implies bullish)
                        p_ok = (pm == 'None' or p_v[i] > 0)
                        
                        if r_ok and s_ok and p_ok: target = 'Long'
                        else: target = 'Cash'
                    else:
                        target = 'Short'
                
                if target != cur:
                    p *= (1 - fee); cur = target
                p *= (1 + (long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)))
            
            years = (len(close) - 300) / 252
            cagr = (p**(1/years) - 1) * 100
            if cagr > best_cagr:
                best_cagr = cagr
                best_params = (eng, rl, rm, sl, sm, nl, nm, pl, pm)
                print(f" [NEW BEST] {best_cagr:.2f}% ({eng}, R:{rl}{rm}, S:{sl}{sm}, N:{nl}{nm}, P:{pl}{pm})")

    end_time = time.time()
    print(f"\nOptimization Finished in {end_time - start_time:.1f}s")
    print(f"=== THE NUCLEAR CHAMPION ===")
    print(f"CAGR: {best_cagr:.2f}%")
    print(f"Engine: {best_params[0]}")
    print(f"RSI: {best_params[1]} {best_params[2]}")
    print(f"Stoch: {best_params[3]} {best_params[4]}")
    print(f"NATR: {best_params[5]} {best_params[6]}")
    print(f"PPO: {best_params[7]} {best_params[8]}")

if __name__ == "__main__":
    run_nuclear_optimization()
