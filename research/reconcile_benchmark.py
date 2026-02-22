import yfinance as yf
import pandas as pd
import numpy as np
import ta
import time

def get_zl_val(arr, window):
    res = np.full(len(arr), np.nan)
    lag = int((window - 1) / 2)
    for i in range(lag, len(arr)):
        res[i] = arr[i] + (arr[i] - arr[i-lag])
    return res

def run_pure_strategy(df_signal, df_long, df_short, start_idx=300):
    close = df_signal['Close'].values; high = df_signal['High'].values
    low = df_signal['Low'].values; volume = df_signal['Volume'].values
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values
    
    # 1. ADX (ta library)
    adx_obj = ta.trend.ADXIndicator(df_signal['High'], df_signal['Low'], df_signal['Close'], window=14)
    adx_vals = adx_obj.adx().values / 10.0
    
    # 2. NATR (Original TR logic: SMA of max(H-L, H-Cp, L-Cp))
    tr = pd.concat([df_signal['High']-df_signal['Low'], 
                   abs(df_signal['High']-df_signal['Close'].shift(1)), 
                   abs(df_signal['Low']-df_signal['Close'].shift(1))], axis=1).max(axis=1)
    natrs = (tr.rolling(window=20).mean() / df_signal['Close'] * 100).fillna(2.0).values
    
    # 3. RSI
    rsi_vals = ta.momentum.RSIIndicator(df_signal['Close'], window=14).rsi().fillna(50).values
    
    # 4. ZL-Stochastic
    st_obj = ta.momentum.StochRSIIndicator(df_signal['Close'], window=10)
    st_k = st_obj.stochrsi_k().fillna(0.5).values
    stoch_zl = get_zl_val(st_k, 10)
    
    # 5. Engine Specs
    A, B, C = 0.6, -35, 170
    vwma_lens = (A * (adx_vals**2) + B * adx_vals + C).astype(int).clip(20, 300)
    pv_vals = close * volume
    
    print(f"Simulating Strategy (Start Index: 280)...")
    p = 1.0; cur = None; fee = 0.002
    for i in range(280, len(close)-1):
        if natrs[i] > 5.0: # Crash Guard
            target = 'Cash'
        else:
            w = vwma_lens[i]
            # VWMA logic
            ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
            if close[i] > ma:
                # Profit Take
                if rsi_vals[i] > 85 and (stoch_zl[i] > 0.9 or np.isnan(stoch_zl[i])):
                    target = 'Cash'
                else:
                    target = 'Long'
            else:
                target = 'Short'
        
        if target != cur:
            p *= (1 - fee); cur = target
        p *= (1 + (long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)))
    
    years = (len(close) - start_idx) / 252
    return (p**(1/years) - 1) * 100

def recon():
    # KOSPI 200
    df = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_l = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_s = yf.download('252670.KS', start='2016-01-01', progress=False)
    for d in [df, df_l, df_s]:
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
    common = df.index.intersection(df_l.index).intersection(df_s.index)
    df = df.loc[common]; df_l = df_l.loc[common]; df_s = df_s.loc[common]
    
    c_kospi = run_pure_strategy(df, df_l, df_s)
    print(f"KOSPI Champion CAGR: {c_kospi:.2f}%")
    
    # KOSDAQ 150
    df_q = yf.download('229200.KS', start='2016-01-01', progress=False)
    df_ql = yf.download('233740.KS', start='2016-01-01', progress=False)
    df_qs = yf.download('251340.KS', start='2016-01-01', progress=False)
    for d in [df_q, df_ql, df_qs]:
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
    common_q = df_q.index.intersection(df_ql.index).intersection(df_qs.index)
    df_q = df_q.loc[common_q]; df_ql = df_ql.loc[common_q]; df_qs = df_qs.loc[common_q]
    
    c_kosdaq = run_pure_strategy(df_q, df_ql, df_qs)
    print(f"KOSDAQ Champion CAGR: {c_kosdaq:.2f}%")
    print(f"Combined Average: {(c_kospi + c_kosdaq)/2:.2f}%")

if __name__ == "__main__":
    recon()
