import pandas as pd
import numpy as np
import ta

class DualMomentumStrategy:
    def __init__(self, lookback=20):
        self.lookback = lookback
        self.risk_assets = ['TIGER NASDAQ100', 'TIGER S&P500', 'KODEX 200']
        self.safe_assets = ['KODEX Dollar', 'KODEX Gold']

    def get_signal(self, data_map):
        latest_date = None
        for name, df in data_map.items():
            if not df.empty:
                latest_date = df.index[-1]
                break
        if not latest_date: return None
        scores = {}; ma_vals = {}; prices = {}
        for name, df in data_map.items():
            if df.empty: continue
            price = df['Close'].iloc[-1]; prices[name] = price
            if len(df) > self.lookback:
                past_price = df['Close'].iloc[-self.lookback-1]
                ret = (price - past_price) / past_price
                scores[name] = ret
                ma = df['Close'].rolling(window=self.lookback).mean().iloc[-1]
                ma_vals[name] = ma
            else:
                scores[name] = -999; ma_vals[name] = 999999
        best_risk = None; best_risk_score = -9999
        for asset in self.risk_assets:
            if asset in scores and scores[asset] > best_risk_score:
                best_risk_score = scores[asset]; best_risk = asset
        target = 'Cash'
        if best_risk:
            if prices[best_risk] > ma_vals[best_risk]: target = best_risk
            else:
                best_safe = None; best_safe_score = -9999
                for asset in self.safe_assets:
                    if asset in scores and scores[asset] > best_safe_score:
                        best_safe_score = scores[asset]; best_safe = asset
                if best_safe: target = best_safe
        return target

class KospiSwitchStrategy:
    def __init__(self, lookback=113, threshold=0.005):
        self.lookback = lookback
        self.threshold = threshold

    def get_signal(self, df_signal):
        if df_signal.empty or len(df_signal) < self.lookback: return None
        price = df_signal['Close'].iloc[-1]
        ma = df_signal['Close'].rolling(window=self.lookback).mean().iloc[-1]
        if price > ma * (1 + self.threshold): return '122630'
        elif price < ma * (1 - self.threshold): return '252670'
        else: return None

class VolSwitchStrategy:
    def __init__(self, low_vol_ma=113, high_vol_ma=50, vol_threshold=0.20):
        self.low_vol_ma = low_vol_ma
        self.high_vol_ma = high_vol_ma
        self.vol_threshold = vol_threshold

    def get_signal(self, df_signal):
        if df_signal.empty or len(df_signal) < max(self.low_vol_ma, self.high_vol_ma, 20): return None
        rets = df_signal['Close'].pct_change()
        current_vol = rets.rolling(window=20).std().iloc[-1] * (252 ** 0.5)
        price = df_signal['Close'].iloc[-1]
        if current_vol < self.vol_threshold:
            ma = df_signal['Close'].rolling(window=self.low_vol_ma).mean().iloc[-1]
        else:
            ma = df_signal['Close'].rolling(window=self.high_vol_ma).mean().iloc[-1]
        if price > ma: return '122630'
        else: return '252670'

class NATRStrategy_Linear:
    def __init__(self, intercept=140, slope=25, min_ma=20, max_ma=250):
        self.intercept = intercept; self.slope = slope
        self.min_ma = min_ma; self.max_ma = max_ma
        
    def get_signal(self, df_signal):
        if df_signal.empty or len(df_signal) < self.max_ma + 20: return None
        high = df_signal['High']; low = df_signal['Low']; close = df_signal['Close']
        prev_close = close.shift(1)
        tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
        atr = tr.rolling(window=20).mean()
        natr = (atr / close) * 100; current_natr = natr.iloc[-1]
        if pd.isna(current_natr): return None
        target_ma = int(self.intercept - (self.slope * current_natr))
        target_ma = max(self.min_ma, min(target_ma, self.max_ma))
        ma = close.rolling(window=target_ma).mean().iloc[-1]; price = close.iloc[-1]
        if price > ma: return '122630'
        else: return '252670'

class FinalBoostedStrategy:
    def __init__(self, A=0.6, B=-35, C=170, rsi_limit=85, stoch_limit=0.9, vol_limit=5.0, ref_vol=2.0):
        self.A = A; self.B = B; self.C = C
        self.rsi_limit = rsi_limit; self.stoch_limit = stoch_limit
        self.vol_limit = vol_limit; self.ref_vol = ref_vol
        self.min_ma = 20; self.max_ma = 250

    def get_signal(self, df_signal):
        if df_signal.empty or len(df_signal) < self.max_ma + 60: return None
        high = df_signal['High']; low = df_signal['Low']; close = df_signal['Close']; volume = df_signal['Volume']
        prev_close = close.shift(1)
        tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
        atr = tr.rolling(window=20).mean(); natr = (atr / close) * 100; current_natr = natr.iloc[-1]
        adx = ta.trend.ADXIndicator(high, low, close, window=14).adx(); current_adx = adx.iloc[-1] / 10.0
        if pd.isna(current_natr) or current_natr > self.vol_limit: return None
        vals = close.values; natrs = natr.values; rsi_out = np.zeros(len(vals)); rsi_out[:] = np.nan
        avg_gain = 0.0; avg_loss = 0.0
        for i in range(1, len(vals)):
            c_natr = natrs[i]
            per = int(14 * (self.ref_vol / c_natr)) if not pd.isna(c_natr) and c_natr != 0 else 14
            per = max(4, min(per, 60)); alpha = 1.0 / per
            change = vals[i] - vals[i-1]; gain = max(change, 0); loss = max(-change, 0)
            if i == 1: avg_gain = gain; avg_loss = loss
            else: avg_gain = (avg_gain * (1 - alpha)) + (gain * alpha); avg_loss = (avg_loss * (1 - alpha)) + (loss * alpha)
            rsi_out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        current_rsi = rsi_out[-1]
        c_natr = natrs[-1]; u_per = max(4, min(int(14 * (self.ref_vol / c_natr)) if not pd.isna(c_natr) and c_natr != 0 else 14, 60))
        if len(rsi_out) < u_per: return None
        stoch_history = []
        for back in range(2, -1, -1):
            idx = len(vals) - 1 - back; p_natr = natrs[idx]
            p_per = max(4, min(int(14 * (self.ref_vol / p_natr)) if not pd.isna(p_natr) and p_natr != 0 else 14, 60))
            w_slice = rsi_out[idx-p_per+1 : idx+1]
            w_slice = w_slice[~np.isnan(w_slice)]
            if len(w_slice) == 0: s = 0.5
            else:
                mn = np.min(w_slice); mx = np.max(w_slice)
                s = 0.5 if mx == mn else (rsi_out[idx] - mn) / (mx - mn)
            stoch_history.append(s)
        current_stoch_k = np.mean(stoch_history)
        target_ma = max(self.min_ma, min(int(self.A * (current_adx**2) + self.B * current_adx + self.C), self.max_ma))
        pv = close * volume; ma = (pv.rolling(window=target_ma).mean() / volume.rolling(window=target_ma).mean()).iloc[-1]
        price = close.iloc[-1]
        if price > ma:
            if (current_rsi > self.rsi_limit) and (current_stoch_k > self.stoch_limit): return None
            return '122630'
        return '252670'
