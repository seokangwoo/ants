import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import itertools

def run_optimization():
    print("Fetching Data...")
    # Signal: KODEX 200
    df_signal = fdr.DataReader('069500', '2010-01-01')['Close']
    # Assets
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    df_short = fdr.DataReader('252670', '2016-01-01')['Close']
    
    # Align Data
    df = pd.DataFrame({'Signal': df_signal, 'Long': df_long, 'Short': df_short}).dropna()
    print(f"Data Range: {df.index[0]} ~ {df.index[-1]} ({len(df)} days)")
    
    # Parameters to Test
    # MA Window: 3 to 200 step 3 (66 variants)
    # Volatility Filter? No, let's stick to MA first (Primary Factor)
    # Adding Noise Filter: Trade only if Price > MA * (1 + threshold)
    
    ma_windows = range(3, 201, 2) # 100 variants
    thresholds = [0.0, 0.005, 0.01] # 0%, 0.5%, 1% Band
    
    best_ret = -999
    best_params = None
    best_stats = None
    
    results = []
    
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    print(f"Testing {len(ma_windows) * len(thresholds)} combinations...")
    
    for window in ma_windows:
        # Pre-calculate MA
        ma = df['Signal'].rolling(window=window).mean()
        
        for thresh in thresholds:
            portfolio = [1.0]
            current_asset = 'Cash'
            fee = 0.002
            
            # Vectorize simulation? Hard with state. Loop is safer for logic check.
            # Optimization: Pre-calculate Signal Arrays
            # Signal: 1 (Long), -1 (Short), 0 (Cash)
            
            # Logic:
            # If Price > MA * (1+thresh) -> Long
            # If Price < MA * (1-thresh) -> Short
            # Else -> Hold Previous (Neutral Zone)
            
            # To speed up, we iterate indices
            dates = df.index
            prices = df['Signal'].values
            ma_vals = ma.values
            
            # We need to skip until window exists
            start_idx = window
            
            if start_idx >= len(dates): continue

            for i in range(start_idx, len(dates)-1): # Predict for next day
                date = dates[i]
                next_date = dates[i+1] # Valid return day
                
                p = prices[i]
                m = ma_vals[i]
                
                target = current_asset
                
                if pd.isna(m): continue
                
                if p > m * (1 + thresh):
                    target = 'Long'
                elif p < m * (1 - thresh):
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
            
            if not portfolio: continue
                
            final_val = portfolio[-1]
            
            if final_val > best_ret:
                best_ret = final_val
                best_params = (window, thresh)
                
                # Calc Params
                years = (dates[-1] - dates[0]).days / 365.25
                cagr = final_val ** (1/years) - 1
                s = pd.Series(portfolio)
                mdd = (s / s.cummax() - 1).min()
                
                best_stats = (cagr, mdd)
                print(f"New Best! MA{window}, Thresh{thresh}: {final_val:.2f}x (CAGR {cagr*100:.1f}%)")

    print("\n=== OPTIMIZATION RESULTS ===")
    print(f"Best Parameters: MA Window = {best_params[0]}, Threshold = {best_params[1]}")
    print(f"Final Value: {best_ret:.2f}x")
    print(f"CAGR: {best_stats[0]*100:.2f}%")
    print(f"MDD: {best_stats[1]*100:.2f}%")

if __name__ == "__main__":
    run_optimization()
