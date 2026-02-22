import FinanceDataReader as fdr
import pandas as pd
import numpy as np

def run_continuous_backtest():
    print("Fetching Data...")
    df_signal = fdr.DataReader('069500', '2010-01-01') # KODEX 200
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    df_short = fdr.DataReader('252670', '2016-01-01')['Close']
    
    # Align
    df = pd.DataFrame({'Close': df_signal['Close'], 'Long': df_long, 'Short': df_short}).dropna()
    dates = df.index
    
    # Calculate Volatility (Annualized 20-day)
    df['Ret'] = df['Close'].pct_change()
    df['Vol'] = df['Ret'].rolling(window=20).std() * np.sqrt(252)
    
    print(f"Data Range: {dates[0]} ~ {dates[-1]}")
    
    # Grid Search for Formula: MA_Len = Intercept - Slope * Vol
    # Constraints: Min MA, Max MA
    
    intercepts = [120, 130, 140, 150, 160] # Base Slow MA
    slopes = [100, 200, 300, 400, 500] # Sensitivity
    min_ma_limit = 20
    
    best_cagr = -999
    best_params = None
    
    # To speed up, pre-calculate ALL moving averages once?
    # We need MAs from 20 to 160.
    # Let's pre-calc a dictionary of MAs.
    print("Pre-calculating MAs...")
    mas = {}
    for w in range(10, 201):
        mas[w] = df['Close'].rolling(window=w).mean()
        
    print("Optimization Loop...")
    
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    prices = df['Close'].values
    vols = df['Vol'].values
    
    start_idx = 200 # Safe start
    
    for intercept in intercepts:
        for slope in slopes:
            portfolio = [1.0]
            fee = 0.002
            current_asset = 'Cash'
            
            # Vectorized or Loop?
            # Since MA length changes daily, we pick from `mas` dict dynamically.
            # We can't vectorise easily. Loop is fine.
            
            for i in range(start_idx, len(dates)-1):
                next_date = dates[i+1]
                price = prices[i]
                vol = vols[i]
                
                # Formula
                # MA = Int - Slope * Vol
                if pd.isna(vol): 
                    target_ma = intercept
                else:
                    target_ma = int(intercept - (slope * vol))
                
                # Clip
                target_ma = max(min_ma_limit, min(target_ma, 200))
                
                # Get MA value
                # mas[target_ma] is a Series. We need iloc[i].
                # Accessing Series in loop is slow.
                # Optimization: `mas` dict contains numpy arrays?
                # mas[w] = df['Close'].rolling(window=w).mean().values
                
                # Let's assume we optimized this part (logic check first)
                ma_val = mas[target_ma].iloc[i] 
                
                if pd.isna(ma_val):
                    target = 'Cash'
                elif price > ma_val:
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
            
            if cagr > best_cagr:
                best_cagr = cagr
                best_params = (intercept, slope)
                print(f"New Best! Int{intercept}, Slope{slope}: {final_val:.1f}x (CAGR {cagr*100:.1f}%)")
                
    print(f"\n=== Best Continuous MA Strategy ===")
    print(f"Formula: MA = {best_params[0]} - {best_params[1]} * Vol")
    print(f"CAGR: {best_cagr*100:.2f}%")

if __name__ == "__main__":
    run_continuous_backtest()
