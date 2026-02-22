import yfinance as yf
import pandas as pd
import numpy as np

def run_pure_battle():
    print("Fetching KOSPI 200 Data...")
    df_signal = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df_signal = df_signal.loc[common]
    df_long = df_long.loc[common]
    df_short = df_short.loc[common]
    
    close = df_signal['Close']
    volume = df_signal['Volume']
    long_rets = df_long['Close'].pct_change()
    short_rets = df_short['Close'].pct_change()
    
    results = []

    # Optimization range: 20 to 200 (Step 10)
    windows = range(20, 201, 10)

    print("\n--- Phase 1: Optimizing Pure VWMA ---")
    best_vwma_cagr = -999
    best_vwma_win = 0
    pv = close * volume

    for w in windows:
        portfolio = [1.0]
        current = None
        fee = 0.002
        
        # Calculate VWMA series
        vwma = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
        for i in range(w, len(df_signal)-1):
            price = close.iloc[i]
            ma = vwma.iloc[i]
            target = 'Long' if price > ma else 'Short'
            
            if target != current:
                portfolio[-1] *= (1 - fee)
                current = target
            
            r = long_rets.iloc[i+1] if current == 'Long' else short_rets.iloc[i+1]
            portfolio.append(portfolio[-1] * (1 + r))
        
        years = (df_signal.index[-1] - df_signal.index[w]).days / 365.25
        cagr = (portfolio[-1]**(1/years) - 1) * 100
        if cagr > best_vwma_cagr:
            best_vwma_cagr = cagr
            best_vwma_win = w
        # print(f"  VWMA({w}): {cagr:.2f}%")

    print("\n--- Phase 2: Optimizing Pure Linear Regression ---")
    # LR Logic: Price vs LR Forecast (Forecast = Price at the end of the fitted line)
    best_lr_cagr = -999
    best_lr_win = 0
    
    for w in windows:
        portfolio = [1.0]
        current = None
        fee = 0.002
        
        # Calculate LR Forecast series
        # LR Forecast is basically the price on the regression line at the current point
        forecasts = np.zeros(len(close)); forecasts[:] = np.nan
        x = np.arange(w)
        for i in range(w, len(close)):
            y = close.values[i-w:i]
            m, b = np.polyfit(x, y, 1)
            forecasts[i] = m * (w-1) + b # Last point on the line
        
        for i in range(w, len(df_signal)-1):
            price = close.iloc[i]
            f = forecasts[i]
            target = 'Long' if price > f else 'Short'
            
            if target != current:
                portfolio[-1] *= (1 - fee)
                current = target
            
            r = long_rets.iloc[i+1] if current == 'Long' else short_rets.iloc[i+1]
            portfolio.append(portfolio[-1] * (1 + r))
            
        years = (df_signal.index[-1] - df_signal.index[w]).days / 365.25
        cagr = (portfolio[-1]**(1/years) - 1) * 100
        if cagr > best_lr_cagr:
            best_lr_cagr = cagr
            best_lr_win = w
        # print(f"  LR({w}): {cagr:.2f}%")

    print("\n=== THE PURE BATTLE RESULTS ===")
    print(f"CHAMPION VWMA (Fixed {best_vwma_win}): {best_vwma_cagr:.2f}%")
    print(f"CHAMPION LR   (Fixed {best_lr_win}): {best_lr_cagr:.2f}%")
    
    winner = "VWMA" if best_vwma_cagr > best_lr_cagr else "Linear Regression"
    print(f"\nWINNER: {winner}")

if __name__ == "__main__":
    run_pure_battle()
