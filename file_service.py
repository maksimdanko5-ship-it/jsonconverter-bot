# [ИЗМЕНЕНО] uuid-суффикс вместо cleanup(): файлы разных пользователей не конфликтуют.
# cleanup() удалена — main.py сам удаляет конкретные файлы через delete_file().

import logging
import uuid
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def save_temp_file(data: bytes, filename: str) -> str:
    """
    Сохраняет байты в temp директорию.
    [ИЗМЕНЕНО] К имени файла добавляется уникальный uuid-суффикс,
    чтобы одновременные загрузки от разных пользователей не перезаписывали друг друга.
    Возвращает путь как строку.
    """
    safe_stem = Path(filename).stem   # имя без расширения
    safe_ext  = Path(filename).suffix  # ".json"
    unique_name = f"{safe_stem}_{uuid.uuid4().hex}{safe_ext}"
    path = config.TEMP_DIR / unique_name
    path.write_bytes(data)
    return str(path)


def delete_file(path: str | None) -> None:
    """
    Удаляет конкретный файл. Безопасен при path=None и при отсутствии файла.
    Используется в finally-блоке main.py вместо глобального cleanup().
    """
    if not path:
        return
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except Exception as e:
        logger.warning("Could not delete file %s: %s", path, e)

# [УДАЛЕНО] cleanup() — удаляла ВСЕ файлы из temp, что ломало параллельные запросы.
