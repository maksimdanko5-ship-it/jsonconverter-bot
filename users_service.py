# [ИЗМЕНЕНО] threading.Lock → asyncio.Lock; функции register_user и get_users_count
# стали async — вызываются через await в async-контексте бота.

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_FILE = Path("users.json")

# [ИЗМЕНЕНО] asyncio.Lock вместо threading.Lock.
# В Python 3.10+ безопасно создавать на уровне модуля — привязывается к loop при первом await.
_lock = asyncio.Lock()


def _load() -> set[int]:
    """Синхронное чтение файла (вызывается внутри async-функций под _lock)."""
    if not _FILE.exists():
        return set()
    try:
        raw = _FILE.read_text(encoding="utf-8")
        return set(json.loads(raw))
    except Exception as e:
        logger.error("Failed to load users.json: %s", e)
        return set()


def _save(users: set[int]) -> None:
    """
    Atomic write через .tmp-файл: защита от повреждения данных при краше.
    Синхронная — вызывается внутри async-функций под _lock.
    """
    tmp = _FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(sorted(users)), encoding="utf-8")
        tmp.replace(_FILE)
    except Exception as e:
        logger.error("Failed to save users.json: %s", e)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


# [ИЗМЕНЕНО] async def + async with _lock → корректно работает в event loop aiogram
async def register_user(user_id: int) -> bool:
    """
    Регистрирует пользователя.
    Возвращает True если пользователь новый, False если уже был.
    """
    async with _lock:
        users = _load()
        if user_id in users:
            return False
        users.add(user_id)
        _save(users)
        return True


# [ИЗМЕНЕНО] async def + async with _lock
async def get_users_count() -> int:
    async with _lock:
        return len(_load())
