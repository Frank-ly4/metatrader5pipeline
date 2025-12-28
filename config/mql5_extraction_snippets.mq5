//+------------------------------------------------------------------+
//| mql5_extraction_snippets.mq5                                     |
//| Purpose: one-shot script to pull authoritative broker & symbol   |
//|          specs from the running MT5 terminal (FOREX.com US Live) |
//+------------------------------------------------------------------+
#property copyright "Trading System"
#property version   "1.03"
#property script_show_inputs

//─ user-editable inputs (set in the “Inputs” tab when launching)
input string Symbol1        = "USDSEK!";            // first symbol
input string Symbol2        = "USDTHB!";            // second symbol
input bool   WriteToFile    = true;                 // write CSV to \MQL5\Files ?
input string OutputFileName = "mt5_broker_spec_extraction.csv";

//+------------------------------------------------------------------+
//| main entry                                                       |
//+------------------------------------------------------------------+
void OnStart()
{
   Print("========== MT5 Broker Specification Extraction ==========");

   bool write_file = WriteToFile;
   int  fh         = INVALID_HANDLE;

   if(write_file)
   {
      fh = FileOpen(OutputFileName,
                    FILE_WRITE | FILE_CSV | FILE_ANSI);
      if(fh == INVALID_HANDLE)
      {
         PrintFormat("⚠  Cannot open %s – continuing without file output.",
                     OutputFileName);
         write_file = false;
      }
      else
         FileWrite(fh, "section", "key", "value");   // CSV header
   }

   ExtractAccountInfo(fh);               // account block
   ExtractSymbolSpec(Symbol1, fh);       // first symbol
   ExtractSymbolSpec(Symbol2, fh);       // second symbol

   if(write_file && fh != INVALID_HANDLE)
   {
      FileClose(fh);
      PrintFormat("✅ CSV written to \\MQL5\\Files\\%s", OutputFileName);
   }

   Print("============ extraction complete ============");
}

//+------------------------------------------------------------------+
//| ACCOUNT INFO                                                     |
//+------------------------------------------------------------------+
void ExtractAccountInfo(int fh)
{
   Print("--- ACCOUNT ---");
   string server   = AccountInfoString(ACCOUNT_SERVER);
   long   login    = AccountInfoInteger(ACCOUNT_LOGIN);
   string name     = AccountInfoString(ACCOUNT_NAME);
   string currency = AccountInfoString(ACCOUNT_CURRENCY);
   string company  = AccountInfoString(ACCOUNT_COMPANY);
   long   lev      = AccountInfoInteger(ACCOUNT_LEVERAGE);
   double bal      = AccountInfoDouble (ACCOUNT_BALANCE);
   double eq       = AccountInfoDouble (ACCOUNT_EQUITY);

   PrintFormat("Server=%s  Login=%I64d  Name=%s  Currency=%s  Leverage=1:%d",
               server, login, name, currency, lev);
   PrintFormat("Balance=%.2f  Equity=%.2f", bal, eq);

   if(fh != INVALID_HANDLE)
   {
      FileWrite(fh, "account", "server",   server);
      FileWrite(fh, "account", "login",    IntegerToString((int)login));
      FileWrite(fh, "account", "name",     name);
      FileWrite(fh, "account", "currency", currency);
      FileWrite(fh, "account", "leverage", IntegerToString((int)lev));
      FileWrite(fh, "account", "balance",  DoubleToString(bal, 2));
      FileWrite(fh, "account", "equity",   DoubleToString(eq , 2));
   }
}

//+------------------------------------------------------------------+
//| SYMBOL INFO                                                      |
//+------------------------------------------------------------------+
void ExtractSymbolSpec(string sym, int fh)
{
   string symbol = sym;
   StringTrimLeft(symbol);
   StringTrimRight(symbol);
   if(symbol == "")
   {
      Print("⚠  Empty symbol supplied.");
      return;
   }

   // ensure symbol is visible in Market Watch
   if(!SymbolSelect(symbol, true))
   {
      PrintFormat("❌ %s not found (add it to Market Watch and retry)", symbol);
      if(fh != INVALID_HANDLE) FileWrite(fh, symbol, "error", "not_selected");
      return;
   }

   PrintFormat("--- SYMBOL  %s ---", symbol);

   // string props
   string desc        = SymbolInfoString(symbol, SYMBOL_DESCRIPTION);
   string cur_base    = SymbolInfoString(symbol, SYMBOL_CURRENCY_BASE);
   string cur_profit  = SymbolInfoString(symbol, SYMBOL_CURRENCY_PROFIT);
   string cur_margin  = SymbolInfoString(symbol, SYMBOL_CURRENCY_MARGIN);

   // numeric props
   long   digits       = SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   double contract_sz  = SymbolInfoDouble (symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double tick_size    = SymbolInfoDouble (symbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_value   = SymbolInfoDouble (symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_val_pf  = SymbolInfoDouble (symbol, SYMBOL_TRADE_TICK_VALUE_PROFIT);

   double min_lot      = SymbolInfoDouble (symbol, SYMBOL_VOLUME_MIN);
   double max_lot      = SymbolInfoDouble (symbol, SYMBOL_VOLUME_MAX);
   double lot_step     = SymbolInfoDouble (symbol, SYMBOL_VOLUME_STEP);

   double margin_init  = SymbolInfoDouble (symbol, SYMBOL_MARGIN_INITIAL);
   double margin_maint = SymbolInfoDouble (symbol, SYMBOL_MARGIN_MAINTENANCE);

   long   spread_prop  = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
   // Note: Execution mode is account-level, not symbol-level in MQL5
   long   exec_mode    = 0;
   long   trade_mode   = SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE);
   long   fill_mode    = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);

   double swap_long    = SymbolInfoDouble (symbol, SYMBOL_SWAP_LONG);
   double swap_short   = SymbolInfoDouble (symbol, SYMBOL_SWAP_SHORT);
   long   swap_mode    = SymbolInfoInteger(symbol, SYMBOL_SWAP_MODE);

   // Note: Commission info is not directly available via SymbolInfo functions
   // Commission is typically broker-specific and may need to be retrieved via OrderCalcProfit
   double commission   = 0.0;
   long   comm_type    = 0;

   double bid          = SymbolInfoDouble (symbol, SYMBOL_BID);
   double ask          = SymbolInfoDouble (symbol, SYMBOL_ASK);
   double spr_points   = (tick_size > 0) ? (ask - bid) / tick_size : 0;

   // console summary
   PrintFormat("Digits=%d  Contract=%g  TickSize=%.*f  TickValue=%g",
               (int)digits, contract_sz, 8, tick_size, tick_value);
   PrintFormat("MinLot=%g  MaxLot=%g  Step=%g", min_lot, max_lot, lot_step);
   PrintFormat("MarginInit=%g  MarginMaint=%g", margin_init, margin_maint);
   PrintFormat("SpreadProp=%d  SpreadNow=%.1f  Exec=%d  Fill=%d",
               (int)spread_prop, spr_points, (int)exec_mode, (int)fill_mode);
   PrintFormat("SwapLong=%g  SwapShort=%g  SwapMode=%d",
               swap_long, swap_short, (int)swap_mode);
   PrintFormat("Commission=%g  CommType=%d",
               commission, (int)comm_type);

   // CSV rows (if requested)
   if(fh != INVALID_HANDLE)
   {
      #define OUT(k,v) FileWrite(fh, symbol, k, v)
      OUT("description",          desc);
      OUT("currency_base",        cur_base);
      OUT("currency_profit",      cur_profit);
      OUT("currency_margin",      cur_margin);
      OUT("digits",               IntegerToString((int)digits));
      OUT("contract_size",        DoubleToString(contract_sz, 0));
      OUT("tick_size",            DoubleToString(tick_size, 8));
      OUT("tick_value",           DoubleToString(tick_value, 6));
      OUT("tick_value_profit",    DoubleToString(tick_val_pf, 6));
      OUT("min_lot",              DoubleToString(min_lot, 2));
      OUT("max_lot",              DoubleToString(max_lot, 2));
      OUT("lot_step",             DoubleToString(lot_step, 2));
      OUT("margin_initial",       DoubleToString(margin_init, 2));
      OUT("margin_maintenance",   DoubleToString(margin_maint, 2));
      OUT("spread_points_prop",   IntegerToString((int)spread_prop));
      OUT("exec_mode",            IntegerToString((int)exec_mode));
      OUT("trade_mode",           IntegerToString((int)trade_mode));
      OUT("fill_mode",            IntegerToString((int)fill_mode));
      OUT("swap_long",            DoubleToString(swap_long, 6));
      OUT("swap_short",           DoubleToString(swap_short, 6));
      OUT("swap_mode",            IntegerToString((int)swap_mode));
      OUT("commission",           DoubleToString(commission, 6));
      OUT("commission_type",      IntegerToString((int)comm_type));
      OUT("bid",                  DoubleToString(bid, 6));
      OUT("ask",                  DoubleToString(ask, 6));
      OUT("spread_now_points",    DoubleToString(spr_points, 1));
      #undef OUT
   }
}
//+------------------------------------------------------------------+
