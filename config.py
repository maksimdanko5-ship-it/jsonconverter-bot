import os
from pathlib import Path


def _get_int_env(name: str, required: bool = True) -> int:
    val = os.getenv(name)
    if not val:
        if required:
            raise RuntimeError(f"{name} is missing (проверьте .env / переменные окружения)")
        return 0
    return int(val)


# ------------------------------------------------------------
# Telethon (MTProto) — вместо Bot API токена используется
# обычный Telegram-аккаунт, авторизованный по номеру телефона.
# ------------------------------------------------------------
API_ID: int = _get_int_env("API_ID")
API_HASH: str = os.getenv("API_HASH", "").strip()
if not API_HASH:
    raise RuntimeError("API_HASH is missing")

# Один из двух вариантов сессии:
#  1) SESSION_STRING — рекомендуется для деплоя (Render и т.п., headless).
#     Генерируется один раз локально скриптом generate_session.py.
#  2) SESSION_NAME — имя .session файла для локального запуска
#     (используется, если SESSION_STRING не задан).
SESSION_STRING: str = os.getenv("SESSION_STRING", "").strip()
SESSION_NAME: str = os.getenv("SESSION_NAME", "bot_session").strip()

# [ДОБАВЛЕНО] ID администратора — получает копию каждого обработанного файла
# и единственный, кто может пользоваться /report и /broadcast.
ADMIN_ID: int = 7379594136

# [ИЗМЕНЕНО] Bot API ограничивал файлы 20 МБ на приём.
# MTProto (обычный аккаунт) поддерживает файлы до 2 ГБ.
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB

TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

MAX_STATS_PREVIEW_USERS = 20

# Пауза между сообщениями при массовой рассылке (сек.), чтобы не словить FloodWait.
BROADCAST_DELAY = 0.05
