import FinanceDataReader as fdr
import pandas as pd
import numpy as np

def run_dynamic_backtest():
    print("Fetching Data...")
    df_signal = fdr.DataReader('069500', '2010-01-01')['Close']
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    df_short = fdr.DataReader('252670', '2016-01-01')['Close']
    
    # Align
    df = pd.DataFrame({'Signal': df_signal, 'Long': df_long, 'Short': df_short}).dropna()
    
    # Indicators
    window = 240 # 1 Year Macro Trend
    
    # 1. Trend Strength (Z-Score)
    # (Price - MA) / Std
    roll_mean = df['Signal'].rolling(window=window).mean()
    roll_std = df['Signal'].rolling(window=window).std()
    df['Z_Score'] = (df['Signal'] - roll_mean) / roll_std
    
    # 2. Volatility (ATR-like, % change std)
    # 20-day Volatility
    df['Vol'] = df['Signal'].pct_change().rolling(window=20).std() * np.sqrt(252) # Annualized
    
    # Thresholds
    # Low Vol Regime < 15%? High > 20%?
    # KOSPI Avg Vol is around 10-15%.
    
    portfolio = [1.0]
    fee = 0.002
    current_asset = 'Cash' # 'Long_100', 'Long_50', 'Short_50', 'Short_100', 'Cash'
    # Actually we need to track cash/weights.
    # Let's simplify:
    # We just calculate daily return based on exposure.
    # Exposure: +1.0 (Long), +0.5, 0.0, -0.5, -1.0 (Short)
    
    exposure = 0.0
    
    dates = df.index
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    print(f"Backtesting Dynamic Sizing on {len(df)} days...")
    
    # 3. Main Loop
    for i in range(window, len(dates)-1):
        date = dates[i]
        next_date = dates[i+1]
        
        z = df['Z_Score'].iloc[i]
        vol = df['Vol'].iloc[i]
        
        # Logic: Determine Target Exposure
        target_exp = 0.0
        
        if pd.isna(z) or pd.isna(vol):
             target_exp = 0.0 # Safety
        else:
             # Trend Logic
             if z > 1.0:
                 target_exp = 1.0 # Strong Bull (2x Long)
             elif z > 0.5:
                 target_exp = 0.5 # Weak Bull
             elif z > -0.5:
                 target_exp = 0.0 # Neutral (Cash)
             elif z > -1.0:
                 target_exp = -0.5 # Weak Bear
             else:
                 target_exp = -1.0 # Strong Bear (Inverse)
            
        # Volatility Scaling (Risk Control)
        # If Volatility is High (>20%), halve the exposure
        if not pd.isna(vol) and vol > 0.20:
            target_exp *= 0.5
            
        # Execute
        # If we change exposure, we pay fee on the delta?
        # Simplified: If sign changes or magnitude changes significantly, pay fee.
        # Let's assess fee based on Turnover.
        turnover = abs(target_exp - exposure)
        cost = turnover * fee if turnover > 0 else 0
        
        # Calculate Return
        # Long Return (122630) ~ 2x Index. Short (252670) ~ -2x Index.
        # If Exposure is 0.5 Long, we buy 50% 122630.
        # If Exposure is -0.5 Short, we buy 50% 252670.
        
        day_ret = 0.0
        
        if target_exp > 0:
            # Long Leg
            if next_date in long_rets.index:
                r = long_rets.loc[next_date]
                day_ret = r * target_exp # We hold partial position
                # Remaining cash earns 0 (or risk free rate? assume 0)
        elif target_exp < 0:
            # Short Leg
            if next_date in short_rets.index:
                r = short_rets.loc[next_date]
                day_ret = r * abs(target_exp)
        
        # Apply Cost
        portfolio_val = portfolio[-1] * (1 - cost) * (1 + day_ret)
        portfolio.append(portfolio_val)
        
        exposure = target_exp
        
    # Stats
    final_val = portfolio[-1]
    years = (dates[-1] - dates[window]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    s = pd.Series(portfolio)
    mdd = (s / s.cummax() - 1).min()
    
    print("\n=== Dynamic Position Sizing (Z-Score + Vol Control) ===")
    print(f"Final Value: {final_val:.2f}x")
    print(f"CAGR: {cagr*100:.2f}%")
    print(f"MDD: {mdd*100:.2f}%")

if __name__ == "__main__":
    run_dynamic_backtest()
