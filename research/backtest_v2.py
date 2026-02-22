from data_loader import fetch_daily_data, get_top_liquid_tickers
from strategy_v2 import StrategyV2
import pandas as pd
import numpy as np

def run_backtest():
    tickers = get_top_liquid_tickers()
    start_date = "2024-01-01"
    end_date = "2026-02-18"
    
    print(f"=== Running Backtest V2 ({start_date} ~ {end_date}) ===")
    
    strategies = [
        {'name': 'Dynamic K + MA5', 'k': 'dynamic'}
    ]
    
    for s in strategies:
        print(f"\n--- Strategy: {s['name']} ---")
        strategy = StrategyV2()
        
        total_strategies = []
        total_buyholds = []
        
        for ticker in tickers:
            try:
                df = fetch_daily_data(ticker, start_date)
                if df.empty: continue
                
                # Buy & Hold Return
                if not df.empty:
                    bh_ret = (df['Close'].iloc[-1] - df['Open'].iloc[0]) / df['Open'].iloc[0]
                    total_buyholds.append(bh_ret + 1)
                
                df = strategy.generate_signals(df)
                cum_ret = (1 + df['Strategy_Return']).cumprod()
                final_ret = cum_ret.iloc[-1] if not cum_ret.empty else 1.0
                total_strategies.append(final_ret)
                
                print(f"  {ticker}: Strategy={final_ret:.2f}, BH={bh_ret+1:.2f}")
            except Exception as e:
                print(f"  Error {ticker}: {e}")
                
        avg_strat = np.mean(total_strategies)
        avg_bh = np.mean(total_buyholds)
        
        print(f"  >> Avg Strategy: {avg_strat:.4f} ({ (avg_strat-1)*100:.2f}% )")
        print(f"  >> Avg Buy&Hold: {avg_bh:.4f} ({ (avg_bh-1)*100:.2f}% )")

if __name__ == "__main__":
    run_backtest()
