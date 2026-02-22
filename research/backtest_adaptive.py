import FinanceDataReader as fdr
import pandas as pd
import numpy as np

def calculate_kama(df, n=10, pow1=2, pow2=30):
    """
    Kaufman's Adaptive Moving Average (KAMA)
    n: Window for Efficiency Ratio (ER)
    pow1: Fast MA window (e.g. 2 days)
    pow2: Slow MA window (e.g. 30 days)
    """
    df = df.copy()
    
    # 1. Efficiency Ratio (ER)
    change = abs(df['Close'] - df['Close'].shift(n))
    volatility = df['Close'].diff().abs().rolling(window=n).sum()
    er = change / volatility
    er = er.fillna(0)
    
    # 2. Smoothing Constant (SC)
    # sc = [er * (fast_sc - slow_sc) + slow_sc] ^ 2
    fast_sc = 2 / (pow1 + 1)
    slow_sc = 2 / (pow2 + 1)
    sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
    
    # 3. KAMA Calculation
    kama = np.zeros_like(df['Close'])
    kama[n-1] = df['Close'].iloc[n-1] # Initialize
    
    # Iterative calculation (Pandas ewm is close but KAMA is specific)
    # Loop is slow but precise
    prices = df['Close'].values
    sc_vals = sc.values
    
    for i in range(n, len(df)):
        kama[i] = kama[i-1] + sc_vals[i] * (prices[i] - kama[i-1])
        
    df['KAMA'] = kama
    # Replace initial zeros with NaN or first price
    df['KAMA'].iloc[:n] = np.nan
    
    return df['KAMA']

def run_adaptive_backtest():
    print("Fetching Data...")
    df_signal = fdr.DataReader('069500', '2010-01-01') # KODEX 200
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    df_short = fdr.DataReader('252670', '2016-01-01')['Close']
    
    # Align
    df = pd.DataFrame({'Signal': df_signal['Close'], 'Long': df_long, 'Short': df_short}).dropna()
    dates = df.index
    
    print(f"Data Range: {dates[0]} ~ {dates[-1]}")
    
    # Parameters for KAMA optimization
    # User wants "50% Return".
    # Standard KAMA is (10, 2, 30).
    # Since we trade Long-Term (MA113 was best), maybe Slow Limit should be 200?
    # And Fast Limit 20?
    # ER Window: 60 days?
    
    er_windows = [10, 30, 60]
    fast_limits = [2, 10, 20]
    slow_limits = [30, 100, 200]
    
    best_cagr = -999
    best_params = None
    
    print("Optimization Loop...")
    
    for er_w in er_windows:
        for fast_w in fast_limits:
            for slow_w in slow_limits:
                if fast_w >= slow_w: continue
                
                # Calc KAMA
                kama = calculate_kama(df_signal[['Close']], n=er_w, pow1=fast_w, pow2=slow_w)
                kama_vals = kama.reindex(dates).values # Align to trade dates
                prices = df['Signal'].values
                
                # Backtest
                portfolio = [1.0]
                fee = 0.002
                current_asset = 'Cash'
                
                long_rets = df['Long'].pct_change()
                short_rets = df['Short'].pct_change()
                
                start_idx = er_w
                if start_idx >= len(dates): continue
                
                valid = True
                
                for i in range(start_idx, len(dates)-1):
                    date = dates[i]
                    next_date = dates[i+1]
                    
                    p = prices[i]
                    k = kama_vals[i]
                    
                    if np.isnan(k) or k == 0: 
                        target = 'Cash'
                    elif p > k:
                        target = 'Long'
                    else:
                        target = 'Short'
                        
                    # Trade
                    if target != current_asset:
                        if current_asset != 'Cash':
                            portfolio[-1] *= (1 - fee)
                        current_asset = target
                        
                    # Return
                    r = 0.0
                    if current_asset == 'Long':
                        if next_date in long_rets.index: r = long_rets.loc[next_date]
                    elif current_asset == 'Short':
                        if next_date in short_rets.index: r = short_rets.loc[next_date]
                    
                    if pd.isna(r): r = 0.0
                    portfolio.append(portfolio[-1] * (1 + r))
                    
                final_val = portfolio[-1]
                years = (dates[-1] - dates[start_idx]).days / 365.25
                if years <= 0: continue
                cagr = final_val ** (1/years) - 1
                
                print(f"ER{er_w}, F{fast_w}, S{slow_w}: CAGR {cagr*100:.1f}%, Final {final_val:.1f}x")
                
                if cagr > best_cagr:
                    best_cagr = cagr
                    best_params = (er_w, fast_w, slow_w)
                    
    print(f"\n=== Best Adaptive (KAMA) Strategy ===")
    print(f"Params: ER{best_params[0]}, Fast{best_params[1]}, Slow{best_params[2]}")
    print(f"CAGR: {best_cagr*100:.2f}%")

if __name__ == "__main__":
    run_adaptive_backtest()
