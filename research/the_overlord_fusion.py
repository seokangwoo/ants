import yfinance as yf
import pandas as pd
import numpy as np
import ta
from itertools import product
import time

# --- Helper Functions ---
def calculate_yang_zhang(open_p, high, low, close, window=20):
    log_ho = np.log(high / open_p); log_lo = np.log(low / open_p)
    log_co = np.log(close / open_p)
    log_oc = pd.Series(np.log(open_p / pd.Series(close).shift(1)))
    overnight_vol = log_oc.rolling(window).var()
    open_to_close_vol = pd.Series(log_co).rolling(window).var()
    rs_vol = pd.Series(log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)).rolling(window).mean()
    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    sigma2 = overnight_vol + k * open_to_close_vol + (1 - k) * rs_vol
    return np.sqrt(sigma2).fillna(0).values * 100.0

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

def run_overlord_fusion():
    print("=== OPERATION: OVERLORD PHASE 2 (Master Fusion) ===")
    df = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    for d in [df, df_long, df_short]:
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
    common = df.index.intersection(df_long.index).intersection(df_short.index)
    df = df.loc[common]; df_long = df_long.loc[common]; df_short = df_short.loc[common]
    
    close = df['Close'].values; high = df['High'].values; low = df['Low'].values
    open_p = df['Open'].values; volume = df['Volume'].values
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values

    # 1. Multi-Volatility Logic
    vol_natr = (ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close']).average_true_range() / df['Close'] * 100).values
    vol_park = calculate_parkinson(high, low, 20)
    vol_yz = calculate_yang_zhang(open_p, high, low, close, 20)
    
    # 2. Momentum Logic
    rsi = ta.momentum.RSIIndicator(df['Close']).rsi().values / 100.0
    st_k = ta.momentum.StochRSIIndicator(df['Close'], window=10).stochrsi_k()
    stoch_zl = (st_k + (st_k - st_k.shift(4))).values
    fisher = calculate_fisher(high, low, 10); fisher_norm = (fisher - np.min(fisher)) / (np.max(fisher) - np.min(fisher))
    
    # 3. Engine
    adx_obj = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'])
    adx = adx_obj.adx().values / 10.0
    engine_lens = (0.6 * (adx**2) - 35 * adx + 170).astype(int).clip(20, 300)
    pv_vals = close * volume
    
    # Grid Search: [Vol_Logic] x [Mom_Threshold]
    # Vol Logic 0: Single (NATR), 1: Multi-Voting (2 out of 3), 2: Multi-Strict (Any)
    vol_logics = [0, 1, 2]
    mom_weights = [(0.5, 0.5, 0), (0.4, 0.4, 0.2), (0.33, 0.33, 0.33)] # [ZL, RSI, Fisher]
    
    best_cagr = -999; best_setup = None
    
    print("Simulating Fusion Matrices...")
    for v_logic, m_w in product(vol_logics, mom_weights):
        p = 1.0; cur = None; fee = 0.002
        for i in range(300, len(close)-1):
            # Volatility Guard
            v1 = (vol_natr[i] > 5.0)
            v2 = (vol_park[i] > 2.5)
            v3 = (vol_yz[i] > 1.5)
            
            if v_logic == 0: danger = v1
            elif v_logic == 1: danger = ((v1 and v2) or (v2 and v3) or (v1 and v3))
            elif v_logic == 2: danger = (v1 or v2 or v3)
            
            if danger:
                target = 'Cash'
            else:
                w = engine_lens[i]; ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
                if close[i] > ma:
                    # Momentum Fusion Score
                    score = m_w[0]*stoch_zl[i] + m_w[1]*rsi[i] + m_w[2]*fisher_norm[i]
                    target = 'Cash' if score > 0.88 else 'Long'
                else:
                    target = 'Short'
            
            if target != cur: p *= (1 - fee); cur = target
            p *= (1 + (long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)))
            
        years = (len(close)-300)/252; cagr = (p**(1/years)-1)*100
        if cagr > best_cagr:
            best_cagr = cagr
            best_setup = (v_logic, m_w)
            print(f" [NEW BEST] {cagr:.2f}% (V:{v_logic}, M:{m_w})")

    print(f"\n=== OVERLORD MASTER FUSION RESULT ===")
    print(f"Top CAGR: {best_cagr:.2f}%")
    print(f"Vol Logic: {best_setup[0]} (0:Std, 1:Voting, 2:Strict)")
    print(f"Mom Weights: {best_setup[1]}")
    print(f"Baseline: 72.14%")

if __name__ == "__main__":
    run_overlord_fusion()
