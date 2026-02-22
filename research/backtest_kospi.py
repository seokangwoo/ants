import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from datetime import datetime

def fetch_kospi_data():
    start_date = '2016-01-01' # 252670 listed around late 2016? Let's check.
    # Actually 252670 (Kp200 Fut Inv 2x) listed 2016-09-22.
    
    # 069500: KODEX 200 (Signal)
    # 122630: KODEX Leverage (Long)
    # 252670: KODEX 200 Futures Inverse 2X (Short)
    
    tickers = {
        'Signal': '069500', 
        'Long': '122630', 
        'Short': '252670' 
    }
    
    data = {}
    print("Fetching data...")
    for name, ticker in tickers.items():
        df = fdr.DataReader(ticker, start_date)
        data[name] = df['Close']
        print(f"  {name} ({ticker}): {len(df)} rows")
        
    df = pd.DataFrame(data).dropna()
    return df

def run_backtest():
    df = fetch_kospi_data()
    
    # Strategy Parameters
    # Test multiple MAs
    mas = [5, 20, 60, 120]
    
    results = {}
    
    # Calculate Benchmark (Hold Long)
    long_only = df['Long'] / df['Long'].iloc[0]
    long_cagr = long_only.iloc[-1] ** (365.25 / (df.index[-1] - df.index[0]).days) - 1
    long_mdd = (long_only / long_only.cummax() - 1).min()
    
    print(f"\nBenchmark (Buy & Hold 122630): CAGR {long_cagr*100:.2f}%, MDD {long_mdd*100:.2f}%")
    
    for lookback in mas:
        # Calculate Signal on Underlying (KODEX 200)
        signal_price = df['Signal']
        # Rolling MA must be aligned
        ma = signal_price.rolling(window=lookback).mean()
        
        portfolio = [1.0]
        current_asset = 'Cash' # Start Cash
        fee = 0.002 # 0.2% Slippage+Fee
        
        # Calculate daily returns for assets
        long_rets = df['Long'].pct_change()
        short_rets = df['Short'].pct_change()
        
        # Align dates
        dates = df.index
        
        for i in range(1, len(dates)):
            date = dates[i]
            prev_date = dates[i-1]
            
            # Use prev_date for signal to avoid lookahead
            if prev_date not in ma.index or pd.isna(ma.loc[prev_date]):
                target = 'Cash'
            else:
                price = signal_price.loc[prev_date]
                trend = ma.loc[prev_date]
                
                if price > trend:
                    target = 'Long'
                else:
                    target = 'Short'
            
            # Trade Execution
            if target != current_asset:
                if current_asset != 'Cash':
                    portfolio[-1] *= (1 - fee)
                current_asset = target
            
            # Return Application
            daily_ret = 0.0
            if current_asset == 'Long':
                if date in long_rets.index:
                    daily_ret = long_rets.loc[date]
            elif current_asset == 'Short':
                if date in short_rets.index:
                    daily_ret = short_rets.loc[date]
            
            # Check NaN
            if pd.isna(daily_ret): daily_ret = 0.0
                
            portfolio.append(portfolio[-1] * (1 + daily_ret))
            
        # Stats calculate
        final_val = portfolio[-1]
        years = (dates[-1] - dates[0]).days / 365.25
        cagr = final_val ** (1/years) - 1
        
        s = pd.Series(portfolio)
        mdd = (s / s.cummax() - 1).min()
        
        results[lookback] = {'CAGR': cagr, 'MDD': mdd, 'Final': final_val}
        print(f"MA {lookback}: CAGR {cagr*100:.2f}%, MDD {mdd*100:.2f}%, Final {final_val:.2f}")

if __name__ == "__main__":
    run_backtest()
