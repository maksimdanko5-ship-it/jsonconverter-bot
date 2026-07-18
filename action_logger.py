import csv
from datetime import datetime
from pathlib import Path

LOG_FILE = Path("actions_log.csv")


# Создаём файл с заголовками, если его нет
def _init_log():
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Дата", "Время", "User ID", "Имя", "Юзернейм",
                "Действие", "Детали", "Статус"
            ])


def log_action(user, action: str, details: str = "", status: str = "OK"):
    """Записывает действие пользователя в CSV-отчёт.

    [ИЗМЕНЕНО] Раньше рассчитывалось на aiogram-объект User (с полем .full_name).
    Теперь бот работает через Telethon, чей User отдаёт first_name/last_name
    по отдельности, поэтому full_name собирается вручную, если атрибута нет.
    """
    _init_log()

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    user_id = user.id
    full_name = getattr(user, "full_name", None) or " ".join(
        filter(None, [getattr(user, "first_name", None), getattr(user, "last_name", None)])
    ).strip() or "Без имени"
    username = f"@{user.username}" if getattr(user, "username", None) else "нет"

    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            date_str, time_str, user_id, full_name, username,
            action, details, status
        ])
