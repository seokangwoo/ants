import FinanceDataReader as fdr
import pandas as pd
import numpy as np

def run_vbo_backtest():
    print("Fetching Data...")
    # We need OHLC of KODEX 200 to generate signals
    df_signal = fdr.DataReader('069500', '2016-01-01') # Underlying
    
    # Assets (we trade these)
    df_long = fdr.DataReader('122630', '2016-01-01')
    df_short = fdr.DataReader('252670', '2016-01-01')
    
    # Parameters
    k = 0.5 # Betting on breakouts > 0.5 * Range
    
    # Calculate Range (Previous Day)
    df_signal['Range'] = df_signal['High'] - df_signal['Low']
    df_signal['Target_Long'] = df_signal['Open'] + df_signal['Range'].shift(1) * k
    df_signal['Target_Short'] = df_signal['Open'] - df_signal['Range'].shift(1) * k
    
    # We need to simulate trading on 'Asset' based on 'Signal' breakout
    # Approximation:
    # If Signal High > Target Long -> We bought Long.
    # Return = (Signal Close - Target Long) / Target Long
    # Leverage = 2x.
    
    portfolio = [1.0]
    fee = 0.002
    
    dates = df_signal.index
    
    print(f"Testing Volatility Breakout (k={k}) on {len(dates)} days...")
    
    for i in range(1, len(dates)):
        date = dates[i]
        
        # Signal Data
        open_p = df_signal['Open'].iloc[i]
        high_p = df_signal['High'].iloc[i]
        low_p = df_signal['Low'].iloc[i]
        close_p = df_signal['Close'].iloc[i]
        
        target_long = df_signal['Target_Long'].iloc[i]
        target_short = df_signal['Target_Short'].iloc[i]
        
        # Logic: 
        # Check Long Breakout
        long_triggered = high_p > target_long
        # Check Short Breakout
        short_triggered = low_p < target_short
        
        daily_ret = 0.0
        trades = 0
        
        # Conflict? Both triggered?
        # Usually we prioritize the first one or take both (whipsaw).
        # Let's assume we take the one in direction of MA5?
        # Or simple: Long VBO.
        
        if long_triggered:
            # We entered at target_long.
            # We exit at close_p.
            # Underlying Return
            raw_ret = (close_p - target_long) / target_long
            # Asset Return (2x)
            daily_ret = raw_ret * 2.0 - fee
            entry_success = True
            
            # Stop Loss? If we bought and it crashed?
            # VBO is risky.
        
        # We accumulate
        portfolio.append(portfolio[-1] * (1 + daily_ret))
        
    # Stats
    final_val = portfolio[-1]
    years = (dates[-1] - dates[0]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    s = pd.Series(portfolio)
    mdd = (s / s.cummax() - 1).min()
    
    print("\n=== Volatility Breakout (2x Long Only) Results ===")
    print(f"Final Value: {final_val:.2f}x")
    print(f"CAGR: {cagr*100:.2f}%")
    print(f"MDD: {mdd*100:.2f}%")

if __name__ == "__main__":
    run_vbo_backtest()
