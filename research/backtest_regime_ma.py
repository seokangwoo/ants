import FinanceDataReader as fdr
import pandas as pd
import numpy as np

def run_regime_backtest():
    print("Fetching Data...")
    df_signal = fdr.DataReader('069500', '2010-01-01') # KODEX 200
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    df_short = fdr.DataReader('252670', '2016-01-01')['Close']
    
    # Align
    df = pd.DataFrame({'Close': df_signal['Close'], 'Long': df_long, 'Short': df_short}).dropna()
    dates = df.index
    
    # Calculate Volatility (Annualized)
    df['Ret'] = df['Close'].pct_change()
    df['Vol'] = df['Ret'].rolling(window=20).std() * np.sqrt(252)
    
    # Pre-calculate MAs
    mas = {}
    for w in [20, 40, 50, 60, 90, 113, 120, 150, 200]:
        mas[w] = df['Close'].rolling(window=w).mean()
        
    print(f"Data Range: {dates[0]} ~ {dates[-1]}")
    
    # Grid Search
    # Low Vol MA (Stable) -> Usually Slow?
    # High Vol MA (Crisis) -> Usually Fast?
    
    low_vol_mas = [60, 90, 113, 120, 150]
    high_vol_mas = [20, 40, 50, 60]
    vol_thresholds = [0.10, 0.15, 0.20, 0.25]
    
    best_cagr = -999
    best_params = None
    
    print("Optimization Loop...")
    
    for lv_ma in low_vol_mas:
        for hv_ma in high_vol_mas:
            if lv_ma == hv_ma: continue
            
            for thresh in vol_thresholds:
                # Backtest
                portfolio = [1.0]
                fee = 0.002
                current_asset = 'Cash'
                
                long_rets = df['Long'].pct_change()
                short_rets = df['Short'].pct_change()
                
                start_idx = max(lv_ma, hv_ma)
                # Need to align loop start
                
                prices = df['Close'].values
                vols = df['Vol'].values
                
                # Pre-fetch MA arrays
                ma_low = mas[lv_ma].values
                ma_high = mas[hv_ma].values
                
                valid_run = True
                
                # Loop
                # Optimization: We can vectorise signal generation?
                # Signal T:
                # If Vol[T] < Thresh: Use MA_Low[T]
                # Else: Use MA_High[T]
                
                # Let's vectorize efficiently
                # active_ma = np.where(df['Vol'] < thresh, mas[lv_ma], mas[hv_ma])
                # signal = np.where(df['Close'] > active_ma, 1, -1)
                
                # BUT: To calculate daily returns we need to iterate for fee calculation?
                # We can vectorise fees too if we detect signal changes.
                
                # Construct combined MA series
                active_ma = np.where(df['Vol'] < thresh, mas[lv_ma], mas[hv_ma])
                
                # Shift logic: We trade AT CLOSE? Or Open next day?
                # Using Trade at Close logic (signal generated at Close T, trade at Close T).
                # Returns are from Close T to Close T+1.
                
                # Signal: 1 (Long, 122630), -1 (Short, 252670)
                # Apply Threshold? Let's stick to 0.5% default or 0% for now to test pure logic.
                # User asked for MA length adjustment.
                
                signals = np.where(df['Close'] > active_ma, 1, -1)
                
                # Calculate Strategy Returns
                # Position[T] holds return of T+1
                # Check for signal changes
                
                # To be precise with fees and asset switching:
                # Iterate is safer for complex asset logic (Long/Short/Cash)
                
                for i in range(start_idx, len(dates)-1):
                    # date = dates[i]
                    next_date = dates[i+1]
                    
                    price = prices[i]
                    vol = vols[i]
                    
                    # Regime Switch
                    if vol < thresh:
                        limit = ma_low[i]
                    else:
                        limit = ma_high[i]
                        
                    if pd.isna(limit): 
                        target = 'Cash'
                    elif price > limit:
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
                        if next_date in long_rets.index: r = long_rets.loc[next_date]
                    elif current_asset == 'Short':
                        if next_date in short_rets.index: r = short_rets.loc[next_date]
                        
                    if pd.isna(r): r = 0.0
                    portfolio.append(portfolio[-1] * (1 + r))
                    
                final_val = portfolio[-1]
                years = (dates[-1] - dates[start_idx]).days / 365.25
                if years <= 0: continue
                cagr = final_val ** (1/years) - 1
                
                if cagr > best_cagr:
                    best_cagr = cagr
                    best_params = (lv_ma, hv_ma, thresh)
                    print(f"New Best! LowVol_MA{lv_ma}, HighVol_MA{hv_ma}, Thresh{thresh}: {final_val:.1f}x (CAGR {cagr*100:.1f}%)")
                    
    print(f"\n=== Best Regime Switching Strategy ===")
    print(f"Low Vol MA: {best_params[0]}")
    print(f"High Vol MA: {best_params[1]}")
    print(f"Vol Threshold: {best_params[2]}")
    print(f"CAGR: {best_cagr*100:.2f}%")

if __name__ == "__main__":
    run_regime_backtest()
