import yfinance as yf
import pandas as pd
import numpy as np
import ta
from itertools import product
import time

def calculate_parkinson(high, low, window=20):
    ln_hl = np.log(high / low)
    sq_ln_hl = pd.Series(ln_hl**2)
    # Parkinson formula: sqrt( (1 / (4 * n * ln2)) * sum( (ln(H/L))^2 ) )
    park = np.sqrt(sq_ln_hl.rolling(window).mean() / (4 * np.log(2)))
    return park.fillna(0).values * 100.0

def calculate_garman_klass(open_p, high, low, close, window=20):
    ln_hl = np.log(high / low)
    ln_co = np.log(close / open_p)
    gk = pd.Series(0.5 * (ln_hl**2) - (2 * np.log(2) - 1) * (ln_co**2))
    vol = np.sqrt(gk.rolling(window).mean())
    return vol.fillna(0).values * 100.0

def calculate_hv(close, window=20):
    rets = np.log(pd.Series(close) / pd.Series(close).shift(1))
    hv = rets.rolling(window).std() * np.sqrt(252)
    return hv.fillna(0).values * 100.0

def run_volatility_royale():
    print("Fetching KOSPI 200 Data for Volatility Royale...")
    df = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df.index.intersection(df_long.index).intersection(df_short.index)
    df = df.loc[common]; df_long = df_long.loc[common]; df_short = df_short.loc[common]
    
    close = df['Close'].values; high = df['High'].values
    low = df['Low'].values; open_p = df['Open'].values
    volume = df['Volume'].values
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values
    
    print("Calculating Volatility Metrics...")
    metrics = {
        'NATR': (ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close']).average_true_range() / df['Close'] * 100).values,
        'HV': calculate_hv(close),
        'Parkinson': calculate_parkinson(high, low),
        'Garman-Klass': calculate_garman_klass(open_p, high, low, close)
    }
    
    # Baseline Components (72% Champion)
    adx = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close']).adx().values / 10.0
    rsi = ta.momentum.RSIIndicator(df['Close']).rsi().values
    stoch_k = ta.momentum.StochRSIIndicator(df['Close'], window=10).stochrsi_k()
    stoch_zl = (stoch_k + (stoch_k - stoch_k.shift(4))).values
    pv_vals = close * volume
    
    # Engine lengths with ADX Champion params
    engine_lens = (0.6 * (adx**2) - 35 * adx + 170).astype(int).clip(20, 300)
    
    results = []
    
    print("\nTesting Volatility Dashboards...")
    for v_name, v_vals in metrics.items():
        # Optimization for each metric: Find the best threshold to act as "Crash Guard"
        # For NATR we used 5.0. Let's sweep 1.0 to 15.0
        best_t_cagr = -999; best_t = 0
        
        for t in np.arange(1.0, 15.0, 0.5):
            p = 1.0; cur = None; fee = 0.002
            for i in range(300, len(close)-1):
                if v_vals[i] > t:
                    target = 'Cash'
                else:
                    w = engine_lens[i]
                    ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
                    if close[i] > ma:
                        if rsi[i] > 85 and stoch_zl[i] > 0.9: target = 'Cash'
                        else: target = 'Long'
                    else: target = 'Short'
                
                if target != cur:
                    p *= (1 - fee); cur = target
                p *= (1 + (long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)))
            
            years = (len(close) - 300) / 252
            cagr = (p**(1/years) - 1) * 100
            if cagr > best_t_cagr:
                best_t_cagr = cagr
                best_t = t
                
        print(f" -> {v_name}: Best CAGR {best_t_cagr:.2f}% (Threshold: {best_t})")
        results.append({'Metric': v_name, 'CAGR': best_t_cagr, 'Threshold': best_t})

    print(f"\n=== VOLATILITY ROYALE WINNER ===")
    winner = max(results, key=lambda x: x['CAGR'])
    print(f"Top Metric: {winner['Metric']}")
    print(f"Top CAGR: {winner['CAGR']:.2f}%")
    print(f"Optimal Threshold: {winner['Threshold']}")
    print(f"Baseline (NATR 5.0): 72.14%")

if __name__ == "__main__":
    run_volatility_royale()
