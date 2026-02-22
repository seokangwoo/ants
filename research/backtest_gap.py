import FinanceDataReader as fdr
import pandas as pd
import numpy as np

def run_gap_backtest():
    print("Fetching Data...")
    df = fdr.DataReader('069500', '2010-01-01') # KODEX 200
    
    # Calculate Returns
    # Overnight: Today Open / Prev Close
    # Intraday: Today Close / Today Open
    
    df['Prev_Close'] = df['Close'].shift(1)
    df = df.dropna()
    
    df['Ret_Night'] = df['Open'] / df['Prev_Close'] - 1
    df['Ret_Day'] = df['Close'] / df['Open'] - 1
    
    # Cumulative Returns
    df['Cum_Night'] = (1 + df['Ret_Night']).cumprod()
    df['Cum_Day'] = (1 + df['Ret_Day']).cumprod()
    df['Cum_Total'] = (1 + df['Change']).cumprod() # Start from 1
    
    print(f"Total Return: {df['Cum_Total'].iloc[-1]:.2f}x")
    print(f"Overnight Return: {df['Cum_Night'].iloc[-1]:.2f}x")
    print(f"Intraday Return: {df['Cum_Day'].iloc[-1]:.2f}x")
    
if __name__ == "__main__":
    run_gap_backtest()
