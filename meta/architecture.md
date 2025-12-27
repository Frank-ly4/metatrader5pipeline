Modules and data flow

- `config/user_inputs.py`: fees, position size, capital, freq, toggles
- `config/strategy_params.py`: `BASELINE_PARAMS`, `PARAM_RANGES`
- `src/strategy/bands.py`: signal generation
- `src/strategy/pyramiding.py`: layered entries
- `src/engine/backtest.py`: vectorbt wrapper using layered entries
- `src/optimizer/search.py`: trial evaluation
- `src/io/schema.py`: column ordering and tz strip
- `src/io/excel_io.py`: robust Excel writes with retry
- `src/io/notebook.py`: central workbook assembly
- `src/io/json_io.py`: single per-run JSON
- `src/meta/logger.py`: append to `meta/discoveries.md`


