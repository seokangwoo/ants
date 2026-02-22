import yfinance as yf
import pandas as pd
import numpy as np
import ta
from itertools import product

def get_lr_slope_and_forecast(series, window=20):
    slopes = np.zeros(len(series)); forecasts = np.zeros(len(series))
    slopes[:] = np.nan; forecasts[:] = np.nan
    x = np.arange(window)
    vals = series.values
    for i in range(window, len(series)):
        y = vals[i-window:i]
        m, b = np.polyfit(x, y, 1)
        slopes[i] = m
        forecasts[i] = m * (window-1) + b
    return slopes, forecasts

def run_indicator_lr_optimization():
    print("Fetching KOSPI 200 Data for Indicator-LR Fusion...")
    df_signal = yf.download('069500.KS', start='2016-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-01-01', progress=False)
    
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df_signal = df_signal.loc[common]; df_long = df_long.loc[common]; df_short = df_short.loc[common]
    
    close = df_signal['Close']; high = df_signal['High']; low = df_signal['Low']; volume = df_signal['Volume']
    long_rets = df_long['Close'].pct_change(); short_rets = df_short['Close'].pct_change()
    
    # Pre-calculate Base Indicators
    print("Calculating Base Indicators (RSI, Stoch, NATR, ADX)...")
    adx = ta.trend.ADXIndicator(high, low, close).adx() / 10.0
    adx_vals = adx.fillna(0).values
    
    # 67.22% Champion Engine (ADX-Quadratic VWMA)
    A, B, C = 0.6, -35, 170
    vwma_lengths = (A * (adx_vals**2) + B * adx_vals + C).astype(int).clip(20, 300)
    
    # NATR
    tr = pd.concat([high-low, abs(high-close.shift(1)), abs(low-close.shift(1))], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    
    # RSI
    rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
    # StochRSI
    stoch = ta.momentum.StochRSIIndicator(close, window=14).stochrsi_k()
    
    # LR Variants
    print("Calculating LR Variants for Indicators...")
    rsi_slope, rsi_fc = get_lr_slope_and_forecast(rsi.fillna(50), window=14)
    stoch_slope, stoch_fc = get_lr_slope_and_forecast(stoch.fillna(0.5), window=14)
    natr_slope, natr_fc = get_lr_slope_and_forecast(natr.fillna(2.0), window=20)
    
    # COMBINATIONS
    # Modes: 0=Standard, 1=LR_Slope, 2=LR_Forecast
    modes = [0, 1, 2]
    combinations = list(product(modes, modes, modes)) # 3^3 = 27 combos
    
    best_cagr = -999; best_combo = None
    
    print(f"Testing {len(combinations)} Combinations...")
    
    for r_mode, s_mode, n_mode in combinations:
        portfolio = [1.0]; current = None; fee = 0.002
        
        for i in range(250, len(df_signal)-1):
            price = close.iloc[i]
            target = 'Cash'
            
            # --- 1. NATR Filter ---
            n_val = natr.iloc[i]
            is_risk_on = True
            if n_mode == 0: is_risk_on = (n_val <= 5.0)
            elif n_mode == 1: is_risk_on = (natr_slope[i] <= 0) # Volatility trending down
            elif n_mode == 2: is_risk_on = (n_val <= natr_fc[i]) # Volatility below its own trend
            
            if not is_risk_on:
                target = 'Cash'
            else:
                # --- 2. MA Trend ---
                w = vwma_lengths[i]
                pv = (close * volume).iloc[i-w+1:i+1].sum()
                vs = volume.iloc[i-w+1:i+1].sum()
                ma = pv / vs if vs > 0 else np.nan
                
                if pd.isna(ma): target = 'Cash'
                elif price > ma:
                    # --- 3. RSI/Stoch Profit Take ---
                    is_overheated = False
                    
                    # RSI Exit
                    r_over = False
                    if r_mode == 0: r_over = (rsi.iloc[i] > 85)
                    elif r_mode == 1: r_over = (rsi_slope[i] > 0 and rsi.iloc[i] > 70) # Trending up in overbought
                    elif n_mode == 2: r_over = (rsi.iloc[i] > rsi_fc[i] and rsi.iloc[i] > 70)
                    
                    # Stoch Exit
                    s_over = False
                    if s_mode == 0: s_over = (stoch.iloc[i] > 0.9)
                    elif s_mode == 1: s_over = (stoch_slope[i] > 0 and stoch.iloc[i] > 0.8)
                    elif s_mode == 2: s_over = (stoch.iloc[i] > stoch_fc[i] and stoch.iloc[i] > 0.8)
                    
                    if r_over and s_over: target = 'Cash'
                    else: target = 'Long'
                else:
                    target = 'Short'
            
            if target != current:
                portfolio[-1] *= (1 - fee)
                current = target
            
            r = long_rets.iloc[i+1] if current == 'Long' else (short_rets.iloc[i+1] if current == 'Short' else 0.0)
            portfolio.append(portfolio[-1] * (1 + r))
            
        years = (df_signal.index[-1] - df_signal.index[250]).days / 365.25
        cagr = (portfolio[-1]**(1/years) - 1) * 100
        if cagr > best_cagr:
            best_cagr = cagr
            best_combo = (r_mode, s_mode, n_mode)

    print("\n=== Indicator-LR Fusion Results ===")
    print(f"Best CAGR: {best_cagr:.2f}%")
    print(f"Best Combo (RSI, Stoch, NATR modes): {best_combo}")
    print(f"(Mode 0: Standard, 1: Slope, 2: Forecast)")
    print(f"Champion CAGR: 67.22%")

if __name__ == "__main__":
    run_indicator_lr_optimization()
