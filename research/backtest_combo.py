import yfinance as yf
import pandas as pd
import numpy as np
import ta

def run_combo_test():
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
    
    # 1. Base Engine (VWMA NATR)
    print("Calculating Base Engine (VWMA)...")
    prev_close = close.shift(1)
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    updated_ma_len = 140 - (25 * natr)
    updated_ma_len = updated_ma_len.fillna(140).astype(int).clip(20, 250)
    
    vwmas = {}
    pv = close * volume
    for w in range(20, 251):
        vwmas[w] = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
    prices = close.values
    dates = df.index
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    # 2. Indicators
    print("Calculating Top Indicators...")
    
    rsi = ta.momentum.RSIIndicator(close, window=14).rsi().values
    stoch_rsi = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3).stochrsi_k().values
    adx = ta.trend.ADXIndicator(high, low, close, window=14).adx().values
    cci = ta.trend.CCIIndicator(high, low, close, window=20).cci().values
    
    # 3. Combo Logic
    # We test:
    # A: RSI > 85 (Baseline)
    # B: RSI > 85 OR StochRSI > 1.0 (Faster Exit)
    # C: RSI > 85 OR ADX > 60 (Trend Exhaustion)
    # D: RSI > 85 OR CCI > 250 (Spike)
    # E: RSI > 85 AND StochRSI > 1.0 (Confirmation)
    
    combos = [
        {'Name': 'Baseline (RSI>85)', 'Func': lambda i: rsi[i] > 85},
        {'Name': 'OR StochRSI>1.0', 'Func': lambda i: (rsi[i] > 85) or (stoch_rsi[i] > 1.0)},
        {'Name': 'OR ADX>60', 'Func': lambda i: (rsi[i] > 85) or (adx[i] > 60)},
        {'Name': 'OR CCI>250', 'Func': lambda i: (rsi[i] > 85) or (cci[i] > 250)},
        {'Name': 'AND StochRSI>0.8', 'Func': lambda i: (rsi[i] > 85) and (stoch_rsi[i] > 0.8)},
        {'Name': 'Mega Combo (RSI>85 OR ADX>60)', 'Func': lambda i: rsi[i]>85 or adx[i]>60}
    ]
    
    print("Running Combo Tests...")
    
    start_idx = 250
    
    results = []
    
    for combo in combos:
        portfolio = [1.0]
        current_asset = 'Cash'
        fee = 0.002
        
        func = combo['Func']
        
        for i in range(start_idx, len(dates)-1):
            curr_natr = natrs[i]
            price = prices[i]
            
            # Vol Filter
            if not pd.isna(curr_natr) and curr_natr > 5.0:
                target = 'Cash'
            else:
                ma_len = int(updated_ma_len.iloc[i])
                ma_val = vwmas[ma_len].iloc[i]
                
                if pd.isna(ma_val): target = 'Cash'
                elif price > ma_val: # Bull
                    # Check Limit
                    should_exit = False
                    try:
                        if func(i): should_exit = True
                    except: pass
                    
                    if should_exit: target = 'Cash'
                    else: target = 'Long'
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
        
        results.append({'Name': combo['Name'], 'CAGR': cagr})
        print(f"  {combo['Name']}: {cagr*100:.2f}%")
            
    print("\n=== CHAMPION COMBO ===")
    results.sort(key=lambda x: x['CAGR'], reverse=True)
    print(f"{results[0]['Name']}: {results[0]['CAGR']*100:.2f}%")

if __name__ == "__main__":
    run_combo_test()
