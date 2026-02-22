import yfinance as yf
import pandas as pd
import numpy as np
import ta
from itertools import product
import time

def get_zl_val(arr, window):
    res = np.full(len(arr), np.nan)
    lag = int((window - 1) / 2)
    for i in range(lag, len(arr)):
        res[i] = arr[i] + (arr[i] - arr[i-lag])
    return res

def run_ppo_optimization():
    print("Fetching KOSPI 200 Data for PPO Fusion...")
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
    
    # 72.14% Champion Engine Base
    adx_obj = ta.trend.ADXIndicator(df_signal['High'], df_signal['Low'], df_signal['Close'])
    adx = adx_obj.adx().values / 10.0
    A, B, C = 0.6, -35, 170
    vwma_lens = (A * (adx**2) + B * adx + C).astype(int).clip(20, 300)
    pv_vals = close_vals * vol_vals
    
    # NATR (Standard 20)
    tr = pd.concat([df_signal['High']-df_signal['Low'], 
                   abs(df_signal['High']-df_signal['Close'].shift(1)), 
                   abs(df_signal['Low']-df_signal['Close'].shift(1))], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natrs = (atr / df_signal['Close'] * 100).fillna(2.0).values
    
    # RSI (Standard 14)
    rsi_vals = ta.momentum.RSIIndicator(df_signal['Close'], window=14).rsi().fillna(50).values
    
    # Stoch (Zero-Lag 10) - The Current Success Point
    stoch_src = ta.momentum.StochRSIIndicator(df_signal['Close'], window=10).stochrsi_k().fillna(0.5).values
    stoch_zl = get_zl_val(stoch_src, 10)
    
    # PPO Calculation
    # PPO(fast, slow, signal)
    print("Calculating PPO Variants...")
    ppo_obj = ta.momentum.PercentagePriceOscillator(df_signal['Close'], window_slow=26, window_fast=12, window_sign=9)
    ppo = ppo_obj.ppo().fillna(0).values
    ppo_sig = ppo_obj.ppo_signal().fillna(0).values
    ppo_hist = ppo_obj.ppo_hist().fillna(0).values
    
    # Optimization Params
    # 1. PPO > 0 (Trend Confirmation)
    # 2. PPO > Signal (Momentum Confirmation)
    # 3. PPO Histogram > 0 (Acceleration)
    ppo_modes = ['None', 'PPO>0', 'PPO>Sig', 'Hist>0']
    
    best_cagr = -999; best_ppo_mode = None
    
    print("Starting PPO Fusion Test...")
    for mode in ppo_modes:
        p = 1.0; cur = None; fee = 0.002
        for i in range(300, len(close_vals)-1):
            if natrs[i] > 5.0: target = 'Cash'
            else:
                w = vwma_lens[i]
                ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(vol_vals[i-w+1:i+1])
                
                # Base Signal
                if close_vals[i] > ma:
                    # Profit Take Check (Default 72% Logic)
                    if rsi_vals[i] > 85 and (stoch_zl[i] > 0.9 or np.isnan(stoch_zl[i])):
                        target = 'Cash'
                    else:
                        # PPO Integration
                        ppo_ok = True
                        if mode == 'PPO>0': ppo_ok = (ppo[i] > 0)
                        elif mode == 'PPO>Sig': ppo_ok = (ppo[i] > ppo_sig[i])
                        elif mode == 'Hist>0': ppo_ok = (ppo_hist[i] > 0)
                        
                        target = 'Long' if ppo_ok else 'Cash'
                else:
                    target = 'Short'
            
            if target != cur:
                p *= (1 - fee); cur = target
            p *= (1 + (long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)))
            
        years = (len(close_vals) - 300) / 252
        cagr = (p**(1/years) - 1) * 100
        if cagr > best_cagr:
            best_cagr = cagr; best_ppo_mode = mode
            
    print(f"\n=== PPO Fusion Results ===")
    print(f"Best PPO Mode: {best_ppo_mode}")
    print(f"Best CAGR: {best_cagr:.2f}%")
    print(f"Current Champion (No PPO): 72.14%")

if __name__ == "__main__":
    run_ppo_optimization()
