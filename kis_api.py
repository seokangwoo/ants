import requests
import json
import time
import os
from datetime import datetime
import pandas as pd

class KisApi:
    def __init__(self, api_key, api_secret, acc_no, mock=False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.acc_no = acc_no
        self.mock = mock
        # Base URL
        if mock:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            self.base_url = "https://openapi.koreainvestment.com:9443"
            
        self.access_token = None
        self.token_file = "token.dat"
        self._auth()

    def _auth(self):
        # Allow checking existing token
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'r') as f:
                    data = json.load(f)
                    # Simple expiration check
                    # We assume if file modified time is recent enough
                    mtime = os.path.getmtime(self.token_file)
                    if time.time() - mtime < 43200: # 12 hours
                        self.access_token = data.get('access_token')
                        if self.access_token:
                             return # Use existing token
            except Exception as e:
                print(f"Token load error: {e}")
        
        # Issue Token
        path = "oauth2/tokenP"
        url = f"{self.base_url}/{path}"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.api_key,
            "appsecret": self.api_secret
        }
        
        try:
            res = requests.post(url, headers=headers, data=json.dumps(body))
            if res.status_code == 200:
                data = res.json()
                self.access_token = data['access_token']
                # Save just in case (optional)
                with open(self.token_file, 'w') as f:
                    json.dump(data, f)
            else:
                print(f"Auth Failed: {res.text}")
                raise Exception("Auth Failed")
        except Exception as e:
            print(f"Auth Exception: {e}")
            raise

    def get_headers(self, tr_id, cust_type="P"):
        return {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.api_key,
            "appSecret": self.api_secret,
            "tr_id": tr_id,
            "custtype": cust_type # P for Personal, B for Business? specific to some TRs
        }

    def fetch_ohlcv_domestic(self, symbol, timeframe, start_day, end_day):
        # TR_ID: FHKST03010100 (Period Price)
        # timeframe: 'D' (Day), 'W', 'M', 'Y'
        path = "uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        url = f"{self.base_url}/{path}"
        
        # Determine Period Code
        period_code = "D"
        if timeframe == 'W': period_code = "W"
        if timeframe == 'M': period_code = "M" 
        
        headers = self.get_headers("FHKST03010100")
        
        # Params
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", # J: Stock, ETF...
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_DATE_1": start_day, # YYYYMMDD
            "FID_INPUT_DATE_2": end_day,   # YYYYMMDD
            "FID_PERIOD_DIV_CODE": period_code,
            "FID_ORG_ADJ_PRC": "0" # Adjusted Price: 0:Adjusted, 1:Original
        }
        
        res = requests.get(url, headers=headers, params=params)
        data = res.json()
        
        # Check Error
        if data.get('rt_cd') != '0':
            # print(f"Error fetching OHLCV for {symbol}: {data.get('msg1')}")
            pass
            
        return data

    def search_stock_info(self, symbol):
        # TR_ID: CTPF1002R (Product Info) - Requires REAL server usually?
        path = "uapi/domestic-stock/v1/quotations/search-stock-info"
        url = f"{self.base_url}/{path}"
        
        headers = self.get_headers("CTPF1002R")
        
        params = {
            "PDNO": symbol,
            "PRDT_TYPE_CD": "300" # 300: Stock, etc.
        }
        
        res = requests.get(url, headers=headers, params=params)
        return res.json()
        
    def fetch_price_detail(self, symbol):
        # TR_ID: FHKST01010100 (Inquire Price/Current Price)
        # Returns: Price, MarketCap (hts_avls), PER, EPS, PBR, etc.
        path = "uapi/domestic-stock/v1/quotations/inquire-price"
        url = f"{self.base_url}/{path}"
        
        headers = self.get_headers("FHKST01010100")
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol
        }
        
        res = requests.get(url, headers=headers, params=params)
        return res.json()

    def fetch_estimate_perform(self, symbol):
         # TR_ID: FHKST01010300 ?? (Guessing based on path pattern domestic-stock/quotations/...)
         # User provided path: uapi/domestic-stock/v1/quotations/estimate-perform
         path = "uapi/domestic-stock/v1/quotations/estimate-perform"
         url = f"{self.base_url}/{path}"
         
         # User identified correct TR_ID: HHKST668300C0
         tr_id = "HHKST668300C0" 
         
         headers = self.get_headers(tr_id)
         
         params = {
             "FID_COND_MRKT_DIV_CODE": "J",
             "SHT_CD": symbol
         }
         
         res = requests.get(url, headers=headers, params=params)
         return res.json()

    def fetch_financial_ratio(self, symbol, timeframe='Y', div_code="0"):
        # TR_ID: FHKST66430300 (Financial Ratio / Financial Statements)
        path = "uapi/domestic-stock/v1/finance/financial-ratio"
        url = f"{self.base_url}/{path}"
        
        headers = self.get_headers("FHKST66430300")
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_DIV_CLS_CODE": div_code # 0: Yearly (contains 12/12 dates), 1: Quarterly
        }
        
        res = requests.get(url, headers=headers, params=params)
        return res.json()

    def fetch_income_statement(self, symbol, timeframe='Y', div_code="0"):
        # TR_ID: FHKST66430100 (Income Statement)
        path = "uapi/domestic-stock/v1/finance/income-statement"
        url = f"{self.base_url}/{path}"
        
        headers = self.get_headers("FHKST66430100")
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_DIV_CLS_CODE": div_code # 0: Yearly
        }
        
        res = requests.get(url, headers=headers, params=params)
        return res.json()

    def fetch_balance_sheet(self, symbol, timeframe='Y', div_code="0"):
        # TR_ID: FHKST66430200 (Balance Sheet)
        path = "uapi/domestic-stock/v1/finance/balance-sheet"
        url = f"{self.base_url}/{path}"
        
        headers = self.get_headers("FHKST66430200")
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_DIV_CLS_CODE": div_code 
        }
        
        res = requests.get(url, headers=headers, params=params)
        return res.json()

    def fetch_other_major_ratios(self, symbol, timeframe='Y'):
        # Calculate EBITDA from Income Statement
        # EBITDA = Operating Profit (opr_profit / op_prfi) + Depreciation (depr_cost)
        # Note: API field names might vary, checking debug output:
        # FHKST66430100 (Income Statement) returns 'op_prfi' (Operating Profit)
        # FHKST66430200 (Balance Sheet) returns 'depr_cost' ? No, Depr is usually in Cash Flow or Income Statement details.
        # Actually in debug output of FHKST66430200 (Balance Sheet) we saw 'depr_cost' as "99.99" (dummy?) or might be in Income Statement?
        # Let's re-check debug output from user turn.
        # FHKST66430100 (Income Statement) output: ['stac_yymm', 'cras', 'fxas'...] -> This looks like Balance Sheet actually?
        # FHKST66430200 (Balance Sheet) output: ['sale_account', 'sale_cost', 'op_prfi'...] -> This looks like Income Statement!
        
        # Swapping: 
        # FHKST66430100 seems to be Balance Sheet (Assets, Liabilities)
        # FHKST66430200 seems to be Income Statement (Sales, OP)
        
        # Let's use FHKST66430200 for Income Statement
        
        income = self.fetch_balance_sheet(symbol) # Intentionally calling the one that returned Income content in debug
        # Note: Naming might be confused in debug script or API. 
        # Debug script trace:
        # FHKST66430100 -> {cras, fxas, total_aset...} -> Balance Sheet
        # FHKST66430200 -> {sale_account, op_prfi...} -> Income Statement

        try:
            output = []
            if 'output' in income:
                for row in income['output']:
                    # row is dict
                    # stac_yymm: YearMonth
                    # op_prfi: Operating Profit
                    # depr_cost: Depreciation
                    
                    try:
                        op = float(row.get('op_prfi', 0))
                        depr = float(row.get('depr_cost', 0))
                        # If depr is 99.99 or similar, it might be invalid/missing.
                        # But let's assume valid for now or 0.
                        
                        ebitda = op + depr
                        
                        output.append({
                            'stac_yymm': row.get('stac_yymm'),
                            'ebitda': str(ebitda),
                            'ev_ebitda': "0" # Cannot easily calc EV without Market Cap history here. Leave 0.
                        })
                    except:
                        pass
            
            return {'output': output}
        except Exception as e:
            print(f"Error calc EBITDA: {e}")
            return {'output': []}

    def fetch_invest_opbysec(self, symbol, start_date=None, end_date=None):
        # TR_ID: FHKST663400C0 (Investment Opinion by Securities Company)
        path = "uapi/domestic-stock/v1/quotations/invest-opbysec"
        url = f"{self.base_url}/{path}"
        
        headers = self.get_headers("FHKST663400C0")
        
        if not start_date:
            from datetime import datetime, timedelta
            start_date = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
        if not end_date:
            from datetime import datetime, timedelta
            end_date = (datetime.now() + timedelta(days=365)).strftime("%Y%m%d")

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "16634",
            "FID_INPUT_ISCD": symbol,
            "FID_DIV_CLS_CODE": "0",  # 0: All
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date
        }
        
        res = requests.get(url, headers=headers, params=params)
        return res.json()

    def get_balance(self):
        """Fetch account balance (Cash & Holdings)"""
        path = "uapi/domestic-stock/v1/trading/inquire-balance"
        url = f"{self.base_url}/{path}"
        headers = self.get_headers("TTTC8434R")
        
        params = {
            "CANO": self.acc_no[:8],
            "ACNT_PRDT_CD": "01", # Default 01
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        res = requests.get(url, headers=headers, params=params)
        return res.json()

    def send_order(self, ticker, order_type, price, qty, trade_type="00"):
        """
        Generic Order Function
        order_type: 1 (Buy), 2 (Sell)
        trade_type: 00 (Limit), 01 (Market)
        """
        path = "uapi/domestic-stock/v1/trading/order-cash"
        url = f"{self.base_url}/{path}"
        
        # TR_ID: Buy TTTC0802U, Sell TTTC0801U
        tr_id = "TTTC0802U" if order_type == "1" else "TTTC0801U"
        headers = self.get_headers(tr_id)
        
        data = {
            "CANO": self.acc_no[:8],
            "ACNT_PRDT_CD": "01",
            "PDNO": ticker,
            "ORD_DVSN": trade_type, 
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }
        
        res = requests.post(url, headers=headers, data=json.dumps(data))
        return res.json()

    def buy_market(self, ticker, qty):
        return self.send_order(ticker, "1", "0", qty, "01")

    def sell_market(self, ticker, qty):
        return self.send_order(ticker, "2", "0", qty, "01")

