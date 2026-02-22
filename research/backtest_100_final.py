import yfinance as yf
import pandas as pd
import numpy as np

def calculate_mcginley_dynamic(series, length):
    # MD[i] = MD[i-1] + (Price[i] - MD[i-1]) / (k * (Price[i]/MD[i-1])^4)
    # k = 0.6 * length
    # This is hard to vectorize. Loop time.
    md = [series.iloc[0]]
    prices = series.values
    k = 0.6 * length
    
    for i in range(1, len(prices)):
        prev_md = md[-1]
        price = prices[i]
        
        # McGinley Formula
        # avoid div by zero
        if prev_md == 0: prev_md = price
        
        try:
            md_val = prev_md + (price - prev_md) / (k * ((price/prev_md)**4))
        except:
            md_val = prev_md
            
        md.append(md_val)
        
    return pd.Series(md, index=series.index)

def run_100_final():
    print("Fetching Data...")
    df_signal = yf.download('069500.KS', start='2010-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2010-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-09-01', progress=False)
    
    # Clean Columns
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    # Align
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df = pd.DataFrame({
        'Close': df_signal.loc[common]['Close'],
        'Long': df_long.loc[common]['Close'],
        'Short': df_short.loc[common]['Close']
    }).dropna()
    
    dates = df.index
    close = df['Close']
    
    print("Pre-calculating McGinley Dynamic (MD)...")
    # McGinley logic reduces lag significantly.
    # We test Lengths [10, 20, 50, 100]
    mds = {}
    for length in [5, 10, 20, 50, 80, 120]:
         mds[length] = calculate_mcginley_dynamic(close, length)
         
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    prices = close.values
    
    best_cagr = -999
    
    print("Optimization Loop (McGinley)...")
    
    start_idx = 150
    
    for length in mds.keys():
        portfolio = [1.0]
        fee = 0.002
        current_asset = 'Cash'
        
        md_series = mds[length]
        
        for i in range(start_idx, len(dates)-1):
            price = prices[i]
            md_val = md_series.iloc[i]
            
            # Logic: Price > MD -> Long, else Short
            if pd.isna(md_val): target = 'Cash'
            elif price > md_val: target = 'Long'
            else: target = 'Short'
            
            # Trade
            if target != current_asset:
                if current_asset != 'Cash': portfolio[-1] *= (1 - fee)
                current_asset = target
                
            # Return
            next_date = dates[i+1]
            r = 0.0
            if current_asset == 'Long':
                r = long_rets.loc[next_date] if next_date in long_rets.index else 0
            elif current_asset == 'Short':
                r = short_rets.loc[next_date] if next_date in short_rets.index else 0
                
            portfolio.append(portfolio[-1]*(1+r))
            
        final_val = portfolio[-1]
        years = (dates[-1] - dates[start_idx]).days / 365.25
        cagr = final_val ** (1/years) - 1
        
        if cagr > best_cagr:
            best_cagr = cagr
            print(f"New Best! McGinley{length}: {final_val:.1f}x (CAGR {cagr*100:.2f}%)")
            
    print(f"Best McGinley Result: {best_cagr*100:.2f}%")

if __name__ == "__main__":
    run_100_final()
