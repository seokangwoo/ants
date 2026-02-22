import yfinance as yf
import pandas as pd
import numpy as np
import quantstats as qs
from strategy import FinalBoostedStrategy

def produce_html_report():
    print("Fetching Data for Report...")
    # KOSPI 200, Leverage, Inverse
    df_signal = yf.download('069500.KS', start='2010-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2010-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-09-01', progress=False)
    
    # Flatten MultiIndex
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    # Align
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df_signal = df_signal.loc[common]
    df_long = df_long.loc[common]
    df_short = df_short.loc[common]
    
    # Run Strategy
    # Fully Dynamic Champion Config
    # Intercept=140, Slope=25, RefVol=2.0
    strategy = FinalBoostedStrategy(
        A=0.6, 
        B=-35, 
        C=170, 
        rsi_limit=85, 
        stoch_limit=0.9, 
        vol_limit=5.0, 
        ref_vol=2.0
    )
    
    print("Running Strategy...")
    portfolio_vals = [1.0]
    dates = df_signal.index
    
    current_asset = 'Cash'
    fee = 0.002
    
    close = df_signal['Close']
    high = df_signal['High']
    low = df_signal['Low']
    volume = df_signal['Volume']
    prev_close = close.shift(1)
    
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    # VWMA Universe
    vwmas = {}
    pv = close * volume
    for w in range(20, 251):
        vwmas[w] = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
    updated_ma_len = 140 - (25 * natr)
    updated_ma_len = updated_ma_len.fillna(140).astype(int).clip(20, 250)
    
    # Dynamic RSI
    vals = close.values
    rsi_out = np.zeros(len(vals))
    rsi_out[:] = np.nan
    avg_gain = 0.0; avg_loss = 0.0
    
    ref_vol = 2.0
    
    for i in range(1, len(vals)):
        c_natr = natrs[i]
        if pd.isna(c_natr) or c_natr == 0: per = 14
        else: per = int(14 * (ref_vol / c_natr))
        per = max(4, min(per, 60))
        alpha = 1.0 / per
        
        change = vals[i] - vals[i-1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        
        if i == 1:
            avg_gain = gain
            avg_loss = loss
        else:
            avg_gain = (avg_gain * (1 - alpha)) + (gain * alpha)
            avg_loss = (avg_loss * (1 - alpha)) + (loss * alpha)
            
        if avg_loss == 0: rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi_out[i] = rsi
        
    # Dynamic StochRSI
    stoch_k_out = np.zeros(len(vals))
    stoch_k_out[:] = np.nan
    
    for i in range(len(vals)):
        c_natr = natrs[i]
        if pd.isna(c_natr) or c_natr == 0: per = 14
        else: per = int(14 * (ref_vol / c_natr))
        per = max(4, min(per, 60))
        
        if i < per: continue
        w_slice = rsi_out[i-per+1 : i+1]
        w_slice = w_slice[~np.isnan(w_slice)]
        if len(w_slice) == 0: s = 0.5
        else:
            mn = np.min(w_slice)
            mx = np.max(w_slice)
            if mx == mn: s = 0.5
            else: s = (rsi_out[i] - mn) / (mx - mn)
        stoch_k_out[i] = s
        
    stoch_k_series = pd.Series(stoch_k_out).rolling(3).mean().values
    
    # Portfolio Loop
    long_rets = df_long['Close'].pct_change()
    short_rets = df_short['Close'].pct_change()
    prices = close.values
    daily_returns = []
    
    start_idx = 250
    dates = dates[start_idx:]
    
    portfolio = [1.0]
    
    for i in range(start_idx, len(vals)-1):
        c_natr = natrs[i]
        price = prices[i]
        
        target = 'Cash'
        
        if not pd.isna(c_natr) and c_natr > 5.0:
            target = 'Cash'
        else:
            ma_len = int(updated_ma_len.iloc[i])
            ma_val = vwmas[ma_len].iloc[i]
            
            if pd.isna(ma_val): target = 'Cash'
            elif price > ma_val:
                # Bull
                d_rsi = rsi_out[i]
                d_stoch = stoch_k_series[i]
                
                # Exit if BOTH RSI>85 and Stoch>0.8
                if (d_rsi > 85) and (d_stoch > 0.8):
                    target = 'Cash'
                else:
                    target = 'Long'
            else:
                target = 'Short'
                
        if target != current_asset:
            if current_asset != 'Cash': portfolio[-1] *= (1 - fee)
            current_asset = target
            
        next_date = dates[i-start_idx+1]
        r = 0.0
        if current_asset == 'Long': r = long_rets.get(next_date, 0)
        elif current_asset == 'Short': r = short_rets.get(next_date, 0)
        
        daily_returns.append(r)
        portfolio.append(portfolio[-1]*(1+r))
        
    rets_series = pd.Series(daily_returns, index=dates[1:])
    rets_series.index = pd.to_datetime(rets_series.index).tz_localize(None)
    
    # Calculates Benchmark Returns (069500.KS - KOSPI 200)
    # df_signal is 069500.KS
    benchmark_rets = df_signal['Close'].pct_change().dropna()
    benchmark_rets.index = pd.to_datetime(benchmark_rets.index).tz_localize(None)
    
    # Align Benchmark to Strategy
    benchmark_rets = benchmark_rets[benchmark_rets.index.isin(rets_series.index)]
    
    print("Generating HTML Report with Benchmark...")
    qs.reports.html(
        rets_series, 
        benchmark=benchmark_rets, 
        output='strategy_report.html', 
        title='KOSPI Fully Dynamic Strategy vs KOSPI 200'
    )
    print("Report Saved: strategy_report.html")

if __name__ == "__main__":
    produce_html_report()
