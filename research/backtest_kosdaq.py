import yfinance as yf
import pandas as pd
import numpy as np
import ta
import quantstats as qs

def run_kosdaq_backtest():
    print("Fetching KOSDAQ 150 Data...")
    # KODEX KOSDAQ 150 (Signal Proxy)
    df_signal = yf.download('229200.KS', start='2016-01-01', progress=False)
    # KODEX KOSDAQ 150 Leverage (2x)
    df_long = yf.download('233740.KS', start='2016-01-01', progress=False)
    # KODEX KOSDAQ 150 Inverse (1x or 2x?) 
    # 251340 is Inverse. Usually 1x. KOSDAQ doesn't have a dominant 2x Inverse like KOSPI's 252670.
    # We will use 251340.KS for short.
    df_short = yf.download('251340.KS', start='2016-01-01', progress=False)
    
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
    volume = df_signal['Volume']
    prev_close = close.shift(1)
    
    # ADX Calculation
    print("Calculating ADX...")
    adx_obj = ta.trend.ADXIndicator(high, low, close, window=14)
    adx = adx_obj.adx()
    adx_metric = adx / 10.0
    adx_vals = adx_metric.fillna(0).values
    
    # NATR Calculation
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    # Dynamic RSI
    print("Calculating Dynamic Indicators...")
    vals = close.values
    rsi_out = np.zeros(len(vals)); rsi_out[:] = np.nan
    avg_gain = 0.0; avg_loss = 0.0; ref_vol = 2.0
    
    for i in range(1, len(vals)):
        c_natr = natrs[i]
        per = int(14 * (ref_vol / c_natr)) if not pd.isna(c_natr) and c_natr != 0 else 14
        per = max(4, min(per, 60))
        alpha = 1.0 / per
        change = vals[i] - vals[i-1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        if i == 1: avg_gain = gain; avg_loss = loss
        else:
            avg_gain = (avg_gain * (1 - alpha)) + (gain * alpha)
            avg_loss = (avg_loss * (1 - alpha)) + (loss * alpha) 
        if avg_loss == 0: rsi = 100.0
        else: rsi = 100.0 - (100.0 / (1.0 + (avg_gain/avg_loss)))
        rsi_out[i] = rsi
        
    # Dynamic StochRSI
    stoch_k_out = np.zeros(len(vals)); stoch_k_out[:] = np.nan
    for i in range(len(vals)):
        c_natr = natrs[i]
        per = int(14 * (ref_vol / c_natr)) if not pd.isna(c_natr) and c_natr != 0 else 14
        per = max(4, min(per, 60))
        if i < per: continue
        w = rsi_out[i-per+1 : i+1]
        w = w[~np.isnan(w)]
        if len(w) == 0: s = 0.5
        else:
            mn = np.min(w); mx = np.max(w)
            s = 0.5 if mx == mn else (rsi_out[i] - mn) / (mx - mn)
        stoch_k_out[i] = s
    stoch_k_series = pd.Series(stoch_k_out).rolling(3).mean().values
    
    # VWMA Calculation
    pv = close * volume
    vwma_cache = {}
    
    # Strategy Params (ADX Peak)
    A, B, C = 0.6, -35, 170
    calc_len = (A * (adx_vals**2) + B * adx_vals + C).astype(int).clip(20, 300)
    
    portfolio = [1.0]
    current_asset = 'Cash'
    fee = 0.002
    
    long_rets = df_long['Close'].pct_change()
    short_rets = df_short['Close'].pct_change()
    
    dates = df_signal.index
    start_idx = 100
    
    for i in range(start_idx, len(dates)-1):
        price = vals[i]
        c_natr = natrs[i]
        target = 'Cash'
        
        if not pd.isna(c_natr) and c_natr > 5.0:
            target = 'Cash'
        else:
            mlen = calc_len[i]
            ma_val = (pv.rolling(window=mlen).mean() / volume.rolling(window=mlen).mean()).iloc[i]
            
            if pd.isna(ma_val): target = 'Cash'
            elif price > ma_val:
                if (rsi_out[i] > 85) and (stoch_k_series[i] > 0.9): target = 'Cash'
                else: target = 'Long'
            else: target = 'Short'
            
        if target != current_asset:
            portfolio[-1] *= (1 - fee)
            current_asset = target
            
        r = long_rets.iloc[i+1] if current_asset == 'Long' else (short_rets.iloc[i+1] if current_asset == 'Short' else 0.0)
        portfolio.append(portfolio[-1] * (1 + r))
        
    strategy_rets = pd.Series(portfolio, index=dates[start_idx:]).pct_change().dropna()
    strategy_rets.index = pd.to_datetime(strategy_rets.index).tz_localize(None)
    
    benchmark_rets = df_signal['Close'].pct_change().loc[strategy_rets.index]
    benchmark_rets.index = pd.to_datetime(benchmark_rets.index).tz_localize(None)
    
    print("Generating KOSDAQ Comparison Report...")
    qs.reports.html(strategy_rets, benchmark=benchmark_rets, output='research/kosdaq_comparison.html', title='ADX Strategy: KOSDAQ 150 Backtest')
    
    final_p = portfolio[-1]
    years = (dates[-1] - dates[start_idx]).days / 365.25
    cagr = (final_p**(1/years) - 1) * 100
    
    print(f"\nKOSDAQ Results:")
    print(f"Final Capital: {final_p:.2f}x")
    print(f"CAGR: {cagr:.2f}%")

if __name__ == "__main__":
    run_kosdaq_backtest()
