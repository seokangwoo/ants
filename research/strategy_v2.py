import pandas as pd
import numpy as np

class StrategyV2:
    def __init__(self, k=0.5):
        self.k = k

    def generate_signals(self, df):
        # Calculate Range and Noise
        df['Range'] = (df['High'] - df['Low']).shift(1)
        denominator = (df['High'] - df['Low']).shift(1)
        # Avoid div by zero
        denominator = denominator.replace(0, np.nan)
        
        # Noise = 1 - |Open - Close| / (High - Low)
        # Low noise (trend) -> Hold? No, K adjustment.
        df['Noise'] = 1 - abs(df['Open'].shift(1) - df['Close'].shift(1)) / denominator
        
        # Dynamic K based on Noise (20 days avg)
        df['K'] = df['Noise'].rolling(window=20).mean()
        # Fallback K
        df['K'] = df['K'].fillna(0.5)
        
        # Target Price
        df['Target'] = df['Open'] + df['Range'] * df['K']
        
        # Moving Average Filter (MA5)
        df['MA5'] = df['Close'].rolling(window=5).mean().shift(1)
        
        # Buy Signal
        # 1. Breakout
        # 2. Bull Market (Open > MA5)
        buy_cond = (df['High'] > df['Target']) & (df['Open'] > df['MA5'])
        
        # Returns
        df['Strategy_Return'] = 0.0
        
        # If High > Target, we enter.
        # Return = (Close - Target) / Target
        # Fees
        fee = 0.0025
        
        # We assume daily reset (sell at close).
        # Overnight hold is complex to backtest in this simple framework without vectorization tricks.
        # Let's stick to Dynamic K first.
        
        mask = buy_cond
        df.loc[mask, 'Strategy_Return'] = (df.loc[mask, 'Close'] - df.loc[mask, 'Target']) / df.loc[mask, 'Target'] - fee
        
        return df
