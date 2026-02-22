import yfinance as yf
import pandas as pd
import numpy as np
import ta

def run_innovation_quest():
    print("Fetching Data...")
    df_signal = yf.download('069500.KS', start='2010-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2010-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-09-01', progress=False)
    
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    df = pd.DataFrame({
        'Open': df_signal.loc[common]['Open'],
        'Close': df_signal.loc[common]['Close'],
        'High': df_signal.loc[common]['High'],
        'Low': df_signal.loc[common]['Low'],
        'Volume': df_signal.loc[common]['Volume'],
        'Long': df_long.loc[common]['Close'],
        'Short': df_short.loc[common]['Close']
    }).dropna()
    
    open_p = df['Open']
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']
    prev_close = close.shift(1)
    
    # 1. Base Driver: NATR (Benchmark)
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values

    # 2. Driver: WillR (Williams %R)
    # WillR is -100 to 0. 
    # We want a "Stress Metric" like NATR (0 to 5+).
    # Stress = High when WillR is extreme (0 or -100)?
    # Or Stress = High when WillR is changing fast?
    # User suggested WillR. Let's try:
    # Metric = abs(WillR + 50) / 10. (Range 0 to 5).
    # Central (Quiet) = 0. Extreme = 5.
    print("Calculating WillR...")
    willr = ta.momentum.WilliamsRIndicator(high, low, close).williams_r()
    willr_metric = abs(willr + 50) / 10.0
    willr_vals = willr_metric.fillna(0).values

    # 3. Driver: QStick (Chande)
    # QStick = MA(Close - Open).
    # We normalized it by price to make it comparable to NATR %.
    # Metric = abs(QStick) / Close * 100 * 5 (Scale factor to match range).
    print("Calculating QStick...")
    qstick = (close - open_p).rolling(window=14).mean()
    qstick_metric = (abs(qstick) / close) * 100 * 5.0 
    qstick_vals = qstick_metric.fillna(0).values
    
    # 4. Driver: ADX
    # Metric = ADX / 10. (Range 0 to 6-7).
    print("Calculating ADX...")
    adx = ta.trend.ADXIndicator(high, low, close, window=14).adx()
    adx_metric = adx / 10.0
    adx_vals = adx_metric.fillna(0).values

    prices = close.values
    dates = df.index
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    # Dynamic Indicators (Ref=2.0)
    # Note: We should strictly keep using NATR for *RSI Period* adaptation?
    # Or should we use the NEW Driver for that too?
    # Let's keep RSI/Stoch Adaptation using NATR (Proven), only change MA Length Driver.
    
    print("Calculating Dynamic Indicators (using NATR)...")
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
    vwmas = {}
    pv = close * volume
    for w in range(10, 350):
        vwmas[w] = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
    # Drivers to Test
    drivers = {
        'NATR (Baseline)': natrs,
        'WillR (Oscillator)': willr_vals,
        'QStick (Pressure)': qstick_vals,
        'ADX (Trend Strength)': adx_vals
    }
    
    # Optimize Quadratic for EACH Driver
    # To save time, we use a coarser grid then refine for the winner.
    # A: [-1, 0, 1]
    # B: [-40, -30, -20]
    # C: [140, 150]
    
    results = []
    
    print("Innovation Optimization Loop...")
    
    for d_name, d_vals in drivers.items():
        print(f"  Testing Driver: {d_name}...")
        
        best_driver_cagr = -1.0
        
        As = [-1.0, 0.0, 1.0]
        Bs = [-40, -30, -20]
        Cs = [140, 150]
        
        for A in As:
            for B in Bs:
                for C in Cs:
                    # Calc Length
                    # Use numpy operations
                    calc_len = A * (d_vals**2) + B * d_vals + C
                    # Clip
                    calc_len = np.clip(np.nan_to_num(calc_len, nan=140), 20, 300).astype(int)
                    
                    portfolio = [1.0]
                    current_asset = 'Cash'
                    fee = 0.002
                    start_idx = 300
                    
                    for i in range(start_idx, len(dates)-1):
                        driver_val = d_vals[i]
                        # Use same Crash Guard logic (if driver > 5.0 -> Cash?)
                        # Or stick to NATR for Crash Guard?
                        # Let's use NATR for Crash Guard as it's proven.
                        # Using Driver for MA Length only.
                        
                        c_natr = natrs[i]
                        price = prices[i]
                        
                        target = 'Cash'
                        
                        if not pd.isna(c_natr) and c_natr > 5.0:
                            target = 'Cash'
                        else:
                            ma_len = calc_len[i]
                            ma_val = vwmas[ma_len].iloc[i]
                            
                            if pd.isna(ma_val): target = 'Cash'
                            elif price > ma_val: # Bull
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
                    
                    if cagr > best_driver_cagr:
                        best_driver_cagr = cagr
                        
        results.append({'Driver': d_name, 'BestCAGR': best_driver_cagr})
        print(f"    Best {d_name}: {best_driver_cagr*100:.2f}%")
        
    results.sort(key=lambda x: x['BestCAGR'], reverse=True)
    print("\n=== INNOVATION RESULTS ===")
    for r in results:
        print(f"{r['Driver']}: {r['BestCAGR']*100:.2f}%")

if __name__ == "__main__":
    run_innovation_quest()
