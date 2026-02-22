from data_loader_long import fetch_all_etfs
import pandas as pd
import numpy as np

def run_leverage_backtest():
    # 1. Fetch Data
    data = fetch_all_etfs()
    
    # Align to daily dataframe
    df_close = pd.DataFrame({k: v['Close'] for k, v in data.items()})
    df_close = df_close.dropna()
    
    # Calculate Daily Returns
    daily_rets = df_close.pct_change()
    
    # Create Proxies for Leveraged ETFs (2x)
    # 2x Daily Return - Expense Ratio/Slippage (approx 0.01% daily ~ 2.5% annual)
    lev_rets = daily_rets * 2.0 - 0.0001 
    
    # Strategy Parameters
    LOOKBACK = 60 # 3 Months Trend
    
    # Moving Average for Trend
    ma = df_close.rolling(window=LOOKBACK).mean()
    
    # Momentum Score (6 month return)
    # We use Underlying Asset for Signal, but Trade the Leveraged Asset
    mom_score = df_close.pct_change(LOOKBACK)
    
    # Portfolio
    portfolio = [1.0]
    dates = df_close.index
    current_asset = 'Cash'
    
    # Assets to Trade
    # Risk: TIGER NASDAQ100, TIGER S&P500
    # Safe: KODEX Dollar, KODEX Gold
    
    risk_candidates = ['TIGER NASDAQ100', 'TIGER S&P500']
    safe_candidates = ['KODEX Dollar', 'KODEX Gold']
    
    fee = 0.001 # 0.1% Transaction Fee
    
    # Daily Simulation? Or Monthly Rebalance?
    # Dual Momentum is usually Monthly. Daily is too noisy/expensive.
    # Let's check signal at month end, but calculate value daily? 
    # Or just calculate Monthly return of Daily Leveraged?
    
    # Let's do Daily Simulation with Monthly Rebalance for accuracy
    
    next_rebalance = dates[0]
    
    for i in range(1, len(dates)):
        date = dates[i]
        prev_date = dates[i-1]
        
        # Check Rebalance
        # If date is new month
        is_rebalance = False
        if date.month != prev_date.month:
            is_rebalance = True
            
        if is_rebalance:
            # Generate Signal
            
            # 1. Best Risk Asset
            best_risk = None
            best_risk_mom = -999
            
            score_row = mom_score.loc[prev_date] # Use prev close data to trade today open/close? 
            # Rebalance at Month End close implies we knew result. 
            # Realistically: Trade at today's close based on today's data (if assumed accessible)
            # or Tomorrow Open. Backtests usually assume Close execution.
            score_row = mom_score.loc[date]
            
            for asset in risk_candidates:
                if score_row[asset] > best_risk_mom:
                    best_risk_mom = score_row[asset]
                    best_risk = asset
            
            # 2. Trend Filter
            target = 'Cash'
            
            if best_risk:
                price = df_close.loc[date, best_risk]
                trend = ma.loc[date, best_risk]
                
                if price > trend:
                    target = best_risk # We will map this to Leveraged later
                else:
                    # Defensive
                    best_safe = None
                    best_safe_mom = -999
                    for asset in safe_candidates:
                        if score_row[asset] > best_safe_mom:
                            best_safe_mom = score_row[asset]
                            best_safe = asset
                    
                    # Filter Safe?
                    if best_safe:
                        target = best_safe
            else:
                 # No valid risk asset (e.g. data missing)
                 target = 'Cash'
            
            # Switch?
            if target != current_asset:
                # Fee
                portfolio[-1] = portfolio[-1] * (1 - fee)
                current_asset = target
        
        # Apply Return
        # If Risk Asset -> Use Leveraged Return
        # If Safe Asset -> Use 1x Return (or 2x? usually 1x for safety)
        
        daily_ret = 0.0
        if current_asset in risk_candidates:
            daily_ret = lev_rets.loc[date, current_asset]
        elif current_asset in safe_candidates:
            daily_ret = daily_rets.loc[date, current_asset] # 1x for safety
        
        new_val = portfolio[-1] * (1 + daily_ret)
        portfolio.append(new_val)
    
    # Stats
    final_val = portfolio[-1]
    years = (dates[-1] - dates[0]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    # Benchmark (Buy & Hold Nasdaq)
    nasdaq = df_close['TIGER NASDAQ100']
    nasdaq_ret = nasdaq.iloc[-1] / nasdaq.iloc[0]
    nasdaq_cagr = nasdaq_ret ** (1/years) - 1
    
    print(f"=== Leveraged (2x) Dual Momentum Results (2014-2025) ===")
    print(f"Final Value: {final_val:.2f} (Start: 1.0)")
    print(f"CAGR: {cagr*100:.2f}%")
    print(f"Benchmark (Nasdaq 100) CAGR: {nasdaq_cagr*100:.2f}%")
    
    # MDD
    s = pd.Series(portfolio)
    mdd = (s / s.cummax() - 1).min()
    print(f"MDD: {mdd*100:.2f}%")

if __name__ == "__main__":
    run_leverage_backtest()
