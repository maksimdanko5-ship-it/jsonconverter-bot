import os
from pathlib import Path

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

# [ДОБАВЛЕНО] ID администратора — получает копию каждого обработанного файла
ADMIN_ID: int = 7379594136

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

MAX_STATS_PREVIEW_USERS = 20
