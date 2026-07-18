import asyncio
import logging
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors import (
    UserIsBlockedError,
    UserDeactivatedError,
    UserDeactivatedBanError,
    PeerIdInvalidError,
    ChatWriteForbiddenError,
    UserPrivacyRestrictedError,
    FloodWaitError,
)

import action_logger
import config
import parser as chat_parser
import formatter
import file_service
import users_service
import stats as stats_module

from rich.console import Console
from rich.text import Text
from rich.align import Align

# ============================================================
# 👇 ВЕБ-СЕРВЕР ДЛЯ RENDER (чтобы не ругался на порт)
# ============================================================
from flask import Flask
import threading
import aiohttp

app = Flask(__name__)


@app.route('/')
def wake_up():
    return "I'm alive!", 200


def run_web():
    app.run(host='0.0.0.0', port=10000)


threading.Thread(target=run_web, daemon=True).start()

PING_INTERVAL = 600
PING_URL = "https://jsonconverter-bot.onrender.com"


async def ping_self():
    while True:
        await asyncio.sleep(PING_INTERVAL)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(PING_URL, timeout=10) as resp:
                    status = resp.status
                    if status == 200:
                        add_log("[green]✅ Self-ping успешен (сервер бодрствует)[/]")
                    else:
                        add_log(f"[yellow]⚠️ Self-ping вернул статус {status}[/]")
        except Exception as e:
            add_log(f"[red]❌ Self-ping ошибка: {e}[/]")

# ------------------------------------------------------------
# 1. НАСТРОЙКА КОНСОЛИ
# ------------------------------------------------------------
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 2. БУФЕР ЛОГОВ И ФУНКЦИЯ add_log
# ------------------------------------------------------------
log_buffer = []


def add_log(message):
    log_buffer.append(message)
    if len(log_buffer) > 100:
        log_buffer.pop(0)
    console.print(message)

# ------------------------------------------------------------
# 3. КРАСИВЫЙ БАННЕР
# ------------------------------------------------------------


def print_banner():
    banner = Text()
    banner.append("╔═══════════════════════════════════════════════════════════════╗\n", style="green")
    banner.append("║  [bold]🤖 JSON CONVERTER v3.0 (Telethon)[/]  •  [green]ONLINE[/]  •  ", style="green")
    banner.append("[yellow]Админ: @tylerFe[/]  •  ", style="yellow")
    banner.append(f"[cyan]Запущен: {datetime.now().strftime('%d.%m.%Y %H:%M')}[/]", style="cyan")
    banner.append(" " * 10 + "║\n", style="green")
    banner.append("╚═══════════════════════════════════════════════════════════════╝", style="green")
    console.print(Align.center(banner))
    console.print()

# ------------------------------------------------------------
# 4. ВЫВОД ЛОГОВ
# ------------------------------------------------------------


def _user_full_name(user) -> str:
    """Собирает отображаемое имя из Telethon-объекта User (first_name/last_name)."""
    return " ".join(filter(None, [getattr(user, "first_name", None), getattr(user, "last_name", None)])).strip() or "Без имени"


def log_event(user, action, details="", status="OK"):
    now = datetime.now().strftime("%H:%M:%S")
    name = _user_full_name(user)
    username = f"(@{user.username})" if getattr(user, "username", None) else ""

    if status == "ERROR":
        icon = "[red]✖[/]"
    else:
        icon = "[green]✔[/]"

    line = Text()
    line.append(f"[{now}] ", style="dim")
    line.append(f"{icon} ")
    line.append(f"{name} ")
    if username:
        line.append(f"{username} ")
    line.append(f"| {action}")
    if details:
        line.append(f" {details}")

    console.print(line)
    logger.info(f"{user.id} {action} {details} {status}")
    action_logger.log_action(user, action, details, status)

# ------------------------------------------------------------
# 5. ИНИЦИАЛИЗАЦИЯ КЛИЕНТА (Telethon / MTProto)
# ------------------------------------------------------------
# [ИЗМЕНЕНО] Вместо aiogram.Bot(token=...) используется обычный Telegram-аккаунт,
# авторизованный по номеру телефона (API_ID/API_HASH + сессия).
# Это снимает ограничение Bot API на приём файлов (≈20 МБ) и позволяет
# принимать файлы до 2 ГБ (лимит самого MTProto для обычных аккаунтов).
_session = StringSession(config.SESSION_STRING) if config.SESSION_STRING else config.SESSION_NAME
client = TelegramClient(_session, config.API_ID, config.API_HASH)
client.parse_mode = "html"  # HTML-разметка по умолчанию, как раньше в aiogram

# ------------------------------------------------------------
# 6. УВЕДОМЛЕНИЕ АДМИНА (копия)
# ------------------------------------------------------------


async def _notify_admin(
    sender_id: int,
    sender_name: str,
    txt_path: str,
    original_filename: str,
    stats_text: str,
) -> None:
    if sender_id == config.ADMIN_ID:
        return

    try:
        txt_filename = Path(original_filename).with_suffix(".txt").name
        await client.send_file(
            config.ADMIN_ID,
            txt_path,
            attributes=[DocumentAttributeFilename(txt_filename)],
            caption=f"from: {sender_name} (id: {sender_id})",
        )
        admin_stats = stats_text if len(stats_text) <= 4000 else stats_text[:4000] + "\n…"
        await client.send_message(config.ADMIN_ID, f"<pre>{admin_stats}</pre>")
        add_log("[cyan]📤 Копия отправлена администратору[/]")
    except Exception as e:
        logger.exception("Failed to notify admin")
        add_log(f"[red]❌ Не удалось отправить копию: {e}[/]")

# ------------------------------------------------------------
# 7. СОСТОЯНИЕ ФИДБЕКА
# ------------------------------------------------------------
# [ИЗМЕНЕНО] Telethon не имеет встроенного FSM, как aiogram.
# Состояние "ожидаем текст отзыва" хранится в простом множестве ID пользователей.
_awaiting_feedback: set[int] = set()

# ------------------------------------------------------------
# 8. ОБРАБОТЧИКИ КОМАНД
# ------------------------------------------------------------


@client.on(events.NewMessage(pattern=r'^/start$'))
async def cmd_start(event):
    user = await event.get_sender()
    await users_service.register_user(user.id)
    log_event(user, "Команда /start")
    await event.respond(
        "👋 Отправь JSON-экспорт чата из Telegram.\n"
        "Я конвертирую его в TXT и посчитаю статистику.\n\n"
        "Команды:\n"
        "/stats — статистика бота\n"
        "/instruction — как получить JSON-экспорт\n"
        "/feedback — отправить отзыв автору"
    )


@client.on(events.NewMessage(pattern=r'^/stats$'))
async def cmd_stats(event):
    user = await event.get_sender()
    count = await users_service.get_users_count()
    log_event(user, "Команда /stats", f"Всего пользователей: {count}")
    await event.respond(
        f"📈 <b>Статистика бота</b>\n\n"
        f"👥 Уникальных пользователей: <b>{count}</b>\n\n"
        f"Отправь JSON-файл, чтобы получить статистику конкретного чата."
    )


@client.on(events.NewMessage(pattern=r'^/instruction$'))
async def cmd_instruction(event):
    user = await event.get_sender()
    await users_service.register_user(user.id)
    log_event(user, "Команда /инструкция")
    await event.respond(
        "📱 <b>Как получить JSON-экспорт чата из Telegram:</b>\n\n"
        "1. Откройте Telegram Desktop или Web-версию\n"
        "2. Перейдите в нужный чат\n"
        "3. Нажмите на название чата/аватар → <b>Экспорт истории чата</b>\n"
        "4. Выберите формат <b>JSON</b>\n"
        "5. Отметьте, что нужно экспортировать (сообщения, фото и т.д.)\n"
        "6. Нажмите <b>Экспортировать</b> и подождите\n"
        "7. Отправьте полученный <b>.json</b> файл этому боту\n\n"
        "📌 Бот конвертирует его в TXT и покажет статистику."
    )


@client.on(events.NewMessage(pattern=r'^/report$'))
async def cmd_report(event):
    user = await event.get_sender()
    if user.id != config.ADMIN_ID:
        await event.respond("❌ Только для администратора.")
        log_event(user, "Попытка доступа к /report", status="ERROR")
        return

    log_event(user, "Команда /report (админ)")

    if not action_logger.LOG_FILE.exists():
        await event.respond("📭 Отчётов пока нет.")
        return

    await client.send_file(
        event.chat_id,
        str(action_logger.LOG_FILE),
        attributes=[DocumentAttributeFilename("actions_log.csv")],
        caption="📊 Отчёт по действиям пользователей",
    )

# ------------------------------------------------------------
# 8.1 АДМИНСКАЯ РАССЫЛКА
# ------------------------------------------------------------
# [ДОБАВЛЕНО] /broadcast <текст> — доступно только config.ADMIN_ID.
# Использует существующую базу пользователей (users.json через users_service),
# рассылает сообщение каждому, кто хоть раз писал боту, и присылает отчёт.


@client.on(events.NewMessage(pattern=r'(?s)^/broadcast(?:\s+(.+))?$'))
async def cmd_broadcast(event):
    user = await event.get_sender()

    if user.id != config.ADMIN_ID:
        await event.respond("❌ Только для администратора.")
        log_event(user, "Попытка доступа к /broadcast", status="ERROR")
        return

    text = event.pattern_match.group(1)
    if not text or not text.strip():
        await event.respond(
            "✏️ Использование: <code>/broadcast текст сообщения</code>\n"
            "Отправьте команду с текстом, который нужно разослать всем пользователям бота."
        )
        return
    text = text.strip()

    log_event(user, "Команда /broadcast (админ)", text[:50] + ("..." if len(text) > 50 else ""))

    user_ids = await users_service.get_all_user_ids()
    total = len(user_ids)
    success = 0
    failed = 0

    status_msg = await event.respond(f"📤 Рассылка запущена. Всего пользователей: <b>{total}</b>")

    for uid in user_ids:
        try:
            await client.send_message(uid, text)
            success += 1
        except FloodWaitError as e:
            # Telegram просит подождать — ждём и повторяем один раз.
            await asyncio.sleep(e.seconds + 1)
            try:
                await client.send_message(uid, text)
                success += 1
            except Exception as e2:
                logger.warning("Broadcast retry failed for %s: %s", uid, e2)
                failed += 1
        except (
            UserIsBlockedError,
            UserDeactivatedError,
            UserDeactivatedBanError,
            PeerIdInvalidError,
            ChatWriteForbiddenError,
            UserPrivacyRestrictedError,
            ValueError,
        ) as e:
            # Пользователь заблокировал бота / удалил аккаунт / недоступен — пропускаем,
            # рассылка не прерывается.
            logger.info("Broadcast skipped for %s: %s", uid, e)
            failed += 1
        except Exception as e:
            logger.warning("Broadcast unexpected error for %s: %s", uid, e)
            failed += 1

        # Небольшая пауза между сообщениями, чтобы не словить FloodWait.
        await asyncio.sleep(config.BROADCAST_DELAY)

    report = (
        f"📊 <b>Рассылка завершена</b>\n\n"
        f"Всего пользователей: <b>{total}</b>\n"
        f"✅ Успешно отправлено: <b>{success}</b>\n"
        f"❌ Не удалось отправить: <b>{failed}</b>"
    )
    try:
        await status_msg.edit(report)
    except Exception:
        await event.respond(report)

    log_event(user, "Рассылка завершена", f"Успешно: {success}, Ошибок: {failed}, Всего: {total}")

# ------------------------------------------------------------
# 9. ФИДБЕК
# ------------------------------------------------------------


@client.on(events.NewMessage(pattern=r'^/feedback$'))
async def cmd_feedback(event):
    user = await event.get_sender()
    await users_service.register_user(user.id)
    log_event(user, "Команда /feedback (начало)")

    await event.respond(
        "💬 Напишите свой отзыв, предложение или сообщите об ошибке.\n\n"
        "✍️ Просто отправьте текстовое сообщение.\n"
        "🔄 Если передумали — нажмите кнопку 'Отмена'.",
        buttons=[[Button.inline("❌ Отмена", data="cancel_feedback")]],
    )
    _awaiting_feedback.add(user.id)


@client.on(events.NewMessage(
    func=lambda e: bool(e.raw_text) and not e.raw_text.startswith('/') and e.sender_id in _awaiting_feedback
))
async def process_feedback(event):
    user = await event.get_sender()
    feedback_text = (event.raw_text or "").strip()
    if not feedback_text:
        await event.respond("❌ Текст не может быть пустым. Попробуйте ещё раз.")
        return

    log_event(user, "💬 Отзыв", f"{feedback_text[:50]}..." if len(feedback_text) > 50 else feedback_text)

    user_info = f"{_user_full_name(user)} (@{user.username}) [id: {user.id}]"
    admin_message = (
        f"📩 <b>Новый отзыв!</b>\n\n"
        f"👤 От: {user_info}\n"
        f"📅 Время: {event.message.date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"<b>Текст:</b>\n{feedback_text}"
    )

    try:
        await client.send_message(config.ADMIN_ID, admin_message)
    except Exception as e:
        logger.error(f"Не удалось отправить фидбек админу: {e}")
        await event.respond("⚠️ Не удалось отправить отзыв. Попробуйте позже.")
        _awaiting_feedback.discard(user.id)
        return

    await event.respond("✅ Спасибо за ваш отзыв! Он отправлен автору.")
    _awaiting_feedback.discard(user.id)


@client.on(events.CallbackQuery(data=b"cancel_feedback"))
async def cancel_feedback_callback(event):
    _awaiting_feedback.discard(event.sender_id)
    await event.edit("❌ Отмена. Вы можете начать заново командой /feedback.")
    await event.answer()


@client.on(events.NewMessage(pattern=r'^/cancel$'))
async def cancel_cmd(event):
    user_id = event.sender_id
    if user_id in _awaiting_feedback:
        _awaiting_feedback.discard(user_id)
        await event.respond("❌ Отменено.")
    else:
        await event.respond("🤷 Нет активных действий для отмены.")

# ------------------------------------------------------------
# 10. ОБРАБОТКА ФАЙЛОВ (ПОТОКОВАЯ, ДО 2 ГБ)
# ------------------------------------------------------------


def _progress_bar(percent: int, width: int = 12) -> str:
    """Рисует текстовый прогресс-бар: [███░░░░░░░] 30%"""
    percent = max(0, min(100, percent))
    filled = int(width * percent / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {percent}%"


@client.on(events.NewMessage(func=lambda e: e.document is not None))
async def handle_file(event):
    user = await event.get_sender()
    await users_service.register_user(user.id)

    file_name = event.file.name or "unknown.json"
    file_size = event.file.size or 0
    size_kb = file_size / 1024
    size_mb = size_kb / 1024
    size_str = f"{size_mb:.2f} MB" if size_mb > 1 else f"{size_kb:.1f} KB"

    log_event(user, "📤 Загрузка файла", f"{file_name} ({size_str})")

    if not file_name.lower().endswith(".json"):
        await event.respond("❌ Принимаю только <b>.json</b> файлы.")
        log_event(user, "Ошибка: не JSON", file_name, status="ERROR")
        return

    if file_size > config.MAX_FILE_SIZE:
        limit_gb = config.MAX_FILE_SIZE / 1024 / 1024 / 1024
        await event.respond(
            f"❌ <b>Файл слишком большой для обработки ботом.</b>\n\n"
            f"📦 Максимальный размер: <b>{limit_gb:.0f} ГБ</b>.\n\n"
            "Если ваш JSON-файл превышает этот лимит, вы можете:\n"
            "• Использовать сервисы на основе <b>ChatGPT</b> (например, ChatGPT Plus с поддержкой файлов) или другие нейросети, "
            "которые умеют работать с большими объёмами данных и могут предоставить вам единый TXT-файл.\n"
            "• Уменьшить размер экспорта, исключив при экспорте медиафайлы (фото, видео, голосовые) — это значительно сократит вес.\n\n"
            "📌 Альтернативно, вы можете разбить переписку на несколько частей и обработать их по отдельности."
        )
        log_event(user, "Ошибка: превышен размер", f"{file_name} ({size_str})", status="ERROR")
        return

    # ---------- Прогресс-сообщение ----------
    progress_msg = await event.respond("⏳ Скачиваю файл...")

    json_path: str | None = None
    txt_path: str | None = None

    # [ИЗМЕНЕНО] Прогресс скачивания — Telethon вызывает этот колбэк по мере
    # получения чанков файла, что позволяет обновлять статус без буферизации
    # всего файла целиком.
    last_percent = -1

    async def _download_progress(current: int, total: int) -> None:
        nonlocal last_percent
        percent = int(current * 100 / total) if total else 0
        if percent - last_percent >= 10 or percent >= 100:
            last_percent = percent
            try:
                await progress_msg.edit(f"⏳ Скачиваю файл... {_progress_bar(percent)}")
            except Exception:
                pass  # не критично, если не удалось обновить статус (например, флуд-лимит)

    try:
        # ---------- Скачивание (потоково, напрямую на диск) ----------
        # [ИЗМЕНЕНО] Раньше файл полностью загружался в память (BytesIO),
        # затем записывался на диск. Теперь Telethon скачивает файл чанками
        # сразу в целевой путь на диске — весь файл никогда не хранится в RAM целиком.
        target_path = file_service.unique_temp_path(file_name)
        json_path = await event.download_media(file=target_path, progress_callback=_download_progress)

        if not json_path:
            await progress_msg.edit("❌ Не удалось скачать файл с серверов Telegram.")
            log_event(user, "Ошибка скачивания", file_name, status="ERROR")
            return

        # ---------- Парсинг JSON (в отдельном потоке) ----------
        await progress_msg.edit(f"⏳ Парсинг JSON... {_progress_bar(20)}")
        messages = await asyncio.to_thread(chat_parser.parse_json, json_path)

        if not messages:
            await progress_msg.edit("⚠️ В файле не найдено сообщений.")
            log_event(user, "Ошибка: нет сообщений", file_name, status="ERROR")
            return

        # ---------- Статистика (в потоке) ----------
        await progress_msg.edit(f"⏳ Анализ статистики... {_progress_bar(50)}")
        chat_stats = await asyncio.to_thread(stats_module.collect_stats, messages)
        stats_text = stats_module.format_stats(chat_stats)

        # ---------- Формирование TXT (в потоке) ----------
        await progress_msg.edit(f"⏳ Формирование TXT... {_progress_bar(75)}")
        txt_path = str(Path(json_path).with_suffix(".txt"))
        await asyncio.to_thread(formatter.format_messages, messages, txt_path)

        # ---------- Отправка файла ----------
        await progress_msg.edit(f"📤 Отправляю результат... {_progress_bar(90)}")
        txt_filename = Path(file_name).with_suffix(".txt").name
        await client.send_file(
            event.chat_id,
            txt_path,
            attributes=[DocumentAttributeFilename(txt_filename)],
            caption="✅ Конвертация готова",
        )
        user_stats = stats_text if len(stats_text) <= 4000 else stats_text[:4000] + "\n…"
        await event.respond(f"<pre>{user_stats}</pre>")

        await event.respond(
            "🙏 Если вам помог мой бесплатный бот, вы можете поддержать автора звёздами!\n\n"
            "👨‍💻 Автор: @tylerFe"
        )

        # ---------- Уведомление админа ----------
        sender_name = _user_full_name(user) if (user.first_name or user.last_name) else str(user.id)
        await _notify_admin(
            sender_id=user.id,
            sender_name=sender_name,
            txt_path=txt_path,
            original_filename=file_name,
            stats_text=stats_text,
        )

        # ---------- Финальный прогресс ----------
        await progress_msg.edit(f"✅ Готово! {_progress_bar(100)}")
        logger.info(
            "Processed file from user %s (%s): %d messages",
            user.id, sender_name, len(messages),
        )
        log_event(user, "✅ Конвертация завершена", f"{len(messages)} сообщений, TXT: {txt_filename}")

        # [ДОБАВЛЕНО] Явно освобождаем ссылку на список сообщений — для больших
        # чатов (сотни тысяч сообщений) это позволяет сборщику мусора освободить
        # память сразу после отправки результата, а не ждать выхода из функции.
        del messages

    except ValueError as e:
        logger.warning("File processing error: %s", e)
        await progress_msg.edit(f"❌ Ошибка файла: {e}")
        log_event(user, "Ошибка обработки (ValueError)", str(e), status="ERROR")

    except Exception as e:
        error_text = traceback.format_exc()
        logger.exception("Unexpected error")

        try:
            await client.send_message(
                config.ADMIN_ID,
                f"⚠️ <b>Ошибка у пользователя</b>\n"
                f"👤 {_user_full_name(user)} (@{user.username}) [id: {user.id}]\n"
                f"📎 Файл: {file_name}\n\n"
                f"<b>Текст ошибки:</b>\n<code>{error_text[:3000]}</code>",
            )
        except Exception:
            pass

        await progress_msg.edit("❌ Внутренняя ошибка. Попробуй ещё раз.")
        log_event(user, "Неожиданная ошибка", str(e), status="ERROR")

    finally:
        # [ВАЖНО] Гарантированно удаляем временные файлы (JSON и TXT) вне зависимости
        # от исхода — это защищает от накопления файлов на диске (утечка "по диску"),
        # а не только от утечек в оперативной памяти.
        file_service.delete_file(json_path)
        file_service.delete_file(txt_path)

# ------------------------------------------------------------
# 11. ЗАПУСК
# ------------------------------------------------------------


async def main() -> None:
    print_banner()
    add_log("[bold green]✅ Бот запускается...[/]")
    add_log("[dim]─────────────────────────────────────────────────────────────[/]")
    logger.info("Bot starting... Admin ID: %s", config.ADMIN_ID)

    await client.start()  # если сессия уже авторизована — запрос телефона/кода не потребуется
    me = await client.get_me()
    add_log(f"[bold green]✅ Авторизован как {me.first_name} (@{me.username}, id={me.id})[/]")

    asyncio.create_task(ping_self())
    add_log("[cyan]🔄 Self-ping запущен (каждые 10 минут)[/]")

    await client.run_until_disconnected()


if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
