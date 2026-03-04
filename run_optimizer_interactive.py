import os
import pandas as pd
import questionary
from datetime import datetime

# --- Setup Project Path ---
# This allows the script to be run from anywhere and still find the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
import sys
sys.path.insert(0, PROJECT_ROOT)
# --- End Setup ---

from src.optimizer.search import (
    random_search, grid_search, lhs_search, sobol_search, evaluate_collect_kfold
)
from src.strategy.bands import compute_signals
from config.strategy_params import PARAM_RANGES
from src.io.results_writer import save_results


def get_chart_files():
    """Lists available chart files for selection."""
    chart_dir = os.path.join('data', 'active_charts')
    if not os.path.isdir(chart_dir):
        return []
    return sorted([f for f in os.listdir(chart_dir) if f.endswith('.csv')])

def get_available_regimes(chart_files: list[str]) -> list[str]:
    """Reads the first available chart to find unique regime labels."""
    if not chart_files:
        return []
    try:
        chart_path = os.path.join('data', 'active_charts', chart_files[0])
        df = pd.read_csv(chart_path)
        if 'regime' in df.columns:
            return ['All'] + sorted(df['regime'].unique().tolist())
    except Exception:
        return ['All']
    return ['All']

def ask_questions(chart_files: list[str], regimes: list[str]):
    """Main function to drive the interactive question-and-answer flow."""
    if not chart_files:
        questionary.print("No charts found in 'data/active_charts/'. Please add charts and try again.", style="bold red").ask()
        return None

    questions = [
        {
            'type': 'checkbox',
            'name': 'charts',
            'message': 'Select charts to optimize on (space to select, enter to confirm):',
            'choices': chart_files,
            'validate': lambda a: True if len(a) > 0 else "Please select at least one chart."
        },
        {
            'type': 'select',
            'name': 'regime',
            'message': 'Select a market regime to optimize for:',
            'choices': regimes
        },
        {
            'type': 'select',
            'name': 'method',
            'message': 'Select optimization method:',
            'choices': ['random', 'grid', 'lhs', 'sobol']
        },
        {
            'type': 'text',
            'name': 'trials',
            'message': 'Enter number of trials:',
            'validate': lambda t: True if t.isdigit() and int(t) > 0 else "Please enter a positive number."
        },
        {
            'type': 'confirm',
            'name': 'use_kfold',
            'message': 'Use K-Fold cross-validation?',
            'default': True
        },
        {
            'type': 'text',
            'name': 'k_folds',
            'message': 'Enter number of K-Folds:',
            'default': '5',
            'when': lambda a: a.get('use_kfold', False),
            'validate': lambda t: True if t.isdigit() and int(t) > 1 else "Please enter a number greater than 1."
        },
        {
            'type': 'text',
            'name': 'embargo_frac',
            'message': 'Enter embargo fraction (e.g., 0.05 for 5%):',
            'default': '0.05',
            'when': lambda a: a.get('use_kfold', False),
            'validate': lambda t: True if 0 < float(t) < 1 else "Please enter a fraction between 0 and 1."
        },
        {
            'type': 'select',
            'name': 'metric',
            'message': 'Select primary metric to optimize for:',
            'choices': ['total_return', 'sharpe_ratio', 'calmar_ratio', 'profit_factor', 'win_rate', 'expectancy']
        },
        {
            'type': 'checkbox',
            'name': 'outputs',
            'message': 'Select output formats to generate:',
            'choices': ['CSV', 'JSON', 'Excel'],
            'default': 'CSV,JSON'
        }
    ]

    answers = questionary.prompt(questions)
    if not answers: # User cancelled with Ctrl+C
        return None

    # Convert numeric strings to numbers
    if answers.get('trials'):
        answers['trials'] = int(answers['trials'])
    if answers.get('k_folds'):
        answers['k_folds'] = int(answers['k_folds'])
    if answers.get('embargo_frac'):
        answers['embargo_frac'] = float(answers['embargo_frac'])

    return answers

def main():
    """Main execution block."""
    run_ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    print(f"--- Interactive Optimizer --- (Run ID: {run_ts})")

    chart_files = get_chart_files()
    regimes = get_available_regimes(chart_files)
    
    settings = ask_questions(chart_files, regimes)
    if not settings:
        print("Optimization cancelled.")
        return

    print("\nStarting optimization with the following settings:")
    print(pd.Series(settings))

    # Map search method string to function
    search_methods = {
        'random': random_search,
        'grid': grid_search,
        'lhs': lhs_search,
        'sobol': sobol_search
    }
    search_func = search_methods[settings['method']]

    all_results = []
    for chart_name in settings['charts']:
        print(f"\nProcessing chart: {chart_name}...")
        chart_path = os.path.join('data', 'active_charts', chart_name)
        price_df = pd.read_csv(chart_path, index_col=0, parse_dates=True)

        toggles = {'chart_name': chart_name}

        if settings['use_kfold']:
            # K-Fold evaluation is per-parameter-set, not a search method itself.
            # For simplicity here, we'll just run one evaluation with default params.
            # A full implementation would integrate this into the search loops.
            print("  Running single K-Fold evaluation (Note: Full search + K-Fold not yet implemented in this TUI)...")
            # Example with first param set
            params = {k: v[0] for k, v in PARAM_RANGES.items()}
            kfold_rows, _ = evaluate_collect_kfold(
                price_df, params, toggles, compute_signals,
                regime_filter=settings['regime'],
                k_folds=settings['k_folds'],
                embargo_frac=settings['embargo_frac']
            )
            for row in kfold_rows:
                row['chart'] = chart_name
            all_results.extend(kfold_rows)
        else:
            results_df, _ = search_func(
                price=price_df,
                param_ranges=PARAM_RANGES,
                toggles=toggles,
                n_trials=settings['trials'],
                metric=settings['metric'],
                compute_signals_func=compute_signals,
                regime_filter=settings['regime'] # Pass the regime filter
            )
            results_df['chart'] = chart_name
            all_results.append(results_df)

    if not all_results:
        print("\nOptimization finished with no results.")
        return

    final_df = pd.concat(all_results, ignore_index=True)
    final_df = final_df.sort_values(by=settings['metric'], ascending=False)

    print(f"\nOptimization complete. Top 5 results by '{settings['metric']}':")
    print(final_df.head(5))

    # --- Saving Results ---
    save_results(
        results_df=final_df,
        run_id=run_ts,
        settings=settings,
        output_formats=settings['outputs']
    )

if __name__ == '__main__':
    main()