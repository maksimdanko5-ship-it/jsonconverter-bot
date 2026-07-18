"""
Скрипт для ОДНОРАЗОВОЙ локальной авторизации Telegram-аккаунта через Telethon.

Зачем нужен:
    Render (и любой другой headless-хостинг) не может ввести код из SMS/Telegram
    интерактивно. Поэтому авторизация делается один раз локально (на своём ПК),
    а результат — session string — сохраняется в переменную окружения
    SESSION_STRING на хостинге. При следующих запусках бот стартует сразу,
    без повторного ввода телефона и кода.

Как использовать:
    1. Заполните API_ID и API_HASH в файле .env (получить на https://my.telegram.org).
    2. Запустите:  python generate_session.py
    3. Введите номер телефона, затем код из Telegram (и пароль 2FA, если включён).
    4. Скрипт напечатает длинную строку — это и есть SESSION_STRING.
    5. Скопируйте её в переменные окружения на Render (или в свой .env).

Файл-сессия НЕ создаётся — используется StringSession (сессия хранится в одной
переменной, а не в *.session файле), это удобнее для деплоя на Render.
"""

import os

from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not API_ID or not API_HASH:
    raise SystemExit(
        "Заполните API_ID и API_HASH в .env перед запуском "
        "(получить на https://my.telegram.org -> API development tools)."
    )

with TelegramClient(StringSession(), int(API_ID), API_HASH) as client:
    session_string = client.session.save()
    print("\n=== Ваша SESSION_STRING ===\n")
    print(session_string)
    print(
        "\n============================\n"
        "Сохраните эту строку в переменную окружения SESSION_STRING "
        "(в .env локально и/или в настройках Render).\n"
        "Никому не передавайте эту строку — она даёт полный доступ к аккаунту!\n"
    )
