import yfinance as yf
import pandas as pd
import numpy as np
import quantstats as qs

def run_lr_backtest():
    print("Fetching KOSPI 200 Data for Linear Regression Analysis...")
    # Signal: KODEX 200
    df_signal = yf.download('069500.KS', start='2016-01-01', progress=False)
    # Long: KODEX Leverage (2x)
    df_long = yf.download('122630.KS', start='2016-01-01', progress=False)
    # Short: KODEX Inverse 2X (2x)
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
    
    # 1. Linear Regression Indicators
    # We fit a line to the last N days
    def get_lr_slope_and_forecast(series, window=90):
        # Rolling polyfit is slow in pandas apply, so we'll use a loop or optimized rolling
        # For 10 years, loop is fine.
        slopes = np.zeros(len(series))
        forecasts = np.zeros(len(series))
        slopes[:] = np.nan
        forecasts[:] = np.nan
        
        x = np.arange(window)
        for i in range(window, len(series)):
            y = series.values[i-window:i]
            # y = mx + b
            m, b = np.polyfit(x, y, 1)
            slopes[i] = m
            forecasts[i] = m * window + b # Forecast for tomorrow
        return slopes, forecasts

    print("Calculating Linear Regression (Window=90)...")
    lr_slopes, lr_forecasts = get_lr_slope_and_forecast(close, window=90)
    
    # 2. Risk Filters (NATR)
    prev_close = close.shift(1)
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    # Portfolio Sim
    portfolio = [1.0]
    current_asset = 'Cash'
    fee = 0.002
    
    long_rets = df_long['Close'].pct_change()
    short_rets = df_short['Close'].pct_change()
    
    dates = df_signal.index
    start_idx = 91 # After LR window
    
    for i in range(start_idx, len(dates)-1):
        price = close.iloc[i]
        slope = lr_slopes[i]
        forecast = lr_forecasts[i]
        c_natr = natrs[i]
        
        target = 'Cash'
        
        # Linear Regression Logic
        # Slope > 0 (Trend is up) AND Price > LR Forecast (Momentum is strong)
        if not pd.isna(c_natr) and c_natr > 5.0:
            target = 'Cash'
        elif not pd.isna(slope) and slope > 0:
            target = 'Long'
        elif not pd.isna(slope) and slope <= 0:
            target = 'Short'
            
        if target != current_asset:
            portfolio[-1] *= (1 - fee)
            current_asset = target
            
        r = long_rets.iloc[i+1] if current_asset == 'Long' else (short_rets.iloc[i+1] if current_asset == 'Short' else 0.0)
        portfolio.append(portfolio[-1] * (1 + r))
        
    final_p = portfolio[-1]
    years = (dates[-1] - dates[start_idx]).days / 365.25
    cagr = (final_p**(1/years) - 1) * 100
    
    print(f"\n[Linear Regression Strategy] Result:")
    print(f"Final Capital: {final_p:.2f}x")
    print(f"CAGR: {cagr:.2f}%")
    
    # Detailed Report
    strategy_rets = pd.Series(portfolio, index=dates[start_idx:]).pct_change().dropna()
    strategy_rets.index = pd.to_datetime(strategy_rets.index).tz_localize(None)
    benchmark_rets = df_signal['Close'].pct_change().loc[strategy_rets.index]
    benchmark_rets.index = pd.to_datetime(benchmark_rets.index).tz_localize(None)
    
    print("Generating LR Comparison Report...")
    qs.reports.html(strategy_rets, benchmark=benchmark_rets, output='research/lr_comparison.html', title='Linear Regression Strategy: KOSPI 200')

if __name__ == "__main__":
    run_lr_backtest()
