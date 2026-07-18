# [ИЗМЕНЕНО] uuid-суффикс вместо cleanup(): файлы разных пользователей не конфликтуют.
# cleanup() удалена — main.py сам удаляет конкретные файлы через delete_file().
#
# [ДОБАВЛЕНО] unique_temp_path() — генерирует уникальный путь ДО скачивания файла,
# чтобы Telethon мог скачивать файл сразу на диск потоково (по частям),
# не загружая его целиком в оперативную память (важно для файлов до 2 ГБ).
# save_temp_file() сохранена для обратной совместимости / других сценариев.

import logging
import uuid
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def unique_temp_path(filename: str) -> str:
    """
    Возвращает уникальный путь внутри TEMP_DIR для последующей потоковой записи
    (используется вместе с Telethon event.download_media(file=...), который
    скачивает файл чанками напрямую на диск, а не в память).
    Файл по этому пути ещё не существует — только путь.
    """
    safe_stem = Path(filename).stem   # имя без расширения
    safe_ext = Path(filename).suffix  # ".json"
    unique_name = f"{safe_stem}_{uuid.uuid4().hex}{safe_ext}"
    return str(config.TEMP_DIR / unique_name)


def save_temp_file(data: bytes, filename: str) -> str:
    """
    Сохраняет байты в temp директорию.
    К имени файла добавляется уникальный uuid-суффикс,
    чтобы одновременные загрузки от разных пользователей не перезаписывали друг друга.
    Оставлена для обратной совместимости (например, для не-потоковых сценариев).
    Возвращает путь как строку.
    """
    path = Path(unique_temp_path(filename))
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
