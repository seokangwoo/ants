import yfinance as yf
import pandas as pd
import numpy as np
import ta
from itertools import product
import time

# --- High-Precision Statistical Helpers ---
def calculate_parkinson(high, low, window=20):
    sq_ln_hl = pd.Series(np.log(high / low)**2)
    park = np.sqrt(sq_ln_hl.rolling(window).mean() / (4 * np.log(2)))
    return park.fillna(0).values * 100.0

def calculate_fisher(high, low, window=10):
    res = np.zeros(len(high)); vals = (high + low) / 2.0; x = np.zeros(len(high))
    for i in range(window, len(high)):
        mn = np.min(low[i-window:i]); mx = np.max(high[i-window:i])
        if mx == mn: x[i] = 0
        else: x[i] = 0.66 * ((vals[i] - mn) / (mx - mn) - 0.5) + 0.67 * x[i-1]
    x = np.clip(x, -0.99, 0.99); fisher = 0.5 * np.log((1 + x) / (1 - x))
    return fisher

def run_final_revelation():
    print("=== OPERATION: OVERLORD (The Final Revelation) ===")
    df = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    for d in [df, df_long, df_short]:
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
    common = df.index.intersection(df_long.index).intersection(df_short.index)
    df = df.loc[common]; df_long = df_long.loc[common]; df_short = df_short.loc[common]
    
    close = df['Close'].values; high = df['High'].values; low = df['Low'].values
    volume = df['Volume'].values
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values

    # --- Pre-calculate Best-of-Best Indicators ---
    print("Synthesizing Ultimate Signal Set...")
    vol_park = calculate_parkinson(high, low, 20)
    rsi = ta.momentum.RSIIndicator(df['Close']).rsi().fillna(50).values
    st_obj = ta.momentum.StochRSIIndicator(df['Close'], window=10)
    st_k = st_obj.stochrsi_k().fillna(0.5); stoch_zl = (st_k + (st_k - st_k.shift(4))).fillna(0.5).values
    fisher = calculate_fisher(high, low, 10)
    adx = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close']).adx().fillna(20).values / 10.0
    
    # 1. Engines: ADX-Quadratic VWMA
    engine_lens = (0.6 * (adx**2) - 35 * adx + 170).astype(int).clip(20, 300)
    pv_vals = close * volume
    pv_zl = ((pd.Series(close) + (pd.Series(close) - pd.Series(close).shift(10))).fillna(pd.Series(close))).values * volume # Pseudo-ZL PV
    
    best_cagr = -999; best_setup = None

    # Search Space: [Dynamic_ThresholdING] x [Engine_Type]
    print("Initiating Global Search...")
    # Dynamic Thresholding: RSI_Limit = Basis - (Vol * K)
    # Engine Types: 0: VWMA, 1: Dual (VWMA & ZL-VWMA consensus)
    
    for k_val in [0, 2, 4]: # k=0 is static
        for eng_type in [0, 1]:
            p = 1.0; cur = None; fee = 0.002
            for i in range(300, len(close)-1):
                # Volatility Guard
                if vol_park[i] > 2.5: target = 'Cash'
                else:
                    w = engine_lens[i]
                    # Engine
                    ma1 = np.sum(pv_vals[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
                    if eng_type == 1:
                        ma2 = np.sum(pv_zl[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
                        bullish = (close[i] > ma1 and close[i] > ma2)
                    else:
                        bullish = (close[i] > ma1)
                    
                    if bullish:
                        # Dynamic Momentum Thresholding
                        rsi_limit = 95 - (vol_park[i] * k_val)
                        stoch_limit = 0.95 - (vol_park[i] * k_val / 100)
                        
                        overheated = (rsi[i] > rsi_limit and stoch_zl[i] > stoch_limit)
                        target = 'Cash' if overheated else 'Long'
                    else:
                        target = 'Short'
                
                if target != cur: p *= (1 - fee); cur = target
                p *= (1 + (long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)))
            
            years = (len(close)-300)/252; cagr = (p**(1/years)-1)*100
            if cagr > best_cagr:
                best_cagr = cagr
                best_setup = (k_val, eng_type)
                print(f" [NEW BEST] {cagr:.2f}% (K:{k_val}, Engine:{eng_type})")

    print(f"\n=== OVERLORD FINAL REVELATION RESULT ===")
    print(f"Top CAGR: {best_cagr:.2f}%")
    print(f"Vol-Dynamic K: {best_setup[0]}")
    print(f"Engine consensus: {best_setup[1]}")
    print(f"Baseline: 72.14% (Re-Targeting...)")

if __name__ == "__main__":
    run_final_revelation()
