import pandas as pd
import numpy as np
import ta

class UltimateChampionStrategy:
    """
    KOSPI 200 Ultimate Champion Strategy (CAGR 72.14%)
    - **Engine**: ADX-Quadratic VWMA (A=0.6, B=-35, C=170)
    - **Indicator 1**: Standard RSI (Window=14, Limit > 85)
    - **Indicator 2**: Zero-Lag Stochastic (Window=10, Limit > 0.9)
    - **Indicator 3**: Standard NATR (Window=20, Crash Guard > 5.0)
    """
    def __init__(self, A=0.6, B=-35, C=170, vol_limit=5.0):
        self.A = A
        self.B = B
        self.C = C
        self.vol_limit = vol_limit
        self.max_ma = 300

    def get_signal(self, df_signal):
        if df_signal.empty or len(df_signal) < 300:
            return None
            
        high = df_signal['High']
        low = df_signal['Low']
        close = df_signal['Close']
        volume = df_signal['Volume']
        
        # 1. NATR Filter (Safety)
        tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
        natr = (tr.rolling(window=20).mean() / close * 100).iloc[-1]
        if natr > self.vol_limit:
            return None # Cash
            
        # 2. ADX-Quadratic Engine
        adx = ta.trend.ADXIndicator(high, low, close, window=14).adx().iloc[-1] / 10.0
        target_ma = int(self.A * (adx**2) + self.B * adx + self.C)
        target_ma = max(20, min(target_ma, 300))
        
        pv = close * volume
        ma = pv.rolling(window=target_ma).mean().iloc[-1] / volume.rolling(window=target_ma).mean().iloc[-1]
        
        # 3. RSI (Standard 14)
        current_rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        
        # 4. Zero-Lag Stochastic (Window 10)
        # Lag = (window-1)/2 = 4
        stoch_k = ta.momentum.StochRSIIndicator(close, window=10).stochrsi_k()
        current_stoch_zl = (stoch_k + (stoch_k - stoch_k.shift(4))).iloc[-1]
        
        # Signal Generation
        price = close.iloc[-1]
        if price > ma:
            # Bullish? Check for overbought (Profit Take)
            if current_rsi > 85 and current_stoch_zl > 0.9:
                return None # Cash
            return '122630' # Long
        else:
            # Bearish
            return '252670' # Inverse
