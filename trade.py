import os
import time
import json
import schedule
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from kis_api import KisApi
from data_loader import fetch_daily_data
from strategy import UltimateChampionStrategy

# Load Env
load_dotenv()

class TradingBot:
    def __init__(self):
        self.key = os.getenv('KIS_APP_KEY')
        self.secret = os.getenv('KIS_APP_SECRET')
        self.acc_no = os.getenv('KIS_ACCOUNT')
        
        # Initialize KIS API
        self.kis = KisApi(self.key, self.secret, self.acc_no, mock=False)
        
        # Ultimate Champion Strategy (CAGR 72.14%)
        # ADX-Quadratic + Zero-Lag Stochastic
        self.strategy = UltimateChampionStrategy(A=0.6, B=-35, C=170, vol_limit=5.0)
        
        # Tickers
        self.signal_ticker = '069500' # KODEX 200
        self.long_ticker = '122630'   # KODEX Leverage
        self.short_ticker = '252670'  # KODEX 200 Futures Inverse 2X
        
        print(f"=== ANTS KOSPI Switching Bot (Ultimate Champion 72.14%) Initialized ===")

    def get_current_holdings(self):
        """Returns list of tickers currently held"""
        try:
            balance = self.kis.get_balance()
            holdings = []
            if 'output1' in balance:
                for item in balance['output1']:
                    qty = int(item['hldg_qty'])
                    if qty > 0:
                        holdings.append(item['pdno'])
            return holdings
        except Exception as e:
            print(f"Error fetching balance: {e}")
            return []

    def _log_trade(self, ticker, action, qty, price):
        """Log trade to local JSON file"""
        log_file = "data/trades.json"
        trade_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ticker": ticker,
            "action": action,
            "qty": qty,
            "price": price,
            "name": "KODEX Leverage" if ticker == self.long_ticker else "KODEX Inverse 2X"
        }
        
        history = []
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                try:
                    history = json.load(f)
                except:
                    history = []
        
        history.append(trade_entry)
        with open(log_file, "w") as f:
            json.dump(history, f, indent=4)

    def execute_rebalance(self):
        """
        Main Trading Logic (Closing Auction Protocol)
        1. Fetch Signal Data
        2. Get Target (Long/Short)
        3. Trade
        """
        print(f"\n[{datetime.now()}] Running Closing Auction Strategy Logic...")
        
        # 1. Fetch Signal Data
        print(f"  Fetching data for Signal ({self.signal_ticker})...")
        start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        df_signal = fetch_daily_data(self.signal_ticker, start_date=start_date)
            
        # 2. Get Target
        target_ticker = self.strategy.get_signal(df_signal)
        if not target_ticker:
            print("  Signal: CASH (or Profit Take). Clearing positions.")
            target_ticker = None

        if target_ticker:
            target_name = "KODEX Leverage" if target_ticker == self.long_ticker else "KODEX Inverse 2X"
            print(f"  >>> STRATEGY SIGNAL: {target_name} ({target_ticker})")
        else:
            print(f"  >>> STRATEGY SIGNAL: CASH (Safe Exit)")
        
        # 3. Check Holdings
        current_holdings = self.get_current_holdings()
        
        # Step A: Sell Incorrect/Unwanted Assets
        for ticker in current_holdings:
            if ticker != target_ticker:
                print(f"  Selling non-target asset: {ticker}...")
                
                # Fetch qty
                balance = self.kis.get_balance()
                qty = 0
                for item in balance['output1']:
                    if item['pdno'] == ticker:
                        qty = int(item['hldg_qty'])
                        break
                
                if qty > 0:
                    # Fetch price for logging
                    price_info = self.kis.fetch_price_detail(ticker)
                    curr_price = float(price_info['output']['stck_prpr'])
                    
                    res = self.kis.sell_market(ticker, qty)
                    print(f"    Sell Result: {res['msg1']}")
                    if res['rt_cd'] == '0':
                        self._log_trade(ticker, "SELL", qty, curr_price)
                    time.sleep(1) # Safety
        
        # Step B: Buy Target Asset (if any)
        if target_ticker:
            current_holdings = self.get_current_holdings()
            if target_ticker not in current_holdings:
                print(f"  Buying Target: {target_name} ({target_ticker})...")
                
                # Get Cash Balance
                balance = self.kis.get_balance()
                cash = float(balance['output2'][0]['prvs_rcdl_tot_amt'])
                
                if cash < 10000:
                    print("    Not enough cash to buy.")
                    return

                # Calculate Qty
                price_info = self.kis.fetch_price_detail(target_ticker)
                curr_price = float(price_info['output']['stck_prpr'])
                
                if curr_price > 0:
                    buy_amount = cash * 0.99
                    qty = int(buy_amount / curr_price)
                    
                    if qty > 0:
                        res = self.kis.buy_market(target_ticker, qty)
                        print(f"    Buy Result: {res['msg1']}")
                        if res['rt_cd'] == '0':
                            self._log_trade(target_ticker, "BUY", qty, curr_price)
                    else:
                        print("    Qty is 0.")
                else:
                    print("    Current Price is 0 or error.")
            else:
                print("  Already holding target. No action.")
        else:
            print("  Portfolio is in CASH. Monitoring mode.")

    def get_dashboard_data(self):
        """Fetch all data needed for dashboard in one go"""
        balance = self.kis.get_balance()
        
        # 1. Total Assets & P&L
        summary = balance.get('output2', [{}])[0]
        total_asset = float(summary.get('tot_evlu_amt', 0))
        eval_pnl = float(summary.get('evlu_amt_smtl_amt', 0))
        pnl_ratio = float(summary.get('evlu_pfrt_smtl_amt', 0))
        cash = float(summary.get('prvs_rcdl_tot_amt', 0))
        
        # 2. Positions
        positions = []
        if 'output1' in balance:
            for item in balance['output1']:
                qty = int(item['hldg_qty'])
                if qty > 0:
                    positions.append({
                        "ticker": item['pdno'],
                        "name": item['prdt_name'],
                        "qty": qty,
                        "avg_price": float(item['pchs_avg_pric']),
                        "curr_price": float(item['prpr']),
                        "pnl": float(item['evlu_pfls_amt']),
                        "pnl_ratio": float(item['evlu_pfls_rt'])
                    })
        
        # 3. Current Strategy Signal
        start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        df_signal = fetch_daily_data(self.signal_ticker, start_date=start_date)
        signal = self.strategy.get_signal(df_signal)
        
        return {
            "total_asset": total_asset,
            "eval_pnl": eval_pnl,
            "pnl_ratio": pnl_ratio,
            "cash": cash,
            "positions": positions,
            "signal": signal,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

def run_schedule():
    bot = TradingBot()
    schedule.every().day.at("15:21:00").do(bot.execute_rebalance)
    print("Scheduler Started... Waiting for 15:21:00 (Closing Auction)...")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    # run_schedule()
    print("Running Logic Immediately for Verification...")
    bot = TradingBot()
    bot.execute_rebalance()
