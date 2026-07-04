import csv
import os
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
    """Записывает действие пользователя в CSV-отчёт"""
    _init_log()
    
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    user_id = user.id
    full_name = user.full_name or "Без имени"
    username = f"@{user.username}" if user.username else "нет"
    
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            date_str, time_str, user_id, full_name, username,
            action, details, status
        ])