import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, classification_report
import matplotlib.pyplot as plt

def calculate_technical_indicators(df):
    """
    Generate Technical Indicators for ML Features
    """
    df = df.copy()
    
    # 1. Moving Averages
    for window in [5, 10, 20, 60, 120]:
        df[f'MA_{window}'] = df['Close'].rolling(window=window).mean()
        # Distance from MA
        df[f'Dist_MA_{window}'] = (df['Close'] - df[f'MA_{window}']) / df[f'MA_{window}']
        
    # 2. RSI (14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 3. MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # 4. Bollinger Bands (20)
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BB_Lower'] = df['BB_Mid'] - (df['BB_Std'] * 2)
    df['BB_Pos'] = (df['Close'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'])
    
    # 5. Momentum (Returns)
    for lag in [1, 3, 5, 10]:
        df[f'Ret_{lag}'] = df['Close'].pct_change(lag)
        
    # 6. Volatility (ATR -ish)
    df['Vol_20'] = df['Close'].pct_change().rolling(window=20).std()
    
    return df.dropna()

def one_hot_encode_date(df):
    df['Month'] = df.index.month
    df['Weekday'] = df.index.dayofweek
    return df

def run_ml_backtest():
    # 1. Fetch Data
    print("Fetching Data...")
    # Signal: KODEX 200
    df_signal = fdr.DataReader('069500', '2010-01-01')
    # Assets
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    df_short = fdr.DataReader('252670', '2016-01-01')['Close'] # Late listing
    
    # 2. Feature Engineering
    print("Generating Features...")
    df = calculate_technical_indicators(df_signal)
    df = one_hot_encode_date(df)
    
    # Target: 5-Day Forward Return Direction
    # 1 if Close(t+5) > Close(t), else 0
    df['Ret_5d_Fwd'] = df['Close'].shift(-5) / df['Close'] - 1
    df['Target'] = (df['Ret_5d_Fwd'] > 0.0).astype(int)
    
    df = df.dropna()
    
    # Features (X)
    feature_cols = [c for c in df.columns if c not in ['Open', 'High', 'Low', 'Close', 'Volume', 'Change', 'Target', 'Ret_5d_Fwd', 'MA_5', 'MA_10', 'MA_20', 'MA_60', 'MA_120', 'BB_Mid', 'BB_Upper', 'BB_Lower']]
    
    X = df[feature_cols]
    y = df['Target']
    
    # Train/Test Split
    # Train: 2010 ~ 2022
    # Test: 2023 ~ 2025
    split_date = '2023-01-01'
    X_train = X.loc[:split_date]
    y_train = y.loc[:split_date]
    X_test = X.loc[split_date:]
    y_test = y.loc[split_date:]
    
    print(f"Train Size: {len(X_train)}, Test Size: {len(X_test)}")
    
    # 3. Model Training
    print("Training Gradient Boosting...")
    model = GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=3, random_state=42)
    model.fit(X_train, y_train)
    
    train_acc = accuracy_score(y_train, model.predict(X_train))
    test_acc = accuracy_score(y_test, model.predict(X_test))
    print(f"Train Accuracy: {train_acc:.2f}, Test Accuracy: {test_acc:.2f}")
    
    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1]
    
    # 4. Backtest Strategy
    print("Running Backtest...")
    portfolio = [1.0]
    fee = 0.002
    
    test_dates = X_test.index
    rets_long = df_long.pct_change()
    rets_short = df_short.pct_change()
    
    current_asset = 'Cash'
    
    for i in range(len(test_dates)-1):
        date = test_dates[i]
        next_date = test_dates[i+1]
        
        # Signal
        prob_up = probs[i]
        
        # High Conviction Thresholds
        if prob_up > 0.60: 
            target = 'Long'
        elif prob_up < 0.40:
            target = 'Short'
        else:
            if current_asset != 'Cash':
                 target = current_asset 
            else:
                 target = 'Cash'
        
        # Trade
        if target != current_asset:
            if current_asset != 'Cash':
                portfolio[-1] *= (1 - fee)
            current_asset = target
            
        # Apply Return (Next Day Return)
        daily_ret = 0.0
        if current_asset == 'Long':
            if next_date in rets_long.index: daily_ret = rets_long.loc[next_date]
        elif current_asset == 'Short':
            if next_date in rets_short.index: daily_ret = rets_short.loc[next_date]
                
        if pd.isna(daily_ret): daily_ret = 0.0
        portfolio.append(portfolio[-1] * (1 + daily_ret))
        
    # Stats
    final_val = portfolio[-1]
    years = (test_dates[-1] - test_dates[0]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    s = pd.Series(portfolio)
    mdd = (s / s.cummax() - 1).min()
    
    print(f"=== ML Strategy Results (2017-2025) ===")
    print(f"Final Value: {final_val:.2f}")
    print(f"CAGR: {cagr*100:.2f}%")
    print(f"MDD: {mdd*100:.2f}%")
    
    # Importance
    imp = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("\nTop 5 Features:")
    print(imp.head(5))

if __name__ == "__main__":
    run_ml_backtest()
