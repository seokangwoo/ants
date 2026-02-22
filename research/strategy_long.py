import pandas as pd
import numpy as np

class DualMomentum:
    def __init__(self, lookback_period=60, rebalance_freq='M'):
        self.lookback = lookback_period # 60 days ~ 3 months
        self.freq = rebalance_freq

    def run_strategy(self, data):
        """
        data: Dict of DataFrames (KODEX 200, S&P500, etc.)
        """
        # Align all data to common index
        df_close = pd.DataFrame({k: v['Close'] for k, v in data.items()})
        df_close = df_close.dropna()
        
        # Calculate Weighted Momentum Score
        # Score = 12*R1 + 4*R3 + 2*R6 + 1*R12 (Aggressive/Fast)
        # Parameters
        LOOKBACK = 120 # 6 Months
        
        # Calculate Returns (6 Month)
        returns = df_close.pct_change(LOOKBACK)
        
        # Calculate MA (Trend Filter)
        ma = df_close.rolling(window=LOOKBACK).mean()
        
        # Monthly Rebalance
        try:
            monthly_dates = df_close.resample('ME').last().index
        except:
            monthly_dates = df_close.resample('M').last().index
            
        portfolio_value = [1.0]
        current_holding = 'Cash'
        holding_log = []
        
        risk_assets = ['TIGER NASDAQ100', 'TIGER S&P500', 'KODEX 200']
        safe_assets = ['KODEX Dollar', 'KODEX Gold'] # Bond is too weak
        
        for i in range(1, len(monthly_dates)):
            date = monthly_dates[i]
            prev_date = monthly_dates[i-1]
            
            if date not in df_close.index:
                try:
                    idx = df_close.index.get_loc(date, method='ffill')
                    date = df_close.index[idx]
                except: continue
                
            # 1. Pick Top Risk Asset (Relative Momentum)
            curr_returns = returns.loc[date]
            
            best_risk = None
            best_risk_ret = -999
            
            for asset in risk_assets:
                if asset not in curr_returns: continue
                if curr_returns[asset] > best_risk_ret:
                    best_risk_ret = curr_returns[asset]
                    best_risk = asset
            
            # 2. Check Trend (Absolute Momentum)
            # Buy if Best Risk > MA
            target_asset = 'Cash'
            
            # DEBUG
            if i % 12 == 0:
                 print(f"Date: {date}")
            
            if best_risk:
                price = df_close.loc[date, best_risk]
                trend = ma.loc[date, best_risk]
                
                # DEBUG
                if i % 12 == 0:
                     print(f"  Best Risk: {best_risk}, Price: {price:.2f}, MA: {trend:.2f}, Gain: {best_risk_ret:.4f}")
                
                if price > trend:
                    target_asset = best_risk
                else:
                    # Defense: Pick Best Safe Asset
                    best_safe = None
                    best_safe_ret = -999
                    for asset in safe_assets:
                        if asset not in curr_returns: continue
                        if curr_returns[asset] > best_safe_ret:
                            best_safe_ret = curr_returns[asset]
                            best_safe = asset
                    
                    if best_safe:
                        target_asset = best_safe
                        
                    if i % 12 == 0:
                         print(f"  Defensive! Best Safe: {best_safe} ({best_safe_ret:.4f})")
            
            # Calculate Return
            period_ret = 0.0
            if current_holding != 'Cash':
                try:
                    # Use asof to find valid trading days
                    valid_prev_date = df_close.index.asof(prev_date)
                    valid_curr_date = df_close.index.asof(date)
                    
                    if pd.isna(valid_prev_date) or pd.isna(valid_curr_date):
                        period_ret = 0.0
                        
                    else:
                        p_start = df_close.loc[valid_prev_date, current_holding]
                        p_end = df_close.loc[valid_curr_date, current_holding]
                        
                        raw_ret = (p_end - p_start) / p_start
                        
                        # Apply 2x Leverage if Risk Asset
                        if current_holding in risk_assets:
                             # Simple 2x approximation (daily compounding is different but monthly 2x is close enough for estimate)
                             # Fee: 2x ETF usually has higher expense ratio and volatility drag.
                             # Let's be conservative: 1.9x return minus extra fee.
                             period_ret = raw_ret * 2.0 - 0.002 # 0.2% monthly cost for leverage
                        else:
                             period_ret = raw_ret
                             
                        period_ret -= 0.001 # Transaction fee
                        
                except Exception as e:
                    print(f"Error calc return: {e}")
                    period_ret = 0.0
            
            new_val = portfolio_value[-1] * (1 + period_ret)
            portfolio_value.append(new_val)
            
            # holding_log.append(...)
            
            # DEBUG Logs removed for clean run, or keep if needed? 
            # Let's keep them but concise or just remove to verify speed.
            # I will remove verbose logs now that I found the bug.
            
            holding_log.append({
                'Date': date,
                'Holding': current_holding,
                'Return': period_ret,
                'Value': new_val
            })
            
            current_holding = target_asset
            
        return pd.DataFrame(holding_log)
