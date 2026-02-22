import FinanceDataReader as fdr
import pandas as pd
import numpy as np

def run_tom_backtest():
    print("Fetching Data...")
    df_long = fdr.DataReader('122630', '2010-01-01')['Close']
    
    # Identify Turn of Month Days
    # We need to label days relative to Month End.
    # Logic: For each month, identify last trading day (-1) and first 3 days (+1, +2, +3).
    
    df = pd.DataFrame({'Close': df_long}).dropna()
    dates = df.index
    
    # Group by Year-Month
    df['Year'] = dates.year
    df['Month'] = dates.month
    
    # Mark TOM days
    tom_dates = set()
    
    grouped = df.groupby(['Year', 'Month'])
    
    for (year, month), group in grouped:
        group_dates = group.index
        if len(group_dates) > 3:
            # Last day
            tom_dates.add(group_dates[-1])
            # First 3 days? Or just first 4 days (TOM covers -1 to +3 generally)
            # Let's try -1 to +3 (4 days total)
            
            # Note: We need next month's first 3 days.
            # Easier: Just iter all groups, get last day.
            # And get first 3 days of CURRENT group (for the previous month's flow? No).
            # TOM Effect: Invest at Close of T-1, Hold until Close of T+3.
            pass

    # Better approach:
    # Iterate months.
    # Get Last Day of Month M.
    # Get First 3 Days of Month M+1.
    # Add to target list.
    
    unique_months = df[['Year', 'Month']].drop_duplicates().values
    
    target_dates = []
    
    for i in range(len(unique_months)-1):
        curr_ym = unique_months[i]
        next_ym = unique_months[i+1]
        
        curr_mask = (df['Year'] == curr_ym[0]) & (df['Month'] == curr_ym[1])
        next_mask = (df['Year'] == next_ym[0]) & (df['Month'] == next_ym[1])
        
        curr_days = df[curr_mask].index
        next_days = df[next_mask].index
        
        if len(curr_days) > 0:
            target_dates.append(curr_days[-1]) # Buy Last Day Close (Hold overnight to 1st)
            
        if len(next_days) >= 3:
            target_dates.extend(next_days[:3]) # Hold 1st, 2nd, 3rd
        else:
            target_dates.extend(next_days) # Partial
            
    target_dates = set(target_dates)
    
    # Backtest
    portfolio = [1.0]
    fee = 0.002
    current_asset = 'Cash'
    
    long_rets = df['Close'].pct_change()
    
    # Iterate
    # If Today is in target_dates -> Hold Long
    # Else -> Cash
    
    # Wait, if we buy at Close of Last Day, we benefit from Last Day -> 1st Day gap?
    # No, we buy at Close of T-1 day. The return we see is (Close T / Close T-1).
    # So if we hold ON the date T, we get Return T.
    
    # Target Dates are dates we want to be INVESTED in.
    # e.g. If 1st is target, we must hold from LastDay Close.
    # My logic above collects Last_Day and First_3_Days.
    # So we want to hold for returns OF these days?
    # Return of Last Day: (Close Last - Close Last-1). TOM effect starts end of month.
    # Correct.
    
    print(f"Testing Turn of Month on {len(df)} days...")
    
    exposure_days = 0
    
    for i in range(1, len(dates)):
        date = dates[i]
        
        target = 'Cash'
        if date in target_dates:
            target = 'Long'
            
        # Trade
        if target != current_asset:
            if current_asset != 'Cash':
                 portfolio[-1] *= (1 - fee)
            current_asset = target
            
        # Return
        daily_ret = 0.0
        if current_asset == 'Long':
            if date in long_rets.index:
                daily_ret = long_rets.loc[date]
                exposure_days += 1
                
        if pd.isna(daily_ret): daily_ret = 0.0
        portfolio.append(portfolio[-1] * (1 + daily_ret))
        
    final_val = portfolio[-1]
    years = (dates[-1] - dates[0]).days / 365.25
    cagr = final_val ** (1/years) - 1
    
    s = pd.Series(portfolio)
    mdd = (s / s.cummax() - 1).min()
    
    print("\n=== Turn of Month (TOM) Strategy (2x Long) ===")
    print(f"Final Value: {final_val:.2f}x")
    print(f"CAGR: {cagr*100:.2f}%")
    print(f"MDD: {mdd*100:.2f}%")
    print(f"Exposure: {exposure_days/len(dates)*100:.1f}% of days")

if __name__ == "__main__":
    run_tom_backtest()
