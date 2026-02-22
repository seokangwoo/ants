import yfinance as yf
import pandas as pd
import numpy as np

def run_quadratic_universe():
    print("Fetching Data...")
    df_signal = yf.download('069500.KS', start='2010-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2010-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-09-01', progress=False)
    
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df = pd.DataFrame({
        'Close': df_signal.loc[common]['Close'],
        'High': df_signal.loc[common]['High'],
        'Low': df_signal.loc[common]['Low'],
        'Volume': df_signal.loc[common]['Volume'],
        'Long': df_long.loc[common]['Close'],
        'Short': df_short.loc[common]['Close']
    }).dropna()
    
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']
    prev_close = close.shift(1)
    
    # NATR
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    prices = close.values
    dates = df.index
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    # Dynamic Indicators (Ref=2.0)
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
    
    # Helper for various MAs
    def get_wma(series, window):
        weights = np.arange(1, window + 1)
        return series.rolling(window).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
        
    def get_hma(series, window):
        half_w = int(window / 2)
        sqrt_w = int(np.sqrt(window))
        wma_half = get_wma(series, half_w)
        wma_full = get_wma(series, window)
        diff = 2 * wma_half - wma_full
        return get_wma(diff, sqrt_w)
        
    def get_zlma(series, window):
        lag = (window - 1) / 2
        # Simple approximation for ZLMA: EMA(Price + (Price - Price(lag)), window)
        # But lagging series by float requires interpolation.
        # Use simpler: DEMA or just EMA(2*Close - EMA(Close, w), w)? No.
        # Let's use DEMA as ZLMA proxy or proper ZLMA if easy.
        # ZLMA = EMA(Close + (Close - Close.shift(lag)), window)
        lag_int = int(lag)
        shifted = series.shift(lag_int)
        data_to_smooth = series + (series - shifted)
        return data_to_smooth.ewm(span=window, adjust=False).mean()
        
    def get_ema(series, window):
        return series.ewm(span=window, adjust=False).mean()
        
    def get_sma(series, window):
        return series.rolling(window).mean()
        
    def get_vwma(series, window):
        pv = series * volume
        return pv.rolling(window).mean() / volume.rolling(window).mean()
    
    # We need to pre-calc ALL Lengths for ALL Types.
    # Expensive?
    # Max length 300.
    # 6 Types.
    # 1800 Series. Feasible.
    
    print("Pre-calculating MA Universe (This may take a moment)...")
    ma_library = {}
    
    types = ['SMA', 'EMA', 'WMA', 'HMA', 'ZLMA', 'VWMA']
    
    for t in types:
        ma_library[t] = {}
        for w in range(10, 301):
            if t == 'SMA': ma_library[t][w] = get_sma(close, w)
            elif t == 'EMA': ma_library[t][w] = get_ema(close, w)
            elif t == 'WMA': ma_library[t][w] = get_wma(close, w)
            elif t == 'HMA': ma_library[t][w] = get_hma(close, w)
            elif t == 'ZLMA': ma_library[t][w] = get_zlma(close, w)
            elif t == 'VWMA': ma_library[t][w] = get_vwma(close, w)

    # Quadratic Config (Winner)
    # A=1.0, B=-34.5, C=150
    A = 1.0; B = -34.5; C = 150
    calc_len = A * (natr**2) + B * natr + C
    calc_len = calc_len.fillna(C).astype(int).clip(20, 300)
    
    results = []
    
    print("Optimization Loop...")
    
    for t in types:
        
        portfolio = [1.0]
        current_asset = 'Cash'
        fee = 0.002
        start_idx = 300
        
        for i in range(start_idx, len(dates)-1):
            c_natr = natrs[i]
            price = prices[i]
            
            target = 'Cash'
            
            if not pd.isna(c_natr) and c_natr > 5.0:
                target = 'Cash'
            else:
                ma_len = int(calc_len.iloc[i])
                ma_val = ma_library[t][ma_len].iloc[i]
                
                if pd.isna(ma_val): target = 'Cash'
                elif price > ma_val: # Bull
                    # Profit Take
                    if (rsi_out[i] > 85) and (stoch_k_series[i] > 0.9):
                        target = 'Cash'
                    else:
                        target = 'Long'
                else:
                    target = 'Short'
                    
            if target != current_asset:
                if current_asset != 'Cash': portfolio[-1] *= (1 - fee)
                current_asset = target
                
            next_date = dates[i+1]
            r = 0.0
            if current_asset == 'Long': r = long_rets.get(next_date, 0)
            elif current_asset == 'Short': r = short_rets.get(next_date, 0)
            portfolio.append(portfolio[-1]*(1+r))
            
        final_val = portfolio[-1]
        years = (dates[-1] - dates[start_idx]).days / 365.25
        cagr = final_val ** (1/years) - 1
        
        results.append({'Type': t, 'CAGR': cagr})
        print(f"  {t}: {cagr*100:.2f}%")
        
    results.sort(key=lambda x: x['CAGR'], reverse=True)
    print("\n=== UNIVERSE BATTLE RESULTS ===")
    for r in results:
        print(f"{r['Type']}: {r['CAGR']*100:.2f}%")
        
if __name__ == "__main__":
    run_quadratic_universe()
