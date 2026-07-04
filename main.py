import asyncio
import logging
import random
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

import action_logger
import config
import parser as chat_parser
import formatter
import file_service
import users_service
import stats as stats_module

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box
from rich.align import Align

# ============================================================
# 👇 ВСТАВЬ ЭТО СЮДА (ПОСЛЕ ВСЕХ ИМПОРТОВ, ДО ЛЮБОЙ ЛОГИКИ)
# ============================================================
from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def wake_up():
    return "I'm alive!", 200

def run_web():
    app.run(host='0.0.0.0', port=10000)

# Запускаем веб-сервер в фоновом потоке
threading.Thread(target=run_web, daemon=True).start()
# ============================================================

# ------------------------------------------------------------
# 1. НАСТРОЙКА КОНСОЛИ
# ------------------------------------------------------------
console = Console()
# Логи пишем только в файл (чтобы не дублировать в консоль)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 2. КРАСИВЫЙ БАННЕР ПРИ ЗАПУСКЕ
# ------------------------------------------------------------
def print_banner():
    banner = Text()
    banner.append("╔═══════════════════════════════════════════════════════════════╗\n", style="green")
    banner.append("║  [bold]🤖 JSON CONVERTER v2.0[/]  •  [green]ONLINE[/]  •  ", style="green")
    banner.append(f"[yellow]Админ: @tylerFe[/]  •  ", style="yellow")
    banner.append(f"[cyan]Запущен: {datetime.now().strftime('%d.%m.%Y %H:%M')}[/]", style="cyan")
    banner.append(" " * 10 + "║\n", style="green")
    banner.append("╚═══════════════════════════════════════════════════════════════╝", style="green")
    console.print(Align.center(banner))
    console.print()

# ------------------------------------------------------------
# 3. КРАСИВЫЙ ВЫВОД ЛОГОВ (основная фишка)
# ------------------------------------------------------------
def log_event(user, action, details="", status="OK"):
    now = datetime.now().strftime("%H:%M:%S")
    name = user.full_name or "Без имени"
    username = f"(@{user.username})" if user.username else ""

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
# 4. ИНИЦИАЛИЗАЦИЯ БОТА
# ------------------------------------------------------------
bot = Bot(token=config.TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ------------------------------------------------------------
# 5. УВЕДОМЛЕНИЕ АДМИНА (копия)
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
        await bot.send_document(
            config.ADMIN_ID,
            FSInputFile(txt_path, filename=txt_filename),
            caption=f"from: {sender_name} (id: {sender_id})",
        )
        admin_stats = stats_text if len(stats_text) <= 4000 else stats_text[:4000] + "\n…"
        await bot.send_message(config.ADMIN_ID, f"<pre>{admin_stats}</pre>")
        log_event(None, "📤 Копия отправлена администратору")
    except Exception as e:
        logger.exception("Failed to notify admin")
        log_event(None, f"❌ Ошибка отправки копии: {e}", status="ERROR")

# ------------------------------------------------------------
# 6. FSM ДЛЯ ФИДБЕКА
# ------------------------------------------------------------
class FeedbackStates(StatesGroup):
    waiting_for_feedback = State()

# ------------------------------------------------------------
# 7. ОБРАБОТЧИКИ КОМАНД
# ------------------------------------------------------------
@dp.message(F.text == "/start")
async def cmd_start(m: Message) -> None:
    await users_service.register_user(m.from_user.id)
    log_event(m.from_user, "Команда /start")
    await m.answer(
        "👋 Отправь JSON-экспорт чата из Telegram.\n"
        "Я конвертирую его в TXT и посчитаю статистику.\n\n"
        "Команды:\n"
        "/stats — статистика бота\n"
        "/instruction — как получить JSON-экспорт\n"
        "/feedback — отправить отзыв автору"
    )

@dp.message(F.text == "/stats")
async def cmd_stats(m: Message) -> None:
    count = await users_service.get_users_count()
    log_event(m.from_user, "Команда /stats", f"Всего пользователей: {count}")
    await m.answer(
        f"📈 <b>Статистика бота</b>\n\n"
        f"👥 Уникальных пользователей: <b>{count}</b>\n\n"
        f"Отправь JSON-файл, чтобы получить статистику конкретного чата."
    )

@dp.message(F.text == "/instruction")
async def cmd_instruction(m: Message) -> None:
    await users_service.register_user(m.from_user.id)
    log_event(m.from_user, "Команда /инструкция")
    await m.answer(
        "📱 <b>Как получить JSON-экспорт чата из Telegram:</b>\n\n"
        "1. Откройте Telegram Desktop или Web-версию\n"
        "2. Перейдите в нужный чат\n"
        "3. Нажмите на название чата/аватар → <b>Экспорт истории чата</b>\n"
        "4. Выберите формат <b>JSON</b>\n"
        "5. Отметьте, что нужно экспортировать (сообщения, фото и т.д.)\n"
        "6. Нажмите <b>Экспортировать</b> и подождите\n"
        "7. Отправьте полученный <b>.json</b> файл этому боту\n\n"
        "📌 Бот конвертирует его в TXT и покажет статистику.",
        parse_mode=ParseMode.HTML,
    )

@dp.message(F.text == "/report")
async def cmd_report(m: Message) -> None:
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("❌ Только для администратора.")
        log_event(m.from_user, "Попытка доступа к /report", status="ERROR")
        return

    log_event(m.from_user, "Команда /report (админ)")

    if not action_logger.LOG_FILE.exists():
        await m.answer("📭 Отчётов пока нет.")
        return

    await m.answer_document(
        FSInputFile(action_logger.LOG_FILE, filename="actions_log.csv"),
        caption="📊 Отчёт по действиям пользователей"
    )

# ------------------------------------------------------------
# 8. ФИДБЕК
# ------------------------------------------------------------
@dp.message(F.text == "/feedback")
async def cmd_feedback(m: Message, state: FSMContext) -> None:
    await users_service.register_user(m.from_user.id)
    log_event(m.from_user, "Команда /feedback (начало)")

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_feedback")]
    ])

    await m.answer(
        "💬 Напишите свой отзыв, предложение или сообщите об ошибке.\n\n"
        "✍️ Просто отправьте текстовое сообщение.\n"
        "🔄 Если передумали — нажмите кнопку 'Отмена'.",
        reply_markup=cancel_kb
    )
    await state.set_state(FeedbackStates.waiting_for_feedback)

@dp.message(FeedbackStates.waiting_for_feedback, F.text)
async def process_feedback(m: Message, state: FSMContext) -> None:
    feedback_text = m.text.strip()
    if not feedback_text:
        await m.answer("❌ Текст не может быть пустым. Попробуйте ещё раз.")
        return

    log_event(m.from_user, "💬 Отзыв", f"{feedback_text[:50]}..." if len(feedback_text) > 50 else feedback_text)

    user_info = f"{m.from_user.full_name} (@{m.from_user.username}) [id: {m.from_user.id}]"
    admin_message = (
        f"📩 <b>Новый отзыв!</b>\n\n"
        f"👤 От: {user_info}\n"
        f"📅 Время: {m.date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"<b>Текст:</b>\n{feedback_text}"
    )

    try:
        await bot.send_message(config.ADMIN_ID, admin_message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Не удалось отправить фидбек админу: {e}")
        await m.answer("⚠️ Не удалось отправить отзыв. Попробуйте позже.")
        await state.clear()
        return

    await m.answer("✅ Спасибо за ваш отзыв! Он отправлен автору.")
    await state.clear()

@dp.callback_query(F.data == "cancel_feedback")
async def cancel_feedback_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отмена. Вы можете начать заново командой /feedback.")
    await callback.answer()

@dp.message(F.text == "/cancel")
async def cancel_cmd(m: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await m.answer("❌ Отменено.")
    else:
        await m.answer("🤷 Нет активных действий для отмены.")

# ------------------------------------------------------------
# 9. ОБРАБОТКА ФАЙЛОВ
# ------------------------------------------------------------
@dp.message(F.document)
async def handle_file(m: Message) -> None:
    await users_service.register_user(m.from_user.id)
    file_name = m.document.file_name or "unknown.json"
    file_size = m.document.file_size or 0
    size_kb = file_size / 1024
    size_mb = size_kb / 1024
    size_str = f"{size_mb:.2f} MB" if size_mb > 1 else f"{size_kb:.1f} KB"

    log_event(m.from_user, "📤 Загрузка файла", f"{file_name} ({size_str})")

    if not file_name.endswith(".json"):
        await m.answer("❌ Принимаю только <b>.json</b> файлы.")
        log_event(m.from_user, "Ошибка: не JSON", file_name, status="ERROR")
        return

    if file_size > config.MAX_FILE_SIZE:
        limit_mb = config.MAX_FILE_SIZE // 1024 // 1024
        await m.answer(
            f"❌ <b>Файл слишком большой для обработки ботом.</b>\n\n"
            f"📦 Максимальный размер: <b>{limit_mb} МБ</b>.\n\n"
            "Если ваш JSON-файл превышает этот лимит, вы можете:\n"
            "• Использовать сервисы на основе <b>ChatGPT</b> (например, ChatGPT Plus с поддержкой файлов) или другие нейросети, "
            "которые умеют работать с большими объёмами данных и могут предоставить вам единый TXT-файл.\n"
            "• Уменьшить размер экспорта, исключив при экспорте медиафайлы (фото, видео, голосовые) — это значительно сократит вес.\n\n"
            "📌 Альтернативно, вы можете разбить переписку на несколько частей и обработать их по отдельности.",
            parse_mode=ParseMode.HTML,
        )
        log_event(m.from_user, "Ошибка: превышен размер", f"{file_name} ({size_str})", status="ERROR")
        return

    await m.answer("⏳ Обрабатываю файл...")

    json_path: str | None = None
    txt_path: str | None = None

    try:
        tg_file = await bot.get_file(m.document.file_id)
        downloaded = await bot.download_file(tg_file.file_path)

        if downloaded is None:
            await m.answer("❌ Не удалось скачать файл с серверов Telegram.")
            log_event(m.from_user, "Ошибка скачивания", file_name, status="ERROR")
            return

        json_path = file_service.save_temp_file(downloaded.read(), file_name)

        messages = chat_parser.parse_json(json_path)

        if not messages:
            await m.answer("⚠️ В файле не найдено сообщений.")
            log_event(m.from_user, "Ошибка: нет сообщений", file_name, status="ERROR")
            return

        txt_path = str(Path(json_path).with_suffix(".txt"))
        formatter.format_messages(messages, txt_path)

        chat_stats = stats_module.collect_stats(messages)
        stats_text = stats_module.format_stats(chat_stats)

        txt_filename = Path(file_name).with_suffix(".txt").name
        await m.answer_document(
            FSInputFile(txt_path, filename=txt_filename),
            caption="✅ Конвертация готова",
        )
        user_stats = stats_text if len(stats_text) <= 4000 else stats_text[:4000] + "\n…"
        await m.answer(f"<pre>{user_stats}</pre>")

        await m.answer(
            "🙏 Если вам помог мой бесплатный бот, вы можете поддержать автора звёздами!\n\n"
            "👨‍💻 Автор: @tylerFe"
        )

        sender_name = m.from_user.full_name or str(m.from_user.id)
        await _notify_admin(
            sender_id=m.from_user.id,
            sender_name=sender_name,
            txt_path=txt_path,
            original_filename=file_name,
            stats_text=stats_text,
        )

        logger.info(
            "Processed file from user %s (%s): %d messages",
            m.from_user.id, sender_name, len(messages),
        )

        log_event(m.from_user, "✅ Конвертация завершена", f"{len(messages)} сообщений, TXT: {txt_filename}")

    except ValueError as e:
        logger.warning("File processing error: %s", e)
        await m.answer(f"❌ Ошибка файла: {e}")
        log_event(m.from_user, "Ошибка обработки (ValueError)", str(e), status="ERROR")

    except Exception as e:
        import traceback
        error_text = traceback.format_exc()
        logger.exception("Unexpected error")
        
        try:
            await bot.send_message(
                config.ADMIN_ID,
                f"⚠️ <b>Ошибка у пользователя</b>\n"
                f"👤 {m.from_user.full_name} (@{m.from_user.username}) [id: {m.from_user.id}]\n"
                f"📎 Файл: {file_name}\n\n"
                f"<b>Текст ошибки:</b>\n<code>{error_text[:3000]}</code>",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

        await m.answer("❌ Внутренняя ошибка. Попробуй ещё раз.")
        log_event(m.from_user, "Неожиданная ошибка", str(e), status="ERROR")

    finally:
        file_service.delete_file(json_path)
        file_service.delete_file(txt_path)

# ------------------------------------------------------------
# 10. ЗАПУСК
# ------------------------------------------------------------
async def main() -> None:
    print_banner()
    console.print("[bold green]✅ Бот запущен и готов к работе![/]")
    console.print("[dim]─────────────────────────────────────────────────────────────[/]\n")
    logger.info("Bot starting... Admin ID: %s", config.ADMIN_ID)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())