import yfinance as yf
import pandas as pd
import numpy as np

def run_100_quest():
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
    
    # Pre-calc VWMA Universe
    vwmas = {}
    pv = close * volume
    for w in range(10, 300):
        vwmas[w] = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
    # Dynamic Indicators (Fixed at Champion Config: Ref=2.0)
    # Re-calc here for speed
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

    # StochRSI
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

    # Grid Search for Asymmetry
    # Long: Int [120, 140, 160], Slope [20, 25, 30]
    # Short: Int [60, 100, 140], Slope [10, 20, 30] (Short might need faster MA!)
    
    long_params = [
        {'Int': 140, 'Slope': 25}, # Baseline
        {'Int': 120, 'Slope': 20},
        {'Int': 160, 'Slope': 30}
    ]
    
    short_params = [
        {'Int': 140, 'Slope': 25}, # Baseline
        {'Int': 100, 'Slope': 20}, # Faster
        {'Int': 60, 'Slope': 10}   # Super Fast
    ]
    
    results = []
    
    print("Optimization Loop...")
    
    for lp in long_params:
        for sp in short_params:
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
                    # Asymmetric Signals
                    # Long Signal Check
                    l_ma = int(lp['Int'] - (lp['Slope'] * c_natr))
                    l_ma = max(20, min(l_ma, 290))
                    l_val = vwmas[l_ma].iloc[i]
                    
                    # Short Signal Check
                    s_ma = int(sp['Int'] - (sp['Slope'] * c_natr))
                    s_ma = max(20, min(s_ma, 290))
                    s_val = vwmas[s_ma].iloc[i]
                    
                    if pd.isna(l_val) or pd.isna(s_val): target = 'Cash'
                    else:
                        is_bull = price > l_val
                        is_bear = price < s_val # Note: strict inequality for short?
                        
                        # Logic:
                        # If Price > LongMA -> Long
                        # If Price < ShortMA -> Short (Inverse)
                        # What if ShortMA < Price < LongMA? (Neutral Zone -> Cash or Hold?)
                        # Or what if LongMA < ShortMA?
                        
                        # Simplified Asymmetry:
                        # We use LongMA for detecting Uptrend.
                        # We use ShortMA for detecting Downtrend.
                        # Priority?
                        # Usually L_MA > S_MA (Long term trend vs Short term?).
                        # No, here both are Trend Engines.
                        # Let's say:
                        # Bull If Price > LongMA.
                        # Bear If Price < ShortMA.
                        # Conflict? If LongMA != ShortMA, there is a gap.
                        # Overlap?
                        
                        # Test Logic:
                        # 1. Check Long Signal
                        if price > l_val:
                            # Check Profit Take (RSI)
                            if (rsi_out[i] > 85) and (stoch_k_series[i] > 0.8):
                                target = 'Cash'
                            else:
                                target = 'Long'
                        # 2. Check Short Signal
                        elif price < s_val:
                            target = 'Short'
                        else:
                            # Neutral Zone
                            target = 'Cash' 
                            
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
            
            cfg_name = f"L({lp['Int']}/{lp['Slope']}) S({sp['Int']}/{sp['Slope']})"
            results.append({'Config': cfg_name, 'CAGR': cagr})
            print(f"  {cfg_name}: {cagr*100:.2f}%")
            
    results.sort(key=lambda x: x['CAGR'], reverse=True)
    print("\n=== QUEST RESULTS ===")
    print(f"Best: {results[0]['Config']} => {results[0]['CAGR']*100:.2f}%")

if __name__ == "__main__":
    run_100_quest()
