import FinanceDataReader as fdr
import pandas as pd
import numpy as np

def run_us_correlation_backtest():
    print("Fetching Data...")
    # KOSPI 200
    df_kospi = fdr.DataReader('069500', '2010-01-01')
    # S&P 500 (SPY)
    df_spy = fdr.DataReader('SPY', '2010-01-01')
    
    # Assets
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    df_short = fdr.DataReader('252670', '2016-01-01')['Close']
    
    # Align Data (US and Korea have different holidays)
    # We need to map: Date T in Korea uses Date T-1 in US (Previous Close).
    # Korea runs 09:00 ~ 15:30. US fits T-1 Close.
    
    df_spy['SPY_Close'] = df_spy['Close']
    df_spy['SPY_Ret'] = df_spy['Close'].pct_change()
    
    # Shift SPY by 1 day to align with KOSPI Trading Day
    # e.g., SPY(Monday) affects KOSPI(Tuesday).
    df_spy_shifted = df_spy.shift(1)
    
    # Merge
    df = pd.concat([df_kospi['Close'].rename('KOSPI'), df_spy_shifted['SPY_Close']], axis=1).dropna()
    df['Long'] = df_long
    df['Short'] = df_short
    df = df.dropna()
    
    dates = df.index
    print(f"Data Range: {dates[0]} ~ {dates[-1]}")
    
    # Strategy Logic: "Global Trend Alignment"
    # MA Window for both
    window = 113 # Use our proven number
    
    df['KOSPI_MA'] = df['KOSPI'].rolling(window=window).mean()
    df['SPY_MA'] = df['SPY_Close'].rolling(window=window).mean()
    
    population = len(df)
    
    portfolio = [1.0]
    fee = 0.002
    current_asset = 'Cash'
    
    kospi_long_rets = df['Long'].pct_change()
    kospi_short_rets = df['Short'].pct_change()
    
    # Iterate
    # Skip window
    
    print("Running Global Trend Backtest...")
    
    for i in range(window, len(dates)-1):
        date = dates[i]
        next_date = dates[i+1]
        
        k_price = df['KOSPI'].iloc[i]
        k_ma = df['KOSPI_MA'].iloc[i]
        
        s_price = df['SPY_Close'].iloc[i]
        s_ma = df['SPY_MA'].iloc[i]
        
        target = 'Cash'
        
        # Logic: Catch-Up / Lead-Lag
        # If US is strong (Bull), KOSPI should follow eventually.
        # If KOSPI is weak (Bear) while US is strong, it's a buying opportunity?
        # OR: KOSPI is weak because of local issues, but US strength puts a floor.
        
        # Test: Follow US Trend Only?
        # If SPY > MA -> Long KOSPI?
        if s_price > s_ma:
             target = 'Long'
        else:
             target = 'Short'
            
        # Trade
        if target != current_asset:
            if current_asset != 'Cash':
                portfolio[-1] *= (1 - fee)
            current_asset = target
            
        # Return
        r = 0.0
        if current_asset == 'Long':
            if next_date in kospi_long_rets.index: r = kospi_long_rets.loc[next_date]
        elif current_asset == 'Short':
            if next_date in kospi_short_rets.index: r = kospi_short_rets.loc[next_date]
            
        if pd.isna(r): r = 0.0
        portfolio.append(portfolio[-1] * (1 + r))
        
    final_val = portfolio[-1]
    years = (dates[-1] - dates[window]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    s = pd.Series(portfolio)
    mdd = (s / s.cummax() - 1).min()
    
    print(f"\n=== Global Trend (KOSPI + US Alignment) Results ===")
    print(f"Final Value: {final_val:.2f}x")
    print(f"CAGR: {cagr*100:.2f}%")
    print(f"MDD: {mdd*100:.2f}%")

if __name__ == "__main__":
    run_us_correlation_backtest()
