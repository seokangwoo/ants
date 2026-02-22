import yfinance as yf
import pandas as pd
import numpy as np
import ta

def run_indicator_royale():
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
    
    # Pre-calc VWMA Universe
    vwmas = {}
    pv = close * volume
    for w in range(20, 251):
        vwmas[w] = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
    # 2. Calculate Indicators (Using 'ta' lib)
    print("Calculating Indicators...")
    
    # RSI (Baseline)
    rsi = ta.momentum.RSIIndicator(close, window=14).rsi().values
    
    # MACD
    macd = ta.trend.MACD(close)
    macd_diff = macd.macd_diff().values # Histogram
    
    # PPO
    ppo = ta.momentum.PercentagePriceOscillator(close)
    ppo_hist = ppo.ppo_hist().values
    
    # Stochastic
    stoch = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
    stoch_k = stoch.stoch().values
    
    # StochRSI
    stoch_rsi = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
    stoch_rsi_k = stoch_rsi.stochrsi_k().values
    
    # CCI
    cci = ta.trend.CCIIndicator(high, low, close, window=20).cci().values
    
    # Bollinger %B
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_p = bb.bollinger_pband().values
    
    # Awesome Oscillator
    ao = ta.momentum.AwesomeOscillatorIndicator(high, low).awesome_oscillator().values
    
    # ADX
    adx = ta.trend.ADXIndicator(high, low, close, window=14).adx().values
    
    indicators = {
        'RSI': rsi,
        'MACD_Hist': macd_diff,
        'PPO_Hist': ppo_hist,
        'Stoch_K': stoch_k,
        'StochRSI_K': stoch_rsi_k,
        'CCI': cci,
        'BB_PctB': bb_p,
        'AO': ao,
        'ADX': adx
    }
    
    # Grid Search logic
    # We test each indicator as a "Profit Take Trigger" (Exit Long -> Cash)
    # Thresholds need to be specific per indicator type.
    
    grids = {
        'RSI': [80, 85, 90, 95],
        'MACD_Hist': [0, 'Reversal'], # Reversal logic logic custom
        'PPO_Hist': [0, 'Reversal'],
        'Stoch_K': [80, 90, 95],
        'StochRSI_K': [0.8, 0.9, 0.95, 1.0],
        'CCI': [100, 150, 200, 250],
        'BB_PctB': [0.9, 1.0, 1.1], # > 1.0 means above upper band
        'AO': ['Reversal'],
        'ADX': [50, 60] # Very high trend -> exhaustion?
    }
    
    dates = df.index
    prices = close.values
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    results = []
    
    start_idx = 250
    
    print("Starting Battle Royale...")
    
    for name, ind_values in indicators.items():
        thresholds = grids.get(name, [])
        
        for thresh in thresholds:
            portfolio = [1.0]
            current_asset = 'Cash'
            fee = 0.002
            
            for i in range(start_idx, len(dates)-1):
                curr_natr = natrs[i]
                price = prices[i]
                
                # Vol Filter (Fixed)
                if not pd.isna(curr_natr) and curr_natr > 5.0:
                    target = 'Cash'
                else:
                    ma_len = int(updated_ma_len.iloc[i])
                    ma_val = vwmas[ma_len].iloc[i]
                    
                    if pd.isna(ma_val): target = 'Cash'
                    elif price > ma_val: # Bull
                        # INDICATOR EXIT LOGIC
                        val = ind_values[i]
                        exit_signal = False
                        
                        if pd.isna(val): exit_signal = False
                        elif thresh == 'Reversal':
                            # Logic: If val was positive and decreases?
                            # Or if val crosses below signal? 
                            # Let's simple: If 2 days down?
                            if i > 2 and ind_values[i-1] > val and ind_values[i-2] < ind_values[i-1]:
                                exit_signal = True # Local Top
                        else:
                            # Standard Threshold (Greater than)
                            if val > thresh:
                                exit_signal = True
                                
                        if exit_signal:
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
            
            fullname = f"{name} > {thresh}"
            results.append({'Config': fullname, 'CAGR': cagr})
            
    print("\n=== BATTLE RESULTS (Top 10) ===")
    results.sort(key=lambda x: x['CAGR'], reverse=True)
    for r in results[:10]:
        print(f"{r['Config']}: {r['CAGR']*100:.2f}%")

if __name__ == "__main__":
    run_indicator_royale()
