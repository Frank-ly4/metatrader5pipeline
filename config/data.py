import os

# Data cadence
DATA_FREQ = '2h'  # UTC assumed

# Paths (use opt_4 local data folders)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
ACTIVE_CHARTS_DIR = os.path.join(DATA_DIR, 'active_charts')
CHARTS_RAW_DIR = os.path.join(DATA_DIR, 'charts_raw')
USED_CHARTS_DIR = os.path.join(DATA_DIR, 'used_charts')
CHARTS_CLEAN_DIR = os.path.join(DATA_DIR, 'charts_cl')



