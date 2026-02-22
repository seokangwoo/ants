import yfinance as yf
import pandas as pd
import numpy as np
import ta
from itertools import product
import time

# --- Helper Functions ---
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

def calculate_fisher(high, low, window):
    # Fisher Transform (Standard logic)
    res = np.zeros(len(high))
    vals = (high + low) / 2.0
    
    # Pre-allocate
    x = np.zeros(len(high))
    for i in range(window, len(high)):
        mn = np.min(low[i-window:i])
        mx = np.max(high[i-window:i])
        if mx == mn: x[i] = 0
        else: x[i] = 0.66 * ((vals[i] - mn) / (mx - mn) - 0.5) + 0.67 * x[i-1]
        
    x = np.clip(x, -0.99, 0.99)
    fisher = 0.5 * np.log((1 + x) / (1 - x))
    return fisher

def run_simulation(close, long_rets, short_rets, vwma_lens, pv_vals, volume, filters, fee=0.002):
    p = 1.0; cur = None; rets = [0.0] * len(close)
    start_idx = 300
    
    # filters = [(indi_vals, condition_func)]
    for i in range(start_idx, len(close)-1):
        # Universal Engine Check
        w = vwma_lens[i]
        ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
        trend_price = close[i]
        
        if trend_price > ma:
            # Check all active filters
            passed = True
            for f_vals, cond_type in filters:
                val = f_vals[i]
                if pd.isna(val): continue
                
                if cond_type == 'RSI': passed = (val <= 85)
                elif cond_type == 'Stoch': passed = (val <= 0.9)
                elif cond_type == 'NATR': passed = (val <= 5.0)
                elif cond_type == 'PPO': passed = (val > 0)
                elif cond_type == 'MFI': passed = (val <= 85)
                elif cond_type == 'CMF': passed = (val > 0)
                elif cond_type == 'Fisher': passed = (val < 2.0) # Arbitrary threshold for overbought
                elif cond_type == 'Williams': passed = (val > -80) # Buy threshold
                elif cond_type == 'CCI': passed = (val < 100)
                
                if not passed: break
            
            target = 'Long' if passed else 'Cash'
        else:
            target = 'Short'
            
        if target != cur:
            p *= (1 - fee); cur = target
        p *= (1 + (long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)))
        
    years = (len(close) - start_idx) / 252
    return (p**(1/years) - 1) * 100

def god_mode():
    print("Fetching KOSPI 200 Data for GOD MODE...")
    df = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df.index.intersection(df_long.index).intersection(df_short.index)
    df = df.loc[common]; df_long = df_long.loc[common]; df_short = df_short.loc[common]
    
    close = df['Close'].values; high = df['High'].values
    low = df['Low'].values; volume = df['Volume'].values
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values
    
    # Engine
    adx = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close']).adx().values / 10.0
    vwma_lens = (0.6 * (adx**2) - 35 * adx + 170).astype(int).clip(20, 300)
    pv_vals = close * volume
    
    # Pre-calculate indicators
    lengths = [10, 14, 20]
    modes = ['Std', 'LR', 'ZL']
    indi_names = ['RSI', 'Stoch', 'NATR', 'PPO', 'MFI', 'CMF', 'Fisher', 'Williams', 'CCI']
    
    print("Pre-calculating Indicator Library...")
    lib = {} # {name: {len: {mode: values}}}
    for name in indi_names:
        lib[name] = {}
        for l in lengths:
            lib[name][l] = {}
            if name == 'RSI': base = ta.momentum.RSIIndicator(df['Close'], window=l).rsi().values
            elif name == 'Stoch': base = ta.momentum.StochRSIIndicator(df['Close'], window=l).stochrsi_k().values
            elif name == 'NATR': 
                tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
                base = (tr.rolling(l).mean() / df['Close'] * 100).values
            elif name == 'PPO': base = ta.momentum.PercentagePriceOscillator(df['Close'], window_fast=l, window_slow=l*2).ppo().values
            elif name == 'MFI': base = ta.volume.MFIIndicator(df['High'], df['Low'], df['Close'], df['Volume'], window=l).money_flow_index().values
            elif name == 'CMF': base = ta.volume.ChaikinMoneyFlowIndicator(df['High'], df['Low'], df['Close'], df['Volume'], window=l).chaikin_money_flow().values
            elif name == 'Fisher': base = calculate_fisher(high, low, l)
            elif name == 'Williams': base = ta.momentum.WilliamsRIndicator(df['High'], df['Low'], df['Close'], lbp=l).williams_r().values
            elif name == 'CCI': base = ta.trend.CCIIndicator(df['High'], df['Low'], df['Close'], window=l).cci().values
            
            lib[name][l]['Std'] = np.nan_to_num(base, nan=100.0 if name in ['RSI','MFI','CCI','Fisher'] else 0.0)
            lib[name][l]['LR'] = np.nan_to_num(get_lr_val(base, l), nan=0.0)
            lib[name][l]['ZL'] = np.nan_to_num(get_zl_val(base, l), nan=0.0)

    # Multi-Stage Simulation
    # Stage 1: Greedy selection
    active_filters = []
    # Start with NATR 20 Std as mandatory risk filter
    active_filters.append((lib['NATR'][20]['Std'], 'NATR'))
    best_cagr = run_simulation(close, long_rets, short_rets, vwma_lens, pv_vals, volume, active_filters)
    print(f"Baseline (NATR only): {best_cagr:.2f}%")
    
    used_categories = set(['NATR'])
    
    while len(used_categories) < len(indi_names):
        best_round_cagr = -999
        best_round_variant = None
        
        for name in indi_names:
            if name in used_categories: continue
            for l in lengths:
                for m in modes:
                    variant = (lib[name][l][m], name)
                    test_filters = active_filters + [variant]
                    c = run_simulation(close, long_rets, short_rets, vwma_lens, pv_vals, volume, test_filters)
                    if c > best_round_cagr:
                        best_round_cagr = c
                        best_round_variant = (variant, name, l, m)
                        
        if best_round_cagr > best_cagr:
            best_cagr = best_round_cagr
            active_filters.append(best_round_variant[0])
            used_categories.add(best_round_variant[1])
            print(f" [ADDED] {best_round_variant[1]} ({best_round_variant[2]}, {best_round_variant[3]}) -> CAGR: {best_cagr:.2f}%")
        else:
            print("No more improvements found in greedy search.")
            break
            
    print(f"\n=== GOD MODE FINAL CHAMPION ===")
    print(f"Final CAGR: {best_cagr:.2f}%")
    print("Active Components:")
    # Re-verify the champion against documented champion
    if best_cagr < 72.14:
        print("!! Note: Champion of 72.14% still holds the title. Greed search reached a local peak.")
    else:
        print("!! NEW WORLD RECORD ACHIEVED !!")

if __name__ == "__main__":
    god_mode()
