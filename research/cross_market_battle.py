import yfinance as yf
import pandas as pd
import numpy as np
import ta
import time

def calculate_parkinson(high, low, window=20):
    sq_ln_hl = pd.Series(np.log(high / low)**2)
    park = np.sqrt(sq_ln_hl.rolling(window).mean() / (4 * np.log(2)))
    return park.fillna(0).values * 100.0

def run_backtest(df_signal, df_long, df_short, strategy_type='Champion'):
    close = df_signal['Close'].values
    high = df_signal['High'].values
    low = df_signal['Low'].values
    volume = df_signal['Volume'].values
    long_rets = df_long['Close'].pct_change().values
    short_rets = df_short['Close'].pct_change().values
    
    # Common Pre-calcs
    adx = ta.trend.ADXIndicator(df_signal['High'], df_signal['Low'], df_signal['Close']).adx().fillna(20).values / 10.0
    engine_lens = (0.6 * (adx**2) - 35 * adx + 170).astype(int).clip(20, 300)
    natr = (ta.volatility.AverageTrueRange(df_signal['High'], df_signal['Low'], df_signal['Close']).average_true_range() / df_signal['Close'] * 100).fillna(2.0).values
    vol_park = calculate_parkinson(high, low, 20)
    rsi = ta.momentum.RSIIndicator(df_signal['Close']).rsi().fillna(50).values
    st_obj = ta.momentum.StochRSIIndicator(df_signal['Close'], window=10)
    st_k = st_obj.stochrsi_k().fillna(0.5); stoch_zl = (st_k + (st_k - st_k.shift(4))).fillna(0.5).values
    mfi = ta.volume.MFIIndicator(df_signal['High'], df_signal['Low'], df_signal['Close'], df_signal['Volume']).money_flow_index().fillna(50).values
    pv_vals = close * volume

    p = 1.0; cur = None; fee = 0.002
    start_idx = 300
    
    for i in range(start_idx, len(close)-1):
        if strategy_type == 'Champion':
            # 72% Logic: NATR Guard + ADX Engine + RSI/Stoch Profit Take
            if natr[i] > 5.0: target = 'Cash'
            else:
                w = engine_lens[i]
                ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
                if close[i] > ma:
                    overheated = (rsi[i] > 85 and stoch_zl[i] > 0.9)
                    target = 'Cash' if overheated else 'Long'
                else:
                    target = 'Short'
        else: # Fusion Logic
            # Overlord Fusion Logic: Parkinson/NATR Voting + Multi-Indi Overheat
            v1 = (natr[i] > 5.0); v2 = (vol_park[i] > 2.5)
            danger = (v1 or v2)
            if danger: target = 'Cash'
            else:
                w = engine_lens[i]
                ma = np.sum(pv_vals[i-w+1:i+1]) / np.sum(volume[i-w+1:i+1])
                if close[i] > ma:
                    # Consensus Overheat (RSI + Stoch + MFI)
                    score = ( (rsi[i]/100) + stoch_zl[i] + (mfi[i]/100) ) / 3
                    target = 'Cash' if score > 0.88 else 'Long'
                else:
                    target = 'Short'
        
        if target != cur: p *= (1 - fee); cur = target
        p *= (1 + (long_rets[i+1] if cur == 'Long' else (short_rets[i+1] if cur == 'Short' else 0.0)))
        
    years = (len(close) - start_idx) / 252
    return (p**(1/years) - 1) * 100

def cross_market_battle():
    print("=== CROSS-MARKET BATTLE: KOSPI vs KOSDAQ ===")
    
    # 1. Fetch Data
    markets = {
        'KOSPI 200': {'signal': '069500.KS', 'long': '122630.KS', 'short': '252670.KS'},
        'KOSDAQ 150': {'signal': '229200.KS', 'long': '233740.KS', 'short': '251340.KS'}
    }
    
    all_data = {}
    for name, tickers in markets.items():
        print(f"Fetching {name} Data...")
        ds = yf.download(tickers['signal'], start='2016-01-01', progress=False)
        dl = yf.download(tickers['long'], start='2016-01-01', progress=False)
        dw = yf.download(tickers['short'], start='2016-01-01', progress=False)
        
        for d in [ds, dl, dw]:
            if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
        common = ds.index.intersection(dl.index).intersection(dw.index)
        all_data[name] = (ds.loc[common], dl.loc[common], dw.loc[common])

    # 2. Run Simulations
    strategies = ['Champion', 'Fusion']
    results = {}
    
    for s_name in strategies:
        results[s_name] = {}
        total_cagr = 0
        for m_name, data in all_data.items():
            print(f"Testing {s_name} on {m_name}...")
            cagr = run_backtest(data[0], data[1], data[2], s_name)
            results[s_name][m_name] = cagr
            total_cagr += cagr
        results[s_name]['Combined Average'] = total_cagr / 2

    # 3. Print Results
    print("\n" + "="*40)
    print(f"{'Strategy':<15} | {'KOSPI':<10} | {'KOSDAQ':<10} | {'Combined':<10}")
    print("-"*40)
    for s_name in strategies:
        print(f"{s_name:<15} | {results[s_name]['KOSPI 200']:.2f}% | {results[s_name]['KOSDAQ 150']:.2f}% | {results[s_name]['Combined Average']:.2f}%")
    print("="*40)

if __name__ == "__main__":
    cross_market_battle()
