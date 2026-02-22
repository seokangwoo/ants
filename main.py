import os
import sys
from dotenv import load_dotenv
from kis_api import KisApi
import time

# Load environment variables
load_dotenv()

def main():
    print("=== Starting Automated Trading Bot ===")
    
    key = os.getenv('KIS_APP_KEY')
    secret = os.getenv('KIS_APP_SECRET')
    acc_no = os.getenv('KIS_ACCOUNT')

    if not key or not secret:
        print("Error: Missing API credentials. Please configure .env file.")
        print("Copy .env.example to .env and fill in your keys.")
        return

    # Initialize API
    # Assuming acc_no is optional if hardcoded in logic, but good to have
    try:
        broker = KisApi(key, secret, acc_no if acc_no else "MASKED", mock=False)
        print("KIS API Client Initialized.")
        
        # Test Connection with Samsung Electronics (005930)
        print("Testing connection...")
        ticker = "005930"
        price_info = broker.fetch_price_detail(ticker)
        
        if 'output' in price_info:
            current_price = price_info['output'].get('stck_prpr')
            print(f"Success! {ticker} Current Price: {current_price} KRW")
        else:
            print("Connection test returned unexpected data:", price_info)

    except Exception as e:
        print(f"Failed to initialize or connect: {e}")

if __name__ == "__main__":
    main()
