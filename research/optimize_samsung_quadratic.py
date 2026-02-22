import yfinance as yf
import pandas as pd
import numpy as np
import ta

def optimize_samsung():
    print("Fetching Samsung Electronics (005930.KS) Data...")
    df = yf.download('005930.KS', start='2005-01-01', progress=False)
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df = df.dropna()
    
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']
    prev_close = close.shift(1)
    
    # ADX
    print("Calculating ADX...")
    adx_obj = ta.trend.ADXIndicator(high, low, close, window=14)
    adx = adx_obj.adx()
    adx_metric = adx / 10.0
    adx_vals = adx_metric.fillna(0).values
    
    # NATR
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    # Dynamic RSI
    print("Calculating Indicators...")
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
    
    # Pre-calc VWMA Universe
    print("Pre-calculating VWMA Universe...")
    vwmas = {}
    pv = close * volume
    for w in range(10, 301):
        vwmas[w] = (pv.rolling(window=w).mean() / volume.rolling(window=w).mean()).values
        
    # Grid Search
    # A: [0, 1.5], B: [-50, 0], C: [100, 250]
    As = np.linspace(0.0, 1.6, 9)
    Bs = np.linspace(-60, 0, 13)
    Cs = np.linspace(100, 260, 9)
    
    best_cagr = -1.0
    best_params = (0, 0, 0)
    
    dates = df.index
    rets_series = df['Close'].pct_change().values
    start_idx = 300
    fee = 0.002
    
    years = (dates[-1] - dates[start_idx+1]).days / 365.25
    
    print(f"Starting Grid Search ({len(As)*len(Bs)*len(Cs)} combinations)...")
    
    count = 0
    for a in As:
        for b in Bs:
            for c in Cs:
                calc_len = a * (adx_vals**2) + b * adx_vals + c
                calc_len = np.clip(calc_len, 10, 300).astype(int)
                
                portfolio = 1.0
                current_asset = 'Cash'
                
                for i in range(start_idx, len(dates)-1):
                    price = vals[i]
                    c_natr = natrs[i]
                    target = 'Cash'
                    
                    if not pd.isna(c_natr) and c_natr > 5.0:
                        target = 'Cash'
                    else:
                        ma_len = calc_len[i]
                        ma_val = vwmas[ma_len][i]
                        
                        if np.isnan(ma_val): target = 'Cash'
                        elif price > ma_val:
                            if (rsi_out[i] > 85) and (stoch_k_series[i] > 0.9):
                                target = 'Cash'
                            else:
                                target = 'Long'
                        else:
                            target = 'Cash'
                    
                    if target != current_asset:
                        portfolio *= (1 - fee)
                        current_asset = target
                        
                    r = rets_series[i+1] if current_asset == 'Long' else 0.0
                    portfolio *= (1 + r)
                
                cagr = portfolio ** (1/years) - 1
                if cagr > best_cagr:
                    best_cagr = cagr
                    best_params = (a, b, c)
                
                count += 1
                if count % 200 == 0:
                    print(f"  Processed {count} combinations...")

    print("\n--- OPTIMIZATION RESULT ---")
    print(f"Best Params: A={best_params[0]:.2f}, B={best_params[1]:.2f}, C={best_params[2]:.2f}")
    print(f"Best CAGR: {best_cagr*100:.2f}%")
    
    # Benchmarking
    benchmark_final = np.prod(1 + rets_series[start_idx+1:])
    benchmark_cagr = benchmark_final ** (1/years) - 1
    print(f"Benchmark CAGR (Buy & Hold): {benchmark_cagr*100:.2f}%")

if __name__ == "__main__":
    optimize_samsung()
