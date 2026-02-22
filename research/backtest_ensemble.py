import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

def calculate_adx(df, window=14):
    dfP = df.copy()
    dfP['H-L'] = dfP['High'] - dfP['Low']
    dfP['H-PC'] = abs(dfP['High'] - dfP['Close'].shift(1))
    dfP['L-PC'] = abs(dfP['Low'] - dfP['Close'].shift(1))
    dfP['TR'] = dfP[['H-L', 'H-PC', 'L-PC']].max(axis=1) # True Range
    
    dfP['DM+'] = np.where((dfP['High'] - dfP['High'].shift(1)) > (dfP['Low'].shift(1) - dfP['Low']), 
                          np.maximum(dfP['High'] - dfP['High'].shift(1), 0), 0)
    dfP['DM-'] = np.where((dfP['Low'].shift(1) - dfP['Low']) > (dfP['High'] - dfP['High'].shift(1)), 
                          np.maximum(dfP['Low'].shift(1) - dfP['Low'], 0), 0)
    
    dfP['TR14'] = dfP['TR'].rolling(window=window).sum()
    dfP['DM+14'] = dfP['DM+'].rolling(window=window).sum()
    dfP['DM-14'] = dfP['DM-'].rolling(window=window).sum()
    
    dfP['DI+'] = 100 * (dfP['DM+14'] / dfP['TR14'])
    dfP['DI-'] = 100 * (dfP['DM-14'] / dfP['TR14'])
    
    dfP['DX'] = 100 * abs(dfP['DI+'] - dfP['DI-']) / (dfP['DI+'] + dfP['DI-'])
    dfP['ADX'] = dfP['DX'].rolling(window=window).mean()
    
    return dfP['ADX']

def run_ensemble_backtest():
    print("Fetching Data...")
    df_signal = fdr.DataReader('069500', '2010-01-01') # KODEX 200
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    df_short = fdr.DataReader('252670', '2016-01-01')['Close']
    
    # 1. Base Strategy (MA113 + Threshold)
    # Generate Features
    df = df_signal.copy()
    df['MA113'] = df['Close'].rolling(window=113).mean()
    df['Trend'] = np.where(df['Close'] > df['MA113'] * 1.005, 1, 
                           np.where(df['Close'] < df['MA113'] * 0.995, -1, 0))
    
    # 2. ADX Filter
    df['ADX'] = calculate_adx(df, 14)
    # ADX Filter: If ADX < 20, Trend is weak. Treat as 0 (Cash).
    
    # 3. MLP Filter (Deep Learning)
    # Target: Will the Trend Signal be correct tomorrow?
    # Label: 1 if (Trend > 0 and Return > 0) or (Trend < 0 and Return < 0). Else 0.
    
    df['Ret_1d'] = df['Close'].shift(-1) / df['Close'] - 1
    df['Label'] = np.where((df['Trend'] == 1) & (df['Ret_1d'] > 0), 1, 
                           np.where((df['Trend'] == -1) & (df['Ret_1d'] < 0), 1, 0))
    
    # MLP Features: RSI, SMA Slope, Volatility
    df['RSI'] = 0 # Placeholder, assume robust calc later
    # Let's use simple features to avoid complexity explosion for now
    df['Vol'] = df['Close'].pct_change().rolling(20).std()
    df['Slope'] = df['MA113'].pct_change() * 100
    
    df = df.dropna()
    
    # Train MLP
    # We train on 2010-2020, Test on 2021-2025
    train_end = '2020-12-31'
    
    X = df[['ADX', 'Vol', 'Slope']] # Inputs
    y = df['Label'] # Outcome check
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    X_train = X_scaled[df.index <= train_end]
    y_train = y[df.index <= train_end]
    
    X_test = X_scaled[df.index > train_end]
    # y_test = y[df.index > train_end]
    
    print(f"Training MLP (Deep Learning)...")
    mlp = MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=500, random_state=42)
    mlp.fit(X_train, y_train)
    
    # Predict Confidence
    # Prob of "Success"
    probs = mlp.predict_proba(X_test)[:, 1]
    
    # Backtest Loop (2021-2025)
    test_df = df[df.index > train_end]
    dates = test_df.index
    
    portfolio = [1.0]
    fee = 0.002
    current_asset = 'Cash'
    
    long_rets = df_long.pct_change()
    short_rets = df_short.pct_change()
    
    print(f"Running Ensemble Backtest ({len(dates)} days)...")
    
    for i in range(len(dates)-1):
        date = dates[i]
        next_date = dates[i+1]
        
        # 1. Trend Signal (MA113)
        trend_sig = test_df['Trend'].iloc[i]
        
        # 2. ADX Filter
        adx = test_df['ADX'].iloc[i]
        
        # 3. MLP Confidence
        confidence = probs[i]
        
        # Combine
        target = 'Cash'
        
        # Logic: Follow Trend ONLY IF Confidence is High (> 0.5) AND ADX is decent (> 15)
        # If Trend is 0 (Neutral), we stay Cash.
        
        if trend_sig == 1: # Bull
            if confidence > 0.5 and adx > 15:
                target = 'Long'
            else:
                 target = 'Cash' # Filtered out (Weak trend or AI veto)
        elif trend_sig == -1: # Bear
            if confidence > 0.5 and adx > 15:
                target = 'Short'
            else:
                 target = 'Cash'
        else:
            target = 'Cash'
            
        # Trade
        if target != current_asset:
            if current_asset != 'Cash':
                portfolio[-1] *= (1 - fee)
            current_asset = target
            
        # Return
        r = 0.0
        if current_asset == 'Long':
            if next_date in long_rets.index: r = long_rets.loc[next_date]
        elif current_asset == 'Short':
            if next_date in short_rets.index: r = short_rets.loc[next_date]
            
        if pd.isna(r): r = 0.0
        portfolio.append(portfolio[-1] * (1 + r))
        
    # Stats
    final_val = portfolio[-1]
    years = (dates[-1] - dates[0]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    s = pd.Series(portfolio)
    mdd = (s / s.cummax() - 1).min()
    
    print(f"\n=== Ensemble Strategy (Trend + AI Filter) Results ===")
    print(f"Final Value: {final_val:.2f}x")
    print(f"CAGR: {cagr*100:.2f}%")
    print(f"MDD: {mdd*100:.2f}%")

if __name__ == "__main__":
    run_ensemble_backtest()
