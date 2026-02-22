from data_loader_long import fetch_all_etfs
from strategy_long import DualMomentum
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def run_backtest():
    # 1. Fetch Data
    data = fetch_all_etfs()
    
    # 2. Run Strategy
    # Classic Dual Momentum uses 12 month lookback
    dm = DualMomentum(lookback_period=250, rebalance_freq='M')
    
    print("Running Dual Momentum Strategy (2014-2024)...")
    res_df = dm.run_strategy(data)
    
    if res_df.empty:
        print("No trades generated.")
        return

    # 3. Process Results
    res_df['Date'] = pd.to_datetime(res_df['Date'])
    res_df.set_index('Date', inplace=True)
    
    # Print Date Range
    print(f"Backtest Period: {res_df.index[0]} ~ {res_df.index[-1]}")
    
    final_val = res_df['Value'].iloc[-1]
    years = (res_df.index[-1] - res_df.index[0]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    # MDD Calculation
    rolling_max = res_df['Value'].cummax()
    drawdown = (res_df['Value'] - rolling_max) / rolling_max
    mdd = drawdown.min()
    
    # Print Individual Asset Performance
    print("\n=== Asset Performance (Buy & Hold) ===")
    start_date = res_df.index[0]
    end_date = res_df.index[-1]
    
    print("\n=== Asset Performance (Buy & Hold) ===")
    start_date = res_df.index[0]
    end_date = res_df.index[-1]
    
    for name, df in data.items():
        try:
            # Safe Lookup
            # Filter by date range first
            mask = (df.index >= start_date) & (df.index <= end_date)
            subset = df.loc[mask]
            
            if subset.empty:
                print(f"{name}: No data in backtest range")
                continue
                
            s_val = subset.iloc[0]['Close']
            e_val = subset.iloc[-1]['Close']
            
            ret = e_val / s_val
            asset_cagr = ret ** (1/years) - 1
            
            # MDD
            series = subset['Close']
            mdd = (series / series.cummax() - 1).min()
            
            print(f"{name}: Returns={ret:.2f}x, CAGR={asset_cagr*100:.2f}%, MDD={mdd*100:.2f}%")
        except Exception as e:
            print(f"{name}: Error calculating stats ({e})")
            
    print(f"\n=== Backtest Results (Strategy) ===")
    print(f"Final Portfolio Value: {final_val:.4f} (Start: 1.0)")
    print(f"CAGR: {cagr*100:.2f}%")
    print(f"MDD: {mdd*100:.2f}%")

if __name__ == "__main__":
    run_backtest()
