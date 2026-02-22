import yfinance as yf
import pandas as pd
import numpy as np
import ta

def run_open_execution_backtest():
    print("Fetching Data...")
    df_signal = yf.download('069500.KS', start='2010-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2010-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-09-01', progress=False)
    
    if isinstance(df_signal.columns, pd.MultiIndex): df_signal.columns = df_signal.columns.get_level_values(0)
    if isinstance(df_long.columns, pd.MultiIndex): df_long.columns = df_long.columns.get_level_values(0)
    if isinstance(df_short.columns, pd.MultiIndex): df_short.columns = df_short.columns.get_level_values(0)
    
    common = df_signal.index.intersection(df_long.index).intersection(df_short.index)
    
    df_signal = df_signal.loc[common]
    df_long = df_long.loc[common]
    df_short = df_short.loc[common]
    
    close = df_signal['Close']
    open_p = df_signal['Open']
    high = df_signal['High']
    low = df_signal['Low']
    volume = df_signal['Volume']
    prev_close = close.shift(1)
    
    dates = df_signal.index
    
    # Base NATR
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values

    # ADX
    print("Calculating ADX...")
    adx = ta.trend.ADXIndicator(high, low, close, window=14).adx()
    adx_metric = adx / 10.0
    adx_vals = adx_metric.fillna(0).values

    # Prices array for performance
    prices = close.values
    
    # Asset prices
    l_opens = df_long['Open'].values
    l_closes = df_long['Close'].values
    s_opens = df_short['Open'].values
    s_closes = df_short['Close'].values
    
    # Dynamic Indicators
    print("Calculating RSI/Stoch...")
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
    
    target_stoch = 0.9
    target_rsi = 85
    
    # Pre-calc VWMA Universe
    vwmas = {}
    pv = close * volume
    for w in range(10, 350):
        vwmas[w] = pv.rolling(window=w).mean() / volume.rolling(window=w).mean()
        
    A, B, C = 0.6, -35, 170
    calc_len = A * (adx_vals**2) + B * adx_vals + C
    calc_len = calc_len.astype(int).clip(20, 300)
    
    start_idx = 300
    fee = 0.002
    
    # We track portfolio value precisely day by day.
    # capital_at_close is the true marked-to-market value at the end of each day.
    
    capital_at_close = 1.0
    current_asset = 'Cash'
    
    print("\n--- Running OPEN EXECUTION Simulation ---")
    
    for i in range(start_idx, len(dates)-1):
        # 1. EVALUATE SIGNAL AT CLOSE OF DAY 'i'
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
                if (rsi_out[i] > target_rsi) and (stoch_k_series[i] > target_stoch):
                    target = 'Cash'
                else:
                    target = 'Long'
            else:
                target = 'Short'
                
        # 2. WHAT HAPPENS TOMORROW (DAY i+1) ?
        
        # Overnight Phase (Close i to Open i+1)
        if current_asset == 'Long':
            val_at_open = capital_at_close * (l_opens[i+1] / l_closes[i])
        elif current_asset == 'Short':
            val_at_open = capital_at_close * (s_opens[i+1] / s_closes[i])
        else: # Cash
            val_at_open = capital_at_close
            
        # Rebalance Phase (At Open i+1)
        if target != current_asset:
            # We must sell current and buy target.
            # Sell
            if current_asset != 'Cash':
                cash_available = val_at_open * (1 - fee)
            else:
                cash_available = val_at_open
                
            # Buy Target
            if target != 'Cash':
                invested = cash_available * (1 - fee)
            else:
                invested = cash_available
                
            current_asset = target
        else:
            invested = val_at_open # No trade, just keep holding
            
        # Intraday Phase (Open i+1 to Close i+1)
        if current_asset == 'Long':
            capital_at_close = invested * (l_closes[i+1] / l_opens[i+1])
        elif current_asset == 'Short':
            capital_at_close = invested * (s_closes[i+1] / s_opens[i+1])
        else: # Cash
            capital_at_close = invested
            
    years = (dates[-1] - dates[start_idx]).days / 365.25
    cagr = capital_at_close ** (1/years) - 1
    
    print(f"Final Capital (Open Execution): {capital_at_close:.2f}x")
    print(f"Open Execution CAGR: {cagr*100:.2f}%")

if __name__ == "__main__":
    run_open_execution_backtest()
