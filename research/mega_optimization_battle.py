import yfinance as yf
import pandas as pd
import numpy as np
import ta
from itertools import product
import time

def get_lr_val(arr, window):
    # Returns LR forecast for each point
    res = np.full(len(arr), np.nan)
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
    # Returns Zero-Lag adjusted values
    # ZL = Price + (Price - Price[lag]) where lag = (window-1)/2
    res = np.full(len(arr), np.nan)
    lag = int((window - 1) / 2)
    for i in range(lag, len(arr)):
        res[i] = arr[i] + (arr[i] - arr[i-lag])
    return res

def run_mega_battle():
    print("Fetching KOSPI 200 Data for THE MEGA BATTLE...")
    df_signal = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df_signal = df_signal.loc[common]; df_long = df_long.loc[common]; df_short = df_short.loc[common]
    
    close_vals = df_signal['Close'].values
    high_vals = df_signal['High'].values
    low_vals = df_signal['Low'].values
    vol_vals = df_signal['Volume'].values
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values
    
    # ADX-Quadratic (Champion coefficients)
    adx_obj = ta.trend.ADXIndicator(df_signal['High'], df_signal['Low'], df_signal['Close'])
    adx = (adx_obj.adx().values / 10.0)
    A, B, C = 0.6, -35, 170
    vwma_lens = (A * (adx**2) + B * adx + C).astype(int).clip(20, 300)
    
    # PRE-CALCULATION MATRIX
    lengths = [10, 14, 20]
    modes = ['Std', 'LR', 'ZL']
    
    print("Pre-calculating Matrix Components...")
    # Indicator Cache: {name: {len: {mode: values}}}
    cache = {'RSI': {}, 'Stoch': {}, 'NATR': {}}
    
    for l in lengths:
        # RSI
        r_std = ta.momentum.RSIIndicator(df_signal['Close'], window=l).rsi().fillna(50).values
        cache['RSI'][l] = {'Std': r_std, 'LR': get_lr_val(r_std, l), 'ZL': get_zl_val(r_std, l)}
        
        # Stoch (Raw K)
        s_std = ta.momentum.StochRSIIndicator(df_signal['Close'], window=l).stochrsi_k().fillna(0.5).values
        cache['Stoch'][l] = {'Std': s_std, 'LR': get_lr_val(s_std, l), 'ZL': get_zl_val(s_std, l)}
        
        # NATR
        tr = pd.concat([df_signal['High']-df_signal['Low'], 
                       abs(df_signal['High']-df_signal['Close'].shift(1)), 
                       abs(df_signal['Low']-df_signal['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(window=l).mean()
        n_std = (atr / df_signal['Close'] * 100).fillna(2.0).values
        cache['NATR'][l] = {'Std': n_std, 'LR': get_lr_val(n_std, l), 'ZL': get_zl_val(n_std, l)}

    # Engine Matrix: [Standard-VWMA, LR-Engine, ZL-VWMA, ZL-LR]
    engines = ['VWMA-Std', 'LR-Engine', 'ZL-VWMA', 'ZL-LR']
    
    # Prepared data for engines
    pv_vals = close_vals * vol_vals
    zl_close = get_zl_val(close_vals, 20) # Lag for ZL
    zl_pv = zl_close * vol_vals

    best_cagr = -999; best_params = None
    
    # COMBINATIONS: Engine * RSI(L*M) * Stoch(L*M) * NATR(L*M) 
    # That is too many. Let's fix Indicator lengths to 14 to survive.
    # User said: "All combinations including lengths". Let's try to optimize the loop.
    
    indicator_combos = list(product(lengths, modes, lengths, modes, lengths, modes))
    total_engine_combos = len(engines) * len(indicator_combos)
    print(f"Starting The Ultimate Battle Royale ({total_engine_combos} combinations)...")
    
    start_time = time.time()
    
    # Faster Simulation Loop
    for eng in engines:
        for rl, rm, sl, sm, nl, nm in indicator_combos:
            r_v = cache['RSI'][rl][rm]
            s_v = cache['Stoch'][sl][sm]
            n_v = cache['NATR'][nl][nm]
            
            p = 1.0; cur = None; fee = 0.002
            
            for i in range(300, len(close_vals)-1):
                # 1. NATR Filter
                if n_v[i] > 5.0 or np.isnan(n_v[i]):
                    target = 'Cash'
                else:
                    # 2. Engine Logic
                    w = vwma_lens[i]
                    if eng == 'VWMA-Std':
                        ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(vol_vals[i-w+1:i+1])
                        trend_price = close_vals[i]
                    elif eng == 'LR-Engine':
                        # Use LR Forecast as MA equivalent or price?
                        # Let's say: Trend is Long if Price > LR_Forecast
                        y = close_vals[i-w:i]
                        x = np.arange(w)
                        m, b = np.polyfit(x, y, 1)
                        ma = m * (w-1) + b
                        trend_price = close_vals[i]
                    elif eng == 'ZL-VWMA':
                        # VWMA of ZL-Adjusted Price
                        ma = np.sum(zl_pv[i-w+1:i+1]) / np.sum(vol_vals[i-w+1:i+1])
                        trend_price = close_vals[i]
                    elif eng == 'ZL-LR':
                        # LR Forecast of ZL-Adjusted Price? Or ZL-Price > LR_Forecast?
                        # Let's define as: ZL-Adjusted Price > LR_Forecast of Standard Price
                        y = close_vals[i-w:i]
                        x = np.arange(w)
                        m, b = np.polyfit(x, y, 1)
                        ma = m * (w-1) + b
                        trend_price = zl_close[i]
                    
                    if trend_price > ma:
                        # 3. RSI/Stoch Check
                        if r_v[i] > 85 and s_v[i] > 0.9: target = 'Cash'
                        else: target = 'Long'
                    else:
                        target = 'Short'
            
                if target != cur:
                    p *= (1 - fee); cur = target
                ret = long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)
                p *= (1 + ret)
            
            years = (len(close_vals) - 300) / 252 # Approx
            cagr = (p**(1/years) - 1) * 100
            if cagr > best_cagr:
                best_cagr = cagr
                best_params = (eng, rl, rm, sl, sm, nl, nm)
                print(f" New Best: {best_cagr:.2f}% ({eng}, RSI:{rl}{rm}, Stoch:{sl}{sm}, NATR:{nl}{nm})")

    end_time = time.time()
    print(f"\nMega Battle Finished in {end_time - start_time:.1f}s")
    print(f"=== GLOBAL CHAMPION ===")
    print(f"CAGR: {best_cagr:.2f}%")
    print(f"Engine: {best_params[0]}")
    print(f"Indicators: RSI({best_params[1]}{best_params[2]}), Stoch({best_params[3]}{best_params[4]}), NATR({best_params[5]}{best_params[6]})")
    print(f"Previous Champion: 67.22%")

if __name__ == "__main__":
    run_mega_battle()
