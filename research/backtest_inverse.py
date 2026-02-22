from data_loader_long import fetch_all_etfs
import pandas as pd
import numpy as np

def run_inverse_backtest():
    # 1. Fetch Data
    data = fetch_all_etfs()
    
    # Align to daily dataframe
    df_close = pd.DataFrame({k: v['Close'] for k, v in data.items()})
    df_close = df_close.dropna()
    
    # Calculate Daily Returns
    daily_rets = df_close.pct_change()
    
    # Create Proxies
    # Long: 2x Leverage
    lev_rets = daily_rets * 2.0 - 0.0001
    
    # Short: 1x Inverse (Safe) or 2x Inverse?
    # Inverse ETFs usually decay faster. Let's use 1x Inverse First (-1.0x).
    inv_rets = daily_rets * -1.0 - 0.0001
    
    # Strategy Parameters
    LOOKBACK_LONG = 60 # 60 Day Trend for Smoother Signal
    # LOOKBACK_SHORT = 20 # Same for Short Entry?
    
    # Strategy Parameters
    MA_FAST = 5
    MA_SLOW = 60
    
    ma_fast = df_close.rolling(window=MA_FAST).mean()
    ma_slow = df_close.rolling(window=MA_SLOW).mean()
    mom_score = df_close.pct_change(60) # Still use 3-month mom for asset selection
    
    portfolio = [1.0]
    dates = df_close.index
    current_asset = 'Cash'
    
    risk_candidates = ['TIGER NASDAQ100', 'TIGER S&P500']
    
    fee = 0.001
    
    for i in range(1, len(dates)):
        date = dates[i]
        prev_date = dates[i-1]
        
        # 1. Pick Best Market
        best_risk = None
        best_risk_mom = -999
        
        score_row = mom_score.loc[prev_date]
        
        for asset in risk_candidates:
            if score_row[asset] > best_risk_mom:
                best_risk_mom = score_row[asset]
                best_risk = asset
        
        target = 'Cash'
        
        if best_risk:
            fast = ma_fast.loc[prev_date, best_risk]
            slow = ma_slow.loc[prev_date, best_risk]
            
            if fast > slow:
                # Bull Market -> Long 2x
                target = f"LONG_{best_risk}"
            else:
                # Bear Market -> Short 1x (Inverse)
                target = f"SHORT_{best_risk}"
        else:
            target = 'Cash'
            
        # Switch
        if target != current_asset:
            portfolio[-1] = portfolio[-1] * (1 - fee)
            current_asset = target
            
        # Apply Return
        daily_ret = 0.0
        
        if current_asset.startswith("LONG_"):
            asset = current_asset.replace("LONG_", "")
            daily_ret = lev_rets.loc[date, asset]
        elif current_asset.startswith("SHORT_"):
            asset = current_asset.replace("SHORT_", "")
            daily_ret = inv_rets.loc[date, asset]
        else:
            daily_ret = 0.0 # Cash
            
        new_val = portfolio[-1] * (1 + daily_ret)
        portfolio.append(new_val)
        
    # Stats
    final_val = portfolio[-1]
    years = (dates[-1] - dates[0]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    # Benchmark
    nasdaq = df_close['TIGER NASDAQ100']
    nasdaq_ret = nasdaq.iloc[-1] / nasdaq.iloc[0]
    nasdaq_cagr = nasdaq_ret ** (1/years) - 1
    
    s = pd.Series(portfolio)
    mdd = (s / s.cummax() - 1).min()
    
    print(f"=== Long/Short (2x Long, 1x Short) Strategy Results (MA5/60 Cross) ===")
    print(f"Final Value: {final_val:.2f}")
    print(f"CAGR: {cagr*100:.2f}%")
    print(f"MDD: {mdd*100:.2f}%")
    print(f"Benchmark: {nasdaq_cagr*100:.2f}%")

if __name__ == "__main__":
    run_inverse_backtest()
