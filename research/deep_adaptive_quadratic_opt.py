import yfinance as yf
import pandas as pd
import numpy as np
import ta
from itertools import product
import time

def calculate_vhf(close, window=28):
    high_w = pd.Series(close).rolling(window).max()
    low_w = pd.Series(close).rolling(window).min()
    diff = abs(pd.Series(close).diff())
    sum_diff = diff.rolling(window).sum()
    vhf = abs(high_w - low_w) / sum_diff
    return vhf.fillna(0).values

def calculate_er(close, window=10):
    change = abs(pd.Series(close).diff(window))
    volatility = abs(pd.Series(close).diff()).rolling(window).sum()
    er = change / volatility
    return er.fillna(0).values

def run_deep_adaptive_optimization():
    print("Fetching KOSPI 200 Data for Deep Engine Optimization...")
    df = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df.index.intersection(df_long.index).intersection(df_short.index)
    df = df.loc[common]; df_long = df_long.loc[common]; df_short = df_short.loc[common]
    
    close = df['Close'].values; volume = df['Volume'].values
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values
    
    # --- Prepare Champion Framework (ZL-Stoch + RSI + NATR) ---
    natr = (ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close']).average_true_range() / df['Close'] * 100).values
    rsi = ta.momentum.RSIIndicator(df['Close']).rsi().values
    stoch_k = ta.momentum.StochRSIIndicator(df['Close'], window=10).stochrsi_k()
    # Zero-Lag Stochastic Calculation
    stoch_zl = (stoch_k + (stoch_k - stoch_k.shift(4))).values
    pv_vals = close * volume
    vol_vals = volume
    
    # --- Candidate Metrics (Normalized to 0-10) ---
    metrics = {
        'ADX': ta.trend.ADXIndicator(df['High'], df['Low'], df['Close']).adx().values / 10.0,
        'VHF': calculate_vhf(close) * 10.0, # VHF is 0-1
        'ER': calculate_er(close) * 10.0,    # ER is 0-1
    }
    # Add Absolute Momentum of Price (AMP) as another contender
    metrics['AMP'] = abs(pd.Series(close).pct_change(20)).fillna(0).values * 100.0
    
    # --- Search Space for A, B, C ---
    # Length = A*x^2 + B*x + C
    # ADX-Champ uses A=0.6, B=-35, C=170 (where ADX is /10, so range 0-6ish)
    A_list = np.arange(0.2, 1.1, 0.2)
    B_list = np.arange(-45, -20, 5)
    C_list = np.arange(130, 210, 20)
    
    total_metrics = len(metrics)
    best_overall_cagr = -999
    best_overall_setup = None
    
    start_time = time.time()
    
    print(f"Starting Exhaustive Engine Search ({total_metrics} Metrics x {len(A_list)*len(B_list)*len(C_list)} Param Combos)...")
    
    for m_name, x_vals in metrics.items():
        best_m_cagr = -999
        print(f" Testing Engine: {m_name}...")
        
        for a, b, c in product(A_list, B_list, C_list):
            p = 1.0; cur = None; fee = 0.002
            
            # Vectorized length calculation
            lengths = (a * (x_vals**2) + b * x_vals + c).astype(int).clip(20, 300)
            
            # Simulation Loop (Optimized with pre-calculated slices if possible, but rolling sums are fast)
            # For speed, we'll use a slightly optimized cumulative approach or just raw numpy
            
            for i in range(300, len(close)-1):
                if natr[i] > 5.0:
                    target = 'Cash'
                else:
                    w = lengths[i]
                    # VWMA Calculation
                    ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(vol_vals[i-w+1:i+1])
                    
                    if close[i] > ma:
                        # Profit Take Logic (Champion)
                        if rsi[i] > 85 and stoch_zl[i] > 0.9:
                            target = 'Cash'
                        else:
                            target = 'Long'
                    else:
                        target = 'Short'
                
                if target != cur:
                    p *= (1 - fee); cur = target
                p *= (1 + (long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)))
            
            years = (len(close) - 300) / 252
            cagr = (p**(1/years) - 1) * 100
            
            if cagr > best_m_cagr:
                best_m_cagr = cagr
                if cagr > best_overall_cagr:
                    best_overall_cagr = cagr
                    best_overall_setup = (m_name, a, b, c)

        print(f"  [Best {m_name}] CAGR: {best_m_cagr:.2f}%")

    end_time = time.time()
    print(f"\nOptimization Finished in {end_time - start_time:.1f}s")
    print(f"=== ABSOLUTE ENGINE CHAMPION ===")
    print(f"Metric: {best_overall_setup[0]}")
    print(f"CAGR: {best_overall_cagr:.2f}%")
    print(f"Quadratic Params: A={best_overall_setup[1]:.2f}, B={best_overall_setup[2]:.2f}, C={best_overall_setup[3]:.2f}")
    print(f"Baseline Research Peak: 72.14%")

if __name__ == "__main__":
    run_deep_adaptive_optimization()
