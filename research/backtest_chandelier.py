import FinanceDataReader as fdr
import pandas as pd
import numpy as np

def run_chandelier_backtest():
    print("Fetching Data...")
    df_signal = fdr.DataReader('069500', '2010-01-01')
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    df_short = fdr.DataReader('252670', '2016-01-01')['Close']
    
    df = pd.DataFrame({'Close': df_signal['Close'], 'High': df_signal['High'], 'Low': df_signal['Low'], 
                       'Long': df_long, 'Short': df_short}).dropna()
    dates = df.index
    
    # Indicators
    window = 113
    df['MA'] = df['Close'].rolling(window=window).mean()
    
    # ATR
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(window=22).mean()
    
    portfolio = [1.0]
    current_asset = 'Cash'
    entry_price = 0.0
    highest_high = 0.0 # Since entry
    lowest_low = 999999.0 # Since entry for short
    
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    threshold = 0.005
    mult = 3.0 # Chandelier Multiplier
    fee = 0.002
    
    print(f"Testing MA{window} + Chandelier Exit ({mult}x ATR)...")
    
    for i in range(window, len(dates)-1):
        date = dates[i]
        next_date = dates[i+1]
        
        price = df['Close'].iloc[i]
        ma = df['MA'].iloc[i]
        atr = df['ATR'].iloc[i]
        
        target = current_asset
        
        # Signals
        buy_signal = price > ma * (1 + threshold)
        sell_signal = price < ma * (1 - threshold)
        
        # Stop Logic (Chandelier)
        exit_signal = False
        
        if current_asset == 'Long':
            if price > highest_high: highest_high = price
            stop_price = highest_high - (atr * mult)
            if price < stop_price:
                exit_signal = True # Exit to Cash
        
        elif current_asset == 'Short':
            if price < lowest_low: lowest_low = price
            stop_price = lowest_low + (atr * mult)
            if price > stop_price:
                exit_signal = True # Exit to Cash
                
        # State Machine
        if current_asset == 'Cash':
            if buy_signal:
                target = 'Long'
                highest_high = price
            elif sell_signal:
                target = 'Short'
                lowest_low = price
                
        elif current_asset == 'Long':
            if sell_signal: # Reverse
                target = 'Short'
                lowest_low = price
            elif exit_signal: # Stop to Cash
                target = 'Cash'
                
        elif current_asset == 'Short':
            if buy_signal: # Reverse
                target = 'Long'
                highest_high = price
            elif exit_signal: # Stop to Cash
                target = 'Cash'
                
        # Trade
        if target != current_asset:
            if current_asset != 'Cash':
                 portfolio[-1] *= (1 - fee)
            current_asset = target
            # Reset High/Low if entering new trade
            if target == 'Long': highest_high = price
            if target == 'Short': lowest_low = price
            
        # Return
        r = 0.0
        if current_asset == 'Long':
            if next_date in long_rets.index: r = long_rets.loc[next_date]
        elif current_asset == 'Short':
            if next_date in short_rets.index: r = short_rets.loc[next_date]
            
        if pd.isna(r): r = 0.0
        portfolio.append(portfolio[-1] * (1 + r))
        
    final_val = portfolio[-1]
    years = (dates[-1] - dates[window]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    s = pd.Series(portfolio)
    mdd = (s / s.cummax() - 1).min()
    
    print(f"\n=== MA{window} + Chandelier Exit (ATR {mult}) Results ===")
    print(f"Final Value: {final_val:.2f}x")
    print(f"CAGR: {cagr*100:.2f}%")
    print(f"MDD: {mdd*100:.2f}%")

if __name__ == "__main__":
    run_chandelier_backtest()
