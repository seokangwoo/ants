import yfinance as yf
import pandas as pd
import numpy as np
import math
import sys

def calculate_hma(series, length):
    series = pd.Series(series)
    def wma(s, l):
        weights = np.arange(1, l + 1)
        return s.rolling(l).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    
    half_length = int(length / 2)
    sqrt_length = int(math.sqrt(length))
    
    wma_half = wma(series, half_length)
    wma_full = wma(series, length)
    
    diff = 2 * wma_half - wma_full
    return wma(diff, sqrt_length)

def calculate_zlma(series, length):
    series = pd.Series(series)
    lag = int((length - 1) / 2)
    lag_series = series.shift(lag)
    data_to_smooth = series + (series - lag_series)
    return data_to_smooth.ewm(span=length).mean()

def run_100_percent_backtest():
    print("Fetching Data (via yfinance)...")
    try:
        df_signal = yf.download('069500.KS', start='2010-01-01', progress=False)
        df_long = yf.download('122630.KS', start='2010-01-01', progress=False)
        df_short = yf.download('252670.KS', start='2016-09-01', progress=False)
    except Exception as e:
        print(f"Error downloading: {e}")
        return

    # Check Columns (YF often returns MultiIndex 'Price', 'Ticker')
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)

    # Intersection
    common_idx = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    
    if len(common_idx) < 100:
        print(f"Error: Not enough common data points. Len: {len(common_idx)}")
        return

    print(f"Data Points: {len(common_idx)}")

    df = pd.DataFrame()
    df['Close'] = df_signal.loc[common_idx]['Close']
    df['Long'] = df_long.loc[common_idx]['Close']
    df['Short'] = df_short.loc[common_idx]['Close']
    
    # Pre-calculate N-Vol (Using available High/Low)
    # NATR
    high = df_signal.loc[common_idx]['High']
    low = df_signal.loc[common_idx]['Low']
    close = df['Close']
    prev_close = close.shift(1)
    
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    dates = df.index
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    prices = close.values
    
    start_idx = 250
    
    # Experiment Grid
    ma_types = ['HMA', 'ZLMA'] # Faster MAs
    intercepts = [120, 140, 160]
    slopes = [20, 25, 30]
    
    # Also test RSI Dynamic Period? 
    # Let's add RSI Dynamic Period to the mix later if this fails.
    
    best_cagr = -999
    best_config = ""
    
    print("Optimization Loop...")
    
    for ma_type in ma_types:
        print(f"Processing {ma_type}...")
        mas = {}
        for w in range(10, 251):
            if ma_type == 'HMA': mas[w] = calculate_hma(close, w)
            else: mas[w] = calculate_zlma(close, w)
            
        for intercept in intercepts:
            for slope in slopes:
                portfolio = [1.0]
                fee = 0.002
                current_asset = 'Cash'
                
                for i in range(start_idx, len(dates)-1):
                    curr_natr = natrs[i]
                    price = prices[i]
                    
                    if pd.isna(curr_natr):
                        ma_len = intercept
                    else:
                        ma_len = int(intercept - (slope * curr_natr))
                        
                    ma_len = max(20, min(ma_len, 250))
                    
                    # Logic
                    ma_val = mas[ma_len].iloc[i]
                    
                    if pd.isna(ma_val): target = 'Cash'
                    elif price > ma_val: 
                        target = 'Long'
                        # RSI Filter test? Or keep pure? Keep pure first.
                    else: 
                        target = 'Short'
                        
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
                    
                    if pd.isna(r): r=0
                    portfolio.append(portfolio[-1]*(1+r))
                    
                final_val = portfolio[-1]
                years = (dates[-1] - dates[start_idx]).days / 365.25
                cagr = final_val ** (1/years) - 1
                
                if cagr > best_cagr:
                    best_cagr = cagr
                    best_config = f"{ma_type} Int{intercept} Slope{slope}"
                    print(f"New Best! {best_config}: {final_val:.1f}x (CAGR {cagr*100:.2f}%)")
                    
    print(f"=== Experiment Result ===")
    print(f"Best Config: {best_config}")
    print(f"CAGR: {best_cagr*100:.2f}%")

if __name__ == "__main__":
    run_100_percent_backtest()
