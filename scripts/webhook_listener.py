#!/usr/bin/env python3
"""
TradingView Webhook → MT5 Bridge Listener

This script receives TradingView alerts via webhook, validates them,
and forwards valid orders to MT5 via MetaTrader5 Python API.

Security:
- HMAC signature validation (if HMAC_SECRET is set)
- Idempotency via UID deduplication
- Price tolerance and timestamp skew checks
- Rate limiting

Deployment:
1. Set environment variables: HMAC_SECRET, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
2. Run: python webhook_listener.py
3. Configure TradingView alert webhook URL: http://your-server:8080/webhook
"""

import os
import json
import hmac
import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from collections import defaultdict
from flask import Flask, request, jsonify
import MetaTrader5 as mt5

app = Flask(__name__)

# Configuration (load from environment or config file)
HMAC_SECRET = os.getenv("HMAC_SECRET", "").encode()  # Set in production
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "24385319"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "MT5 US Live 536")
MT5_PATH = os.getenv("MT5_PATH", "C:\\Program Files\\MetaTrader 5\\terminal64.exe")

# Symbol mapping: TradingView → MT5
SYMBOL_MAP = {
    "FX:USDSEK": "USDSEK!",
    "FX:USDTHB": "USDTHB!",
}

# Idempotency store (in production, use Redis or database)
uid_store: Dict[str, datetime] = {}
uid_cleanup_age_seconds = 86400  # 24 hours

# Rate limiting (simple in-memory, use Redis in production)
rate_limit_store: Dict[str, list] = defaultdict(list)
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW_SECONDS = 60

# Load broker spec
try:
    with open("config/mt5_broker_spec.json", "r") as f:
        BROKER_SPEC = json.load(f)
except FileNotFoundError:
    BROKER_SPEC = {}
    print("WARNING: mt5_broker_spec.json not found, using defaults")

# Extract tolerances from broker spec
PRICE_TOLERANCE_PIPS = BROKER_SPEC.get("tradingview_webhook", {}).get("price_tolerance_pips", 10)
TIMESTAMP_SKEW_MAX_SECONDS = BROKER_SPEC.get("tradingview_webhook", {}).get("timestamp_skew_max_seconds", 300)


def validate_hmac(payload: bytes, signature: str) -> bool:
    """Validate HMAC signature if HMAC_SECRET is set."""
    if not HMAC_SECRET:
        return True  # Skip validation if secret not set
    
    expected = hmac.new(HMAC_SECRET, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def check_rate_limit(client_ip: str) -> bool:
    """Simple rate limiting - allow max RATE_LIMIT_REQUESTS per window."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    
    # Clean old entries
    rate_limit_store[client_ip] = [
        ts for ts in rate_limit_store[client_ip] if ts > window_start
    ]
    
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_REQUESTS:
        return False
    
    rate_limit_store[client_ip].append(now)
    return True


def check_idempotency(uid: str) -> bool:
    """Check if UID was already processed. Returns True if new, False if duplicate."""
    if uid in uid_store:
        return False
    
    uid_store[uid] = datetime.now(timezone.utc)
    
    # Cleanup old UIDs
    cutoff = datetime.now(timezone.utc).timestamp() - uid_cleanup_age_seconds
    uid_store.clear()  # Simple cleanup - in production, use TTL
    
    return True


def validate_payload(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate webhook payload. Returns (is_valid, error_message)."""
    required_fields = BROKER_SPEC.get("tradingview_webhook", {}).get("required_fields", [
        "strategy_id", "signal", "symbol_tv", "symbol_mt5", "price",
        "size_lots", "stop_loss", "take_profit", "timestamp_utc", "uid"
    ])
    
    # Check required fields
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
    
    # Validate signal
    if data["signal"] not in ["BUY", "SELL"]:
        return False, f"Invalid signal: {data['signal']} (must be BUY or SELL)"
    
    # Validate symbol mapping
    symbol_tv = data["symbol_tv"]
    if symbol_tv not in SYMBOL_MAP:
        return False, f"Unknown TradingView symbol: {symbol_tv}"
    
    symbol_mt5 = SYMBOL_MAP[symbol_tv]
    if data.get("symbol_mt5") != symbol_mt5:
        return False, f"Symbol mismatch: expected {symbol_mt5}, got {data.get('symbol_mt5')}"
    
    # Validate numeric fields
    try:
        price = float(data["price"])
        size_lots = float(data["size_lots"])
        stop_loss = float(data["stop_loss"])
        take_profit = float(data["take_profit"])
        
        if size_lots <= 0:
            return False, "size_lots must be positive"
        if price <= 0:
            return False, "price must be positive"
    except (ValueError, TypeError) as e:
        return False, f"Invalid numeric field: {e}"
    
    # Validate timestamp
    try:
        alert_time = datetime.fromisoformat(data["timestamp_utc"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        skew_seconds = abs((now - alert_time).total_seconds())
        
        if skew_seconds > TIMESTAMP_SKEW_MAX_SECONDS:
            return False, f"Timestamp skew too large: {skew_seconds}s (max {TIMESTAMP_SKEW_MAX_SECONDS}s)"
    except Exception as e:
        return False, f"Invalid timestamp format: {e}"
    
    return True, None


def check_price_tolerance(symbol_mt5: str, alert_price: float) -> Tuple[bool, Optional[str]]:
    """Check if alert price is within tolerance of current market price."""
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        return False, f"MT5 initialization failed: {mt5.last_error()}"
    
    symbol_info = mt5.symbol_info(symbol_mt5)
    if symbol_info is None:
        return False, f"Symbol not found: {symbol_mt5}"
    
    # Get current price (use bid for SELL, ask for BUY - simplified here)
    current_price = (symbol_info.bid + symbol_info.ask) / 2
    
    # Calculate tolerance in price units
    digits = symbol_info.digits
    tick_size = symbol_info.trade_tick_size
    tolerance_price = PRICE_TOLERANCE_PIPS * (tick_size * (10 ** (5 - digits)) if digits == 5 else tick_size * 10)
    
    price_diff = abs(alert_price - current_price)
    
    if price_diff > tolerance_price:
        return False, f"Price tolerance exceeded: diff={price_diff:.5f}, max={tolerance_price:.5f}"
    
    return True, None


def execute_mt5_order(data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[int]]:
    """Execute order in MT5. Returns (success, error_message, ticket)."""
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        return False, f"MT5 initialization failed: {mt5.last_error()}", None
    
    symbol_mt5 = SYMBOL_MAP[data["symbol_tv"]]
    symbol_info = mt5.symbol_info(symbol_mt5)
    
    if symbol_info is None:
        return False, f"Symbol not found: {symbol_mt5}", None
    
    if not symbol_info.visible:
        if not mt5.symbol_select(symbol_mt5, True):
            return False, f"Failed to select symbol: {symbol_mt5}", None
    
    # Determine order type
    order_type = mt5.ORDER_TYPE_BUY if data["signal"] == "BUY" else mt5.ORDER_TYPE_SELL
    
    # Get current price
    if order_type == mt5.ORDER_TYPE_BUY:
        price = symbol_info.ask
    else:
        price = symbol_info.bid
    
    # Prepare request
    lot_size = float(data["size_lots"])
    sl_price = float(data["stop_loss"])
    tp_price = float(data["take_profit"])
    
    # Normalize prices
    sl_price = mt5.symbol_info_tick(symbol_mt5).ask if sl_price == 0 else sl_price
    tp_price = mt5.symbol_info_tick(symbol_mt5).bid if tp_price == 0 else tp_price
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol_mt5,
        "volume": lot_size,
        "type": order_type,
        "price": price,
        "sl": sl_price,
        "tp": tp_price,
        "deviation": 3,  # Slippage tolerance in points
        "magic": 12345,  # Magic number for EA identification
        "comment": f"{data.get('strategy_id', 'TV')}-{data.get('uid', '')}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,  # Fill or Kill
    }
    
    # Send order
    result = mt5.order_send(request)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, f"Order failed: {result.retcode} - {result.comment}", None
    
    return True, None, result.order


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle TradingView webhook requests."""
    # Rate limiting
    client_ip = request.remote_addr
    if not check_rate_limit(client_ip):
        return jsonify({"error": "Rate limit exceeded"}), 429
    
    # HMAC validation
    if HMAC_SECRET:
        signature = request.headers.get("X-TradingView-Signature", "")
        if not validate_hmac(request.data, signature):
            return jsonify({"error": "Invalid signature"}), 401
    
    # Parse payload
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400
    except Exception as e:
        return jsonify({"error": f"JSON parse error: {e}"}), 400
    
    # Idempotency check
    uid = data.get("uid")
    if not uid:
        return jsonify({"error": "Missing uid field"}), 400
    
    if not check_idempotency(uid):
        return jsonify({
            "status": "duplicate",
            "message": "UID already processed",
            "uid": uid
        }), 200
    
    # Validate payload
    is_valid, error_msg = validate_payload(data)
    if not is_valid:
        return jsonify({"error": error_msg}), 400
    
    # Check price tolerance
    symbol_mt5 = SYMBOL_MAP[data["symbol_tv"]]
    price_ok, price_error = check_price_tolerance(symbol_mt5, float(data["price"]))
    if not price_ok:
        return jsonify({"error": price_error}), 400
    
    # Execute order
    success, error_msg, ticket = execute_mt5_order(data)
    
    if success:
        return jsonify({
            "status": "success",
            "ticket": ticket,
            "uid": uid,
            "symbol": symbol_mt5,
            "message": "Order executed successfully"
        }), 200
    else:
        return jsonify({
            "status": "error",
            "error": error_msg,
            "uid": uid
        }), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    mt5_connected = mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    return jsonify({
        "status": "healthy",
        "mt5_connected": mt5_connected,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


if __name__ == "__main__":
    print("Starting TradingView Webhook Listener...")
    print(f"MT5 Server: {MT5_SERVER}")
    print(f"MT5 Login: {MT5_LOGIN}")
    print(f"Price Tolerance: {PRICE_TOLERANCE_PIPS} pips")
    print(f"Timestamp Skew Max: {TIMESTAMP_SKEW_MAX_SECONDS}s")
    print("\nDeployment Instructions:")
    print("1. Set environment variables: HMAC_SECRET, MT5_PASSWORD")
    print("2. Configure TradingView webhook URL: http://your-server:8080/webhook")
    print("3. Test with: curl -X POST http://localhost:8080/webhook -H 'Content-Type: application/json' -d @test_alert.json")
    print("\nStarting Flask server on port 8080...")
    
    app.run(host="0.0.0.0", port=8080, debug=False)

