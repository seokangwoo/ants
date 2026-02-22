import FinanceDataReader as fdr
import pandas as pd
import numpy as np

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean() # SMMA usually, but Simple is fast
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_final_push_backtest():
    print("Fetching Data...")
    df_signal = fdr.DataReader('069500', '2010-01-01') # KODEX 200
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    df_short = fdr.DataReader('252670', '2016-01-01')['Close']
    
    # Align
    df = pd.DataFrame({'Close': df_signal['Close'], 'High': df_signal['High'], 'Low': df_signal['Low'],
                       'Long': df_long, 'Short': df_short}).dropna()
    dates = df.index
    
    # 1. Base Strategy Indicators (NATR)
    # NATR Calculation
    df['Prev_Close'] = df['Close'].shift(1)
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Prev_Close'])
    df['L-PC'] = abs(df['Low'] - df['Prev_Close'])
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(window=20).mean()
    df['NATR'] = (df['ATR'] / df['Close']) * 100
    
    # RSI
    df['RSI'] = calculate_rsi(df['Close'], 14)
    
    # Pre-calculate MAs
    mas = {}
    for w in range(20, 251):
        mas[w] = df['Close'].rolling(window=w).mean()
        
    print(f"Data Range: {dates[0]} ~ {dates[-1]}")
    
    # Grid Search Filters
    # Base: Int=140, Slope=25 (Benchmark 44%)
    base_int = 140
    base_slope = 25
    
    # Test Parameters
    rsi_thresholds = [70, 75, 80, 85, 999] # 999 = Off
    vol_cash_limits = [3.0, 4.0, 5.0, 6.0, 999.0] # 999 = Off
    
    best_cagr = -999
    best_config = None
    
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    prices = df['Close'].values
    natrs = df['NATR'].values
    rsis = df['RSI'].values
    
    start_idx = 250
    
    print("Optimization Loop...")
    
    for rsi_top in rsi_thresholds:
        for vol_limit in vol_cash_limits:
            
            portfolio = [1.0]
            fee = 0.002
            current_asset = 'Cash'
            
            for i in range(start_idx, len(dates)-1):
                next_date = dates[i+1]
                price = prices[i]
                natr = natrs[i]
                rsi = rsis[i]
                
                # 1. Base Signal (Dynamic MA)
                if pd.isna(natr): 
                    ma_len = base_int
                else:
                    ma_len = int(base_int - (base_slope * natr))
                ma_len = max(20, min(ma_len, 250))
                
                ma_val = mas[ma_len].iloc[i]
                
                if pd.isna(ma_val): target = 'Cash'
                elif price > ma_val: target = 'Long'
                else: target = 'Short'
                
                # 2. RSI Filter
                # If Long Signal but RSI > Top -> Cash? Or Hold?
                # Usually RSI > 70 is strong momentum, but > 80 is danger.
                # Avoid Opening New Long if RSI > Top?
                # Avoid Holding if RSI > Top?
                # Strategy: If RSI > Top, force Cash (Profit Take).
                if target == 'Long' and rsi > rsi_top:
                    target = 'Cash'
                if target == 'Short' and rsi < (100 - rsi_top):
                    target = 'Cash'
                    
                # 3. Vol Cash Filter
                # If NATR > Limit, Market is broken. Cash.
                if natr > vol_limit:
                    target = 'Cash'
                    
                # Trade
                if target != current_asset:
                    if current_asset != 'Cash':
                         portfolio[-1] *= (1 - fee)
                    current_asset = target
                    
                # Return
                r = 0.0
                if current_asset == 'Long':
                    if next_date in long_rets.index: r = long_rets.loc[next_date]
                elif current_asset == 'Short':
                    if next_date in short_rets.index: r = short_rets.loc[next_date]
                    
                if pd.isna(r): r = 0.0
                portfolio.append(portfolio[-1] * (1 + r))
                
            final_val = portfolio[-1]
            years = (dates[-1] - dates[start_idx]).days / 365.25
            if years <= 0: continue
            cagr = final_val ** (1/years) - 1
            
            # print(f"RSI{rsi_top}, Vol{vol_limit}: {cagr*100:.1f}%")
            
            if cagr > best_cagr:
                best_cagr = cagr
                best_config = (rsi_top, vol_limit)
                print(f"New Best! RSI_Limit{rsi_top}, Vol_Limit{vol_limit}: {final_val:.1f}x (CAGR {cagr*100:.2f}%)")
                
    print(f"\n=== Final Optimized Strategy ===")
    print(f"Base: MA = 140 - 25 * NATR")
    print(f"RSI Limit: {best_config[0]}")
    print(f"Vol Cash Limit: {best_config[1]}")
    print(f"CAGR: {best_cagr*100:.2f}%")

if __name__ == "__main__":
    run_final_push_backtest()
