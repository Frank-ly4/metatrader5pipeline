from dataclasses import dataclass
from typing import Optional

@dataclass
class TradingConfig:
    # Portfolio / backtest settings
    starting_capital: float = 1000.0         # initial cash
    position_size_per_layer: float = 0.40    # 30% per entry layer
    max_layers: int = 3                      # up to 3 pyramiding layers
    fees: float = 0.00045                    # commission per trade
    data_freq: str = "15m"                  # default data frequency
    size_type: str = "percent"           # sizing type for vectorbt portfolio
    max_orders: Optional[int] = None       # cap on orders per backtest (None for unlimited)

    # Risk management settings
    use_stops_in_backtest: bool = False      # default: no SL/TP in backtest
    stop_loss_atr_multiplier: float = 2.0    # ATR multiplier for stop loss
    take_profit_atr_multiplier: float = 3.0  # ATR multiplier for take profit

    def get_backtest_config(self) -> dict:
        return {
            'init_cash': self.starting_capital,
            'size': self.position_size_per_layer,
            'fees': self.fees,
            'data_freq': self.data_freq,
            'max_layers': self.max_layers,
            'size_type': self.size_type,
            'max_orders': self.max_orders,
        }
