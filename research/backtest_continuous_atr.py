import FinanceDataReader as fdr
import pandas as pd
import numpy as np

def run_continuous_atr_backtest():
    print("Fetching Data...")
    df_signal = fdr.DataReader('069500', '2010-01-01') # KODEX 200
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    df_short = fdr.DataReader('252670', '2016-01-01')['Close']
    
    # Align
    df = pd.DataFrame({'Close': df_signal['Close'], 'High': df_signal['High'], 'Low': df_signal['Low'],
                       'Long': df_long, 'Short': df_short}).dropna()
    dates = df.index
    
    # Calculate NATR (Normalized ATR)
    # TR = Max(H-L, H-PC, L-PC)
    df['Prev_Close'] = df['Close'].shift(1)
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Prev_Close'])
    df['L-PC'] = abs(df['Low'] - df['Prev_Close'])
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    
    # ATR Window: Standard 20 or 14? User said "ATR". Let's use 20 to match Vol window.
    df['ATR'] = df['TR'].rolling(window=20).mean()
    df['NATR'] = (df['ATR'] / df['Close']) * 100
    
    print(f"Data Range: {dates[0]} ~ {dates[-1]}")
    print(f"NATR Stats: Min {df['NATR'].min():.2f}, Max {df['NATR'].max():.2f}, Mean {df['NATR'].mean():.2f}")
    
    # Pre-calculate MAs
    print("Pre-calculating MAs...")
    mas = {}
    for w in range(10, 251): # Wide range
        mas[w] = df['Close'].rolling(window=w).mean()
        
    print("Optimization Loop...")
    
    # Grid Search
    # Formula: MA = Int - Slope * NATR
    # If NATR is 1.0 (Low), MA = Int - Slope
    # If NATR is 4.0 (High), MA = Int - 4*Slope
    # We want High MA at Low NATR, Low MA at High NATR.
    
    intercepts = [120, 140, 150, 160, 180, 200, 220]
    slopes = [10, 15, 20, 25, 30, 35, 40, 50, 60]
    
    # Limits
    min_ma = 20
    max_ma = 250
    
    best_cagr = -999
    best_params = None
    
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    prices = df['Close'].values
    natrs = df['NATR'].values
    
    start_idx = 250 # Safe start
    
    for intercept in intercepts:
        for slope in slopes:
            portfolio = [1.0]
            fee = 0.002
            current_asset = 'Cash'
            
            for i in range(start_idx, len(dates)-1):
                next_date = dates[i+1]
                price = prices[i]
                natr = natrs[i]
                
                # Formula
                if pd.isna(natr):
                    target_ma = intercept
                else:
                    target_ma = int(intercept - (slope * natr))
                
                # Clip
                target_ma = max(min_ma, min(target_ma, max_ma))
                
                # Signal
                limit = mas[target_ma].iloc[i]
                
                if pd.isna(limit):
                    target = 'Cash'
                elif price > limit:
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
                
    print(f"\n=== Best Continuous NATR Strategy ===")
    print(f"Formula: MA = {best_params[0]} - {best_params[1]} * NATR")
    print(f"CAGR: {best_cagr*100:.2f}%")

if __name__ == "__main__":
    run_continuous_atr_backtest()
