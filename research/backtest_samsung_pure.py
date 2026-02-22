import yfinance as yf
import pandas as pd
import numpy as np
import ta
import quantstats as qs

def run_samsung_pure_comparison():
    print("Fetching Samsung Electronics (005930.KS) Data...")
    # Samsung Electronics
    df = yf.download('005930.KS', start='2006-01-01', progress=False)
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df = df.dropna()
    
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']
    prev_close = close.shift(1)
    
    # ADX (The Engine)
    print("Calculating ADX...")
    adx_obj = ta.trend.ADXIndicator(high, low, close, window=14)
    adx = adx_obj.adx()
    adx_metric = adx / 10.0
    adx_vals = adx_metric.fillna(0).values
    
    # NATR (For Indicators & Crash Guard)
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    # Dynamic RSI
    print("Calculating Dynamic Indicators...")
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
        if i == 1: avg_gain = gain; avg_loss = loss
        else:
            avg_gain = (avg_gain * (1 - alpha)) + (gain * alpha)
            avg_loss = (avg_loss * (1 - alpha)) + (loss * alpha) 
        if avg_loss == 0: rsi = 100.0
        else: rsi = 100.0 - (100.0 / (1.0 + (avg_gain/avg_loss)))
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
        w = rsi_out[i-per+1 : i+1]
        w = w[~np.isnan(w)]
        if len(w) == 0: s = 0.5
        else:
            mn = np.min(w); mx = np.max(w)
            if mx == mn: s = 0.5
            else: s = (rsi_out[i] - mn) / (mx - mn)
        stoch_k_out[i] = s
    stoch_k_series = pd.Series(stoch_k_out).rolling(3).mean().values
    
    # VWMA pre-calc
    pv = close * volume
    
    # Strategy Params (ADX Peak)
    A, B, C = 0.6, -35, 170
    calc_len = A * (adx_vals**2) + B * adx_vals + C
    calc_len = calc_len.astype(int).clip(20, 300)
    
    daily_rets = []
    portfolio = [1.0]
    current_asset = 'Cash' # Only 'Long' or 'Cash'
    fee = 0.002 # Slightly higher fee for individual stock spread
    
    dates = df.index
    rets_series = df['Close'].pct_change()
    
    start_idx = 300
    
    for i in range(start_idx, len(dates)-1):
        price = vals[i]
        c_natr = natrs[i]
        target = 'Cash'
        
        # Signal Logic
        if not pd.isna(c_natr) and c_natr > 5.0:
            target = 'Cash'
        else:
            ma_len = calc_len[i]
            # Calc VWMA for this length
            ma_val = (pv.rolling(window=ma_len).mean() / volume.rolling(window=ma_len).mean()).iloc[i]
            
            if pd.isna(ma_val): target = 'Cash'
            elif price > ma_val:
                # Bull Check
                if (rsi_out[i] > 85) and (stoch_k_series[i] > 0.9):
                    target = 'Cash'
                else:
                    target = 'Long'
            else:
                target = 'Cash'
        
        # Trade
        if target != current_asset:
            portfolio[-1] *= (1 - fee)
            current_asset = target
            
        r = rets_series.iloc[i+1] if current_asset == 'Long' else 0.0
        portfolio.append(portfolio[-1] * (1 + r))
        daily_rets.append(r)

    # Strategy Performance
    strategy_rets = pd.Series(daily_rets, index=dates[start_idx+1:])
    strategy_rets.index = pd.to_datetime(strategy_rets.index).tz_localize(None)
    
    # Benchmarking (Buy & Hold)
    benchmark_rets = rets_series.iloc[start_idx+1:]
    benchmark_rets.index = pd.to_datetime(benchmark_rets.index).tz_localize(None)
    
    print("Generating Comparison Report...")
    qs.reports.html(
        strategy_rets, 
        benchmark=benchmark_rets, 
        output='samsung_comparison.html',
        title='Strategy (Samsung Only) vs Buy & Hold (20 Years)'
    )
    
    final_p = portfolio[-1]
    bh_p = (1 + benchmark_rets).prod()
    
    print(f"\nResult Over {len(daily_rets)} Days:")
    print(f"Strategy Final: {final_p:.2f}x")
    print(f"Buy & Hold Final: {bh_p:.2f}x")
    print(f"Strategy CAGR: {(final_p**(365.25/((dates[-1]-dates[start_idx]).days))-1)*100:.2f}%")
    print(f"Benchmark CAGR: {(bh_p**(365.25/((dates[-1]-dates[start_idx]).days))-1)*100:.2f}%")

if __name__ == "__main__":
    run_samsung_pure_comparison()
