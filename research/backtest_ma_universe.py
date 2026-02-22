import yfinance as yf
import pandas as pd
import numpy as np
import math

class MAFactory:
    @staticmethod
    def sma(series, length):
        return series.rolling(window=length).mean()

    @staticmethod
    def ema(series, length):
        return series.ewm(span=length, adjust=False).mean()

    @staticmethod
    def wma(series, length):
        weights = np.arange(1, length + 1)
        return series.rolling(length).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

    @staticmethod
    def dema(series, length):
        # DEMA = 2*EMA - EMA(EMA)
        ema1 = series.ewm(span=length, adjust=False).mean()
        ema2 = ema1.ewm(span=length, adjust=False).mean()
        return 2 * ema1 - ema2

    @staticmethod
    def tema(series, length):
        # TEMA = 3*EMA - 3*EMA(EMA) + EMA(EMA(EMA))
        ema1 = series.ewm(span=length, adjust=False).mean()
        ema2 = ema1.ewm(span=length, adjust=False).mean()
        ema3 = ema2.ewm(span=length, adjust=False).mean()
        return 3 * ema1 - 3 * ema2 + ema3

    @staticmethod
    def hma(series, length):
        # HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))
        def weighted_avg(w):
            def _wma(x):
                weights = np.arange(1, w + 1)
                return np.dot(x, weights) / weights.sum()
            return _wma
            
        wma_half = series.rolling(int(length/2)).apply(weighted_avg(int(length/2)), raw=True)
        wma_full = series.rolling(length).apply(weighted_avg(length), raw=True)
        diff = 2 * wma_half - wma_full
        sqrt_len = int(math.sqrt(length))
        return diff.rolling(sqrt_len).apply(weighted_avg(sqrt_len), raw=True)

    @staticmethod
    def zlma(series, length):
        # ZLMA (Zero Lag)
        lag = int((length - 1) / 2)
        lag_series = series.shift(lag)
        data_to_smooth = series + (series - lag_series)
        return data_to_smooth.ewm(span=length).mean()
        
    @staticmethod
    def vwma(series, length, volume):
        # VWMA = SMA(Price * Vol) / SMA(Vol)
        pv = series * volume
        return pv.rolling(window=length).mean() / volume.rolling(window=length).mean()

    @staticmethod
    def alma(series, length, offset=0.85, sigma=6):
        # Arnaud Legoux MA
        m = offset * (length - 1)
        s = length / sigma
        
        def alma_weight(k):
             return math.exp(-((k - m)**2) / (2 * s * s))
             
        weights = np.array([alma_weight(k) for k in range(length)])
        weights = weights / weights.sum() # Normalize
        
        return series.rolling(length).apply(lambda x: np.dot(x, weights), raw=True)

    @staticmethod
    def t3(series, length, v_factor=0.7):
        # T3 Tillson
        # T3 = GD(GD(GD(Price)))
        # GD(x) = EMA(x) * (1+v) - EMA(EMA(x)) * v
        def gd(src, l, v):
            ema1 = src.ewm(span=l, adjust=False).mean()
            ema2 = ema1.ewm(span=l, adjust=False).mean()
            return ema1 * (1 + v) - ema2 * v
            
        t1 = gd(series, length, v_factor)
        t2 = gd(t1, length, v_factor)
        t3 = gd(t2, length, v_factor)
        return t3

    @staticmethod
    def linreg(series, length):
        # Moving Linear Regression Forecast
        # Slope * (n-1) + Intercept
        # Simple: 
        x = np.arange(length)
        def get_linreg_end(y):
            # y is array of prices
            # slope, intercept = np.polyfit(x, y, 1)
            # return slope * (length-1) + intercept
            # Optimization:
            x_mean = (length - 1) / 2
            y_mean = y.mean()
            numerator = np.sum((x - x_mean) * (y - y_mean))
            denominator = np.sum((x - x_mean)**2)
            slope = numerator / denominator
            intercept = y_mean - slope * x_mean
            return slope * (length - 1) + intercept
            
        return series.rolling(length).apply(get_linreg_end, raw=True)

def run_ma_universe():
    print("Fetching Data...")
    df_signal = yf.download('069500.KS', start='2010-01-01', progress=False)
    df_long = yf.download('122630.KS', start='2010-01-01', progress=False)
    df_short = yf.download('252670.KS', start='2016-09-01', progress=False)
    
    # Process Columns
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
    
    dates = df.index
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']
    prices = close.values
    
    # NATR
    prev_close = close.shift(1)
    tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
    atr = tr.rolling(window=20).mean()
    natr = (atr / close) * 100
    natrs = natr.values
    
    long_rets = df['Long'].pct_change()
    short_rets = df['Short'].pct_change()
    
    # Universe Setup
    ma_types = ['SMA', 'EMA', 'DEMA', 'TEMA', 'HMA', 'ZLMA', 'VWMA', 'ALMA', 'T3', 'LINREG']
    
    intercepts = [120, 140, 160]
    slopes = [20, 25, 30]
    
    results = []
    
    print(f"Starting Universe Scan: {len(ma_types)} Types x {len(intercepts)*len(slopes)} Configs")
    
    for ma_type in ma_types:
        print(f"Processing {ma_type}...")
        
        # Pre-calc Optimization
        # We need lengths 20 to 250
        # For HMA/ALMA/Linreg this is slow.
        # But we do it once per type.
        
        ma_cache = {}
        for w in range(10, 251):
            if ma_type == 'SMA': ma_cache[w] = MAFactory.sma(close, w)
            elif ma_type == 'EMA': ma_cache[w] = MAFactory.ema(close, w)
            elif ma_type == 'DEMA': ma_cache[w] = MAFactory.dema(close, w)
            elif ma_type == 'TEMA': ma_cache[w] = MAFactory.tema(close, w)
            elif ma_type == 'HMA': ma_cache[w] = MAFactory.hma(close, w)
            elif ma_type == 'ZLMA': ma_cache[w] = MAFactory.zlma(close, w)
            elif ma_type == 'VWMA': ma_cache[w] = MAFactory.vwma(close, w, volume)
            elif ma_type == 'ALMA': ma_cache[w] = MAFactory.alma(close, w)
            elif ma_type == 'T3': ma_cache[w] = MAFactory.t3(close, w)
            elif ma_type == 'LINREG': ma_cache[w] = MAFactory.linreg(close, w)
            
        # Grid Search
        best_type_cagr = -999
        best_type_config = ""
        
        start_idx = 250
        
        for intercept in intercepts:
            for slope in slopes:
                portfolio = [1.0]
                current_asset = 'Cash'
                fee = 0.002
                
                for i in range(start_idx, len(dates)-1):
                    # Logic: NATR Linear
                    curr_natr = natrs[i]
                    price = prices[i]
                    
                    if pd.isna(curr_natr): 
                        ma_len = intercept
                    else:
                        ma_len = int(intercept - (slope * curr_natr))
                        
                    ma_len = max(20, min(ma_len, 250))
                    
                    ma_val = ma_cache[ma_len].iloc[i]
                    
                    if pd.isna(ma_val): target = 'Cash'
                    elif price > ma_val: target = 'Long'
                    else: target = 'Short'
                    
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
                
                if cagr > best_type_cagr:
                    best_type_cagr = cagr
                    best_type_config = f"Int{intercept} Slope{slope}"
                    
        print(f"  Best {ma_type}: {best_type_cagr*100:.2f}% ({best_type_config})")
        results.append({'Type': ma_type, 'CAGR': best_type_cagr, 'Config': best_type_config})
        
    print("\n=== FINAL RANKING ===")
    results.sort(key=lambda x: x['CAGR'], reverse=True)
    for res in results:
        print(f"{res['Type']}: {res['CAGR']*100:.2f}% ({res['Config']})")

if __name__ == "__main__":
    run_ma_universe()
