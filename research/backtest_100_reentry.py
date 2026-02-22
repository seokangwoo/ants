import yfinance as yf
import pandas as pd
import numpy as np

def run_100_reentry():
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
    
    # VWMA Universe (Fixed 140/25)
    intercept = 140
    slope = 25
    updated_ma_len = 140 - (25 * natr)
    updated_ma_len = updated_ma_len.fillna(140).astype(int).clip(20, 250)
    
    vwmas = {}
    pv = close * volume
    for w in range(20, 300):
        vwmas[w] = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
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
        
    # StochRSI K
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

    # Grid Search Re-entry Thresholds
    # Re-entry RSI: [50, 60, 70]
    # Filter: Vol Limit [5.0] (Fixed for speed)
    # Profit Take: RSI 85, Stoch 0.9 (Best from V2)
    
    reentry_grid = [50, 60, 65, 70, 75]
    
    results = []
    
    print(f"Optimization Loop ({len(reentry_grid)} combos)...")
    
    for re_rsi in reentry_grid:
        portfolio = [1.0]
        current_asset = 'Cash'
        fee = 0.002
        start_idx = 300
        
        profit_taken_flag = False
        
        for i in range(start_idx, len(dates)-1):
            c_natr = natrs[i]
            price = prices[i]
            
            target = 'Cash' # Default temp
            
            if not pd.isna(c_natr) and c_natr > 5.0:
                target = 'Cash'
                profit_taken_flag = False # Reset flag on crash
            else:
                ma_len = int(updated_ma_len.iloc[i])
                ma_val = vwmas[ma_len].iloc[i]
                
                c_rsi = rsi_out[i]
                c_stoch = stoch_k_series[i]
                
                if pd.isna(ma_val): target = 'Cash'
                elif price > ma_val: # Bull Trend
                    # 1. Check if we should Profit Take
                    is_overbought = (c_rsi > 85) and (c_stoch > 0.9)
                    
                    if current_asset == 'Long':
                        if is_overbought:
                            target = 'Cash'
                            profit_taken_flag = True
                        else:
                            target = 'Long'
                    else:
                        # Current is Cash or Short
                        # If Cash and ProfitTaken, Check Re-entry
                        if current_asset == 'Cash' and profit_taken_flag:
                             # Re-entry Logic
                             if c_rsi < re_rsi:
                                 target = 'Long'
                                 profit_taken_flag = False # Reset
                             else:
                                 target = 'Cash' # Wait
                        elif current_asset == 'Cash' and not profit_taken_flag:
                             # Fresh Entry (Price > MA)
                             if not is_overbought:
                                 target = 'Long'
                             else:
                                 target = 'Cash'
                        else:
                             # Switching from Short
                             target = 'Long'
                             profit_taken_flag = False

                else: # Bear Trend
                    target = 'Short'
                    profit_taken_flag = False
                    
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
        
        results.append({'ReEntry': re_rsi, 'CAGR': cagr})
        print(f"  Re-Entry RSI<{re_rsi}: {cagr*100:.2f}%")
                
    results.sort(key=lambda x: x['CAGR'], reverse=True)
    print("\n=== RE-ENTRY RESULTS ===")
    print(f"Best: RSI<{results[0]['ReEntry']} => {results[0]['CAGR']*100:.2f}%")

if __name__ == "__main__":
    run_100_reentry()
