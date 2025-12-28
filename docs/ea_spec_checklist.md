# EA Specification Checklist - USDSEK & USDTHB

## 1. Lot Sizing Formula (Risk Percent → Lots)

### Formula
```
Risk Amount (USD) = Account Equity × Risk Percent / 100
Stop Loss Distance (points) = |Entry Price - Stop Loss Price| / Tick Size
Risk Per Lot (USD) = Stop Loss Distance × Tick Value × Contract Size / Tick Size
Lot Size = Risk Amount / Risk Per Lot
Lot Size = Normalize to Volume Step (round to 0.01)
```

### Worked Examples (Account: $10,000, Risk: 0.25%)

#### Example 1: USDSEK BUY
- **Account Equity**: $10,000
- **Risk Percent**: 0.25%
- **Risk Amount**: $10,000 × 0.0025 = **$25.00**
- **Entry Price**: 11.23456
- **Stop Loss**: 11.20000
- **Stop Loss Distance**: |11.23456 - 11.20000| = 0.03456
- **Tick Size**: 0.00001
- **Stop Loss Points**: 0.03456 / 0.00001 = **3,456 points**
- **Tick Value**: 1.00 USD
- **Contract Size**: 100,000
- **Risk Per Lot**: 3,456 × 1.00 × 100,000 / 0.00001 = **$345.60** (simplified: 3,456 × 1.00 = $3,456 per lot)
- **Correction**: For 5-digit symbol, 1 point = 0.00001, so 3,456 points = 3,456 × 0.00001 = 0.03456
- **Risk Per Lot (Correct)**: (Entry - SL) × Contract Size × Tick Value = 0.03456 × 100,000 × 1.00 = **$3,456.00**
- **Lot Size**: $25.00 / $3,456.00 = **0.0072 lots**
- **Normalized**: Round to 0.01 step → **0.01 lots** (minimum)

#### Example 2: USDTHB BUY
- **Account Equity**: $10,000
- **Risk Percent**: 0.25%
- **Risk Amount**: $10,000 × 0.0025 = **$25.00**
- **Entry Price**: 35.500
- **Stop Loss**: 35.400
- **Stop Loss Distance**: |35.500 - 35.400| = 0.100
- **Tick Size**: 0.001
- **Stop Loss Points**: 0.100 / 0.001 = **100 points**
- **Tick Value**: 1.00 USD
- **Contract Size**: 100,000
- **Risk Per Lot**: (Entry - SL) × Contract Size × Tick Value = 0.100 × 100,000 × 1.00 = **$10,000.00**
- **Lot Size**: $25.00 / $10,000.00 = **0.0025 lots**
- **Normalized**: Round to 0.01 step → **0.01 lots** (minimum)

**Note**: Both examples result in minimum lot size (0.01) due to high margin requirements. Consider:
- Increasing risk percent for larger positions
- Using tighter stop losses
- Verifying USDTHB margin (20,000 USD/lot seems unusually high)

---

## 2. Pre-Trade Checks

### Margin Available Check
```mql5
double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
double requiredMargin = SymbolInfoDouble(symbol, SYMBOL_MARGIN_INITIAL) * lotSize;
if (freeMargin < requiredMargin) {
    Print("Insufficient margin: required=", requiredMargin, ", available=", freeMargin);
    return false;
}
```

### Max Open Lots Check
```mql5
double totalLots = 0.0;
for (int i = 0; i < PositionsTotal(); i++) {
    if (PositionSelectByTicket(PositionGetTicket(i))) {
        if (PositionGetString(POSITION_SYMBOL) == symbol) {
            totalLots += PositionGetDouble(POSITION_VOLUME);
        }
    }
}
if (totalLots + lotSize > MAX_TOTAL_LOTS_PER_SYMBOL) {
    Print("Max lots exceeded for symbol: ", symbol);
    return false;
}
```

### Daily Loss Limit Check (FTMO-style)
```mql5
double dailyStartBalance = GetDailyStartBalance(); // Store at start of day
double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
double dailyLoss = dailyStartBalance - currentEquity;
double maxDailyLoss = dailyStartBalance * MAX_DAILY_LOSS_PERCENT / 100.0;

if (dailyLoss >= maxDailyLoss) {
    Print("Daily loss limit reached: ", dailyLoss, " (max: ", maxDailyLoss, ")");
    DisableTrading();
    return false;
}
```

---

## 3. Order Placement Logic

### Market Entry
```mql5
MqlTradeRequest request = {};
MqlTradeResult result = {};

request.action = TRADE_ACTION_DEAL;
request.symbol = symbol;
request.volume = lotSize;
request.type = (signal == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
request.price = (request.type == ORDER_TYPE_BUY) ? SymbolInfoDouble(symbol, SYMBOL_ASK) : SymbolInfoDouble(symbol, SYMBOL_BID);
request.sl = stopLoss;
request.tp = takeProfit;
request.deviation = MAX_SLIPPAGE_POINTS;
request.magic = MAGIC_NUMBER;
request.comment = comment;
request.type_time = ORDER_TIME_GTC;
request.type_filling = ORDER_FILLING_FOK; // Fill or Kill

if (!OrderSend(request, result)) {
    Print("Order failed: ", result.retcode, " - ", result.comment);
    // Retry logic with exponential backoff
    return false;
}
```

### SL/TP Placement
- **Method**: Separate orders (not OCO) - SL/TP set in OrderSend request
- **Handling Partial Fills**: FOK mode prevents partial fills - order either fills completely or is rejected
- **Retry/Backoff**: 
  - Retry on `TRADE_RETCODE_REQUOTE`: Wait 1s, retry up to 3 times
  - Retry on `TRADE_RETCODE_NO_MONEY`: Check margin, wait 2s, retry once
  - No retry on `TRADE_RETCODE_MARKET_CLOSED`: Log and skip

---

## 4. P/L Conversion Rules

### Profit Currency Handling
- **USDSEK**: Profit currency is SEK, margin currency is USD
- **USDTHB**: Profit currency is THB, margin currency is USD
- **MT5 Auto-Conversion**: MT5 automatically converts P/L to account currency (USD)
- **Equity Calculation**: Use `AccountInfoDouble(ACCOUNT_EQUITY)` - MT5 handles conversion

### Margin Checks
```mql5
// MT5 handles conversion automatically
double equity = AccountInfoDouble(ACCOUNT_EQUITY); // Already in account currency (USD)
double margin = AccountInfoDouble(ACCOUNT_MARGIN); // Already in account currency (USD)
double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE); // Already in account currency (USD)
```

**No manual conversion needed** - MT5 handles all currency conversions internally.

---

## 5. Emergency Stop Rules

### Drawdown-Based Stop
```mql5
double maxEquity = GetMaxEquity(); // Track peak equity
double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
double drawdownPercent = (maxEquity - currentEquity) / maxEquity * 100.0;

if (drawdownPercent >= EMERGENCY_STOP_DRAWDOWN_PERCENT) {
    Print("Emergency stop: Drawdown=", drawdownPercent, "%");
    CloseAllPositions();
    DisableTrading();
    SendAlert("Emergency stop triggered: Drawdown limit exceeded");
}
```

### Consecutive Losses Stop
```mql5
int consecutiveLosses = GetConsecutiveLosses();
if (consecutiveLosses >= EMERGENCY_STOP_CONSECUTIVE_LOSSES) {
    Print("Emergency stop: Consecutive losses=", consecutiveLosses);
    CloseAllPositions();
    DisableTrading();
    SendAlert("Emergency stop triggered: Consecutive loss limit exceeded");
}
```

### Manual Reset Required
- Emergency stop requires **manual reset** via EA input parameter or external command
- Log all emergency stops with timestamp, reason, and account state

---

## 6. Logging Fields

### Required Log Fields
```mql5
struct TradeLog {
    datetime execution_time;      // DealTime()
    double fill_price;            // DealPrice()
    double requested_price;       // Order price
    double slippage;              // FillPrice - RequestPrice
    double commission;            // DealCommission()
    ulong ticket_id;              // DealTicket()
    datetime server_time;         // TimeCurrent()
    string symbol;                // DealSymbol()
    double volume;                // DealVolume()
    ENUM_DEAL_TYPE deal_type;     // DealType()
    double profit;                // DealProfit()
    double swap;                  // DealSwap()
};
```

### Log to File
```mql5
void LogTrade(TradeLog& log) {
    string filename = "trade_log_" + TimeToString(TimeCurrent(), TIME_DATE) + ".csv";
    int file = FileOpen(filename, FILE_WRITE | FILE_CSV | FILE_COMMON);
    if (file != INVALID_HANDLE) {
        FileWrite(file, 
            TimeToString(log.execution_time),
            DoubleToString(log.fill_price, _Digits),
            DoubleToString(log.slippage, _Digits),
            DoubleToString(log.commission, 2),
            IntegerToString(log.ticket_id),
            TimeToString(log.server_time),
            log.symbol,
            DoubleToString(log.volume, 2)
        );
        FileClose(file);
    }
}
```

---

## 7. FTMO-Style Risk Rules

### Daily Loss Limit: 5%
- Track daily starting balance
- Disable trading if daily loss ≥ 5% of starting balance
- Reset at start of new trading day

### Max Drawdown: 10%
- Track peak equity
- Disable trading if drawdown ≥ 10% from peak
- Requires manual reset

### Profit Target: 10%
- Track starting balance
- Optional: Disable trading if profit ≥ 10% (for challenge accounts)

### Minimum Trading Days: 5
- Track trading days (days with at least one trade)
- Enforce minimum before considering account "passed"

---

## 8. Position Scaling Rules

### Max Adds: 3
- Track number of adds per position
- Reject add orders if adds >= 3

### Add Distance: ATR-based
```mql5
double atr = iATR(symbol, timeframe, atr_period);
double addDistance = atr * MIN_ADDON_DISTANCE_ATR;
double lastEntryPrice = GetLastEntryPrice(positionTicket);

if (MathAbs(currentPrice - lastEntryPrice) < addDistance) {
    Print("Add distance too close: ", MathAbs(currentPrice - lastEntryPrice), " < ", addDistance);
    return false;
}
```

### Max Total Lots Per Symbol
- Enforce max total lots across all positions for a symbol
- Default: 10 lots (adjustable)

---

## 9. Order Timeout & Reprice

### Timeout: 5 seconds
```mql5
datetime orderStartTime = TimeCurrent();
if (!OrderSend(request, result)) {
    // Wait for fill or timeout
    while (TimeCurrent() - orderStartTime < ORDER_TIMEOUT_SECONDS) {
        Sleep(100);
        if (OrderSelect(result.order)) {
            if (OrderGetInteger(ORDER_STATE) == ORDER_STATE_FILLED) {
                return true; // Filled
            }
        }
    }
    // Timeout - cancel and reprice
    OrderCancel(result.order);
    // Reprice and retry (optional)
}
```

### Limit vs Market Orders
- **Default**: Market orders (use_limit_orders = false)
- **Limit orders**: Only if use_limit_orders = true and price tolerance allows
- **FOK mode**: Prevents partial fills - order fills completely or is rejected

---

## 10. Error Handling

### Retry Logic
```mql5
int retries = 0;
int maxRetries = 3;
int backoffSeconds[] = {1, 2, 4};

while (retries < maxRetries) {
    if (OrderSend(request, result)) {
        return true; // Success
    }
    
    if (result.retcode == TRADE_RETCODE_REQUOTE) {
        Sleep(backoffSeconds[retries] * 1000);
        // Update price and retry
        request.price = (request.type == ORDER_TYPE_BUY) ? SymbolInfoDouble(symbol, SYMBOL_ASK) : SymbolInfoDouble(symbol, SYMBOL_BID);
        retries++;
    } else {
        // Non-retryable error
        Print("Order failed: ", result.retcode, " - ", result.comment);
        return false;
    }
}
```

### Error Codes to Handle
- `TRADE_RETCODE_REQUOTE`: Retry with updated price
- `TRADE_RETCODE_NO_MONEY`: Check margin, retry once
- `TRADE_RETCODE_MARKET_CLOSED`: Log and skip
- `TRADE_RETCODE_INVALID_STOPS`: Adjust SL/TP and retry
- `TRADE_RETCODE_TRADE_DISABLED`: Emergency stop - disable trading

