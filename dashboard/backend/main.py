import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json

# Add parent dir to path to import trade
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from trade import TradingBot

app = FastAPI(title="ANTS Trading API")

# Enable CORS for Next.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared Bot Instance
bot = TradingBot()

@app.get("/api/status")
async def get_status():
    """Returns real-time account status and positions"""
    try:
        return bot.get_dashboard_data()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/history")
async def get_history():
    """Returns local trade history"""
    log_file = os.path.join(os.path.dirname(__file__), '../../data/trades.json')
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            return json.load(f)
    return []

@app.get("/api/ping")
async def ping():
    return {"status": "ok", "time": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
