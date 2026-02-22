import yfinance as yf
import pandas as pd
import numpy as np
import ta

def run_dynamic_lr_optimization():
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
    high = df_signal['High']
    low = df_signal['Low']
    long_rets = df_long['Close'].pct_change()
    short_rets = df_short['Close'].pct_change()
    
    print("Pre-calculating ADX and NATR...")
    adx_obj = ta.trend.ADXIndicator(high, low, close, window=14)
    adx = adx_obj.adx() / 10.0
    adx_vals = adx.fillna(0).values
    
    tr = pd.concat([high-low, abs(high-close.shift(1)), abs(low-close.shift(1))], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values

    # Grid Search Params
    A_list = [0.4, 0.6, 0.8]
    B_list = [-30, -35, -40]
    C_list = [150, 170, 190]
    
    best_cagr = -999
    best_params = None
    
    print(f"Starting Grid Search (27 combinations) for Dynamic LR...")
    
    for A in A_list:
        for B in B_list:
            for C in C_list:
                # Dynamic LR Window lengths
                lengths = (A * (adx_vals**2) + B * adx_vals + C).astype(int).clip(20, 300)
                
                portfolio = [1.0]
                current = None
                fee = 0.002
                
                # To speed up, we pre-calculate the logic
                # Linear Regression involves fitting a slope on a window.
                # Since 'window' is dynamic, we must do it day-by-day.
                
                for i in range(250, len(df_signal)-1):
                    price = close.iloc[i]
                    c_natr = natrs[i]
                    
                    # 1. Crash Guard
                    if not pd.isna(c_natr) and c_natr > 5.0:
                        target = 'Cash'
                    else:
                        w = lengths[i]
                        # LR Forecast calculation for day i
                        y_slice = close.values[i-w:i]
                        x_slice = np.arange(w)
                        m, b = np.polyfit(x_slice, y_slice, 1)
                        forecast = m * (w-1) + b
                        
                        target = 'Long' if price > forecast else 'Short'
                        
                    if target != current:
                        portfolio[-1] *= (1 - fee)
                        current = target
                    
                    r = long_rets.iloc[i+1] if current == 'Long' else (short_rets.iloc[i+1] if current == 'Short' else 0.0)
                    portfolio.append(portfolio[-1] * (1 + r))
                
                years = (df_signal.index[-1] - df_signal.index[250]).days / 365.25
                cagr = (portfolio[-1]**(1/years) - 1) * 100
                
                if cagr > best_cagr:
                    best_cagr = cagr
                    best_params = (A, B, C)
                
                # print(f"  A={A}, B={B}, C={C}: {cagr:.2f}%")

    print("\n=== Optimized Dynamic LR Engine Results ===")
    print(f"Best CAGR: {best_cagr:.2f}%")
    print(f"Best Params: A={best_params[0]}, B={best_params[1]}, C={best_params[2]}")
    print(f"Current VWMA Champion: 67.22%")

if __name__ == "__main__":
    run_dynamic_lr_optimization()
