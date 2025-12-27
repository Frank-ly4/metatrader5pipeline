import os
import shutil
from config.data import ACTIVE_CHARTS_DIR, USED_CHARTS_DIR


def move_active_to_used(filename: str) -> str:
    src = os.path.join(ACTIVE_CHARTS_DIR, filename)
    if not os.path.exists(src):
        raise FileNotFoundError(src)
    dst = os.path.join(USED_CHARTS_DIR, filename)
    os.makedirs(USED_CHARTS_DIR, exist_ok=True)
    shutil.move(src, dst)
    return dst


