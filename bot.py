import os
import re
import asyncio
import tempfile
from openpyxl import load_workbook
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

keyboard = ReplyKeyboardMarkup(
    [["Zvonok", "Gudman"]],
    resize_keyboard=True
)

user_queues = {}
user_tasks = {}


def clean_phone(value):
    if value is None:
        return None

    digits = re.sub(r"\D", "", str(value))

    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]

    if len(digits) == 10:
        digits = "7" + digits

    return digits if len(digits) >= 10 else None


def process_gudman(file_path):
    wb = load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active

    numbers = []

    for row in ws.iter_rows(values_only=True):
        phone = clean_phone(row[0])

        if phone:
            numbers.append(phone)

    return numbers


def process_zvonok(file_path):
    wb = load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active

    rows = ws.iter_rows(values_only=True)
    headers = next(rows)

    headers_lower = [
        str(h).strip().lower() if h else ""
        for h in headers
    ]

    phone_col = None
    status_col = None
    client_answer_col = None

    for i, h in enumerate(headers_lower):
        if "номер" in h and "телефон" in h:
            phone_col = i

        if "статус звонка" in h:
            status_col = i

        if (
            "транскрибация клиента" in h
            or "транскрипция клиента" in h
            or "ответ клиента" in h
        ):
            client_answer_col = i

    if phone_col is None:
        raise Exception("Не нашёл столбец 'Номер телефона'.")

    if status_col is None:
        raise Exception("Не нашёл столбец 'Статус звонка'.")

    if client_answer_col is None:
        raise Exception("Не нашёл столбец 'Транскрибация клиента' или 'Ответ клиента'.")

    bad_answers = [
        "номер набран неправильно",
        "проверьте корректность наборам",
        "проверьте корректность набора",
        "номер не используется",
    ]

    numbers = []

    for row in rows:
        status = (
            str(row[status_col]).strip().lower()
            if row[status_col] else ""
        )

        client_answer = (
            str(row[client_answer_col]).strip().lower()
            if row[client_answer_col] else ""
        )

        if status == "закончен удачно":
            if any(bad in client_answer for bad in bad_answers):
                continue

            phone = clean_phone(row[phone_col])

            if phone:
                numbers.append(phone)

    return numbers


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = None

    await update.message.reply_text(
        "Выбери режим обработки:",
        reply_markup=keyboard
    )


async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()

    if text == "zvonok":
        context.user_data["mode"] = "Zvonok"

    elif text == "gudman":
        context.user_data["mode"] = "Gudman"

    else:
        await update.message.reply_text(
            "Нажми кнопку Zvonok или Gudman.",
            reply_markup=keyboard
        )
        return

    await update.message.reply_text(
        f"Режим выбран: {context.user_data['mode']} ✅\n"
        f"Кидай Excel-файлы .xlsx"
    )


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")

    if not mode:
        await update.message.reply_text(
            "Сначала выбери режим: Zvonok или Gudman.",
            reply_markup=keyboard
        )
        return

    document = update.message.document

    if not document.file_name.lower().endswith(".xlsx"):
        await update.message.reply_text("Отправь Excel-файл в формате .xlsx")
        return

    user_id = update.effective_user.id

    if user_id not in user_queues:
        user_queues[user_id] = []

    user_queues[user_id].append({
        "document": document,
        "mode": mode,
        "chat_id": update.effective_chat.id
    })

    await update.message.reply_text(f"Файл принят ✅\n{document.file_name}")

    if user_id not in user_tasks or user_tasks[user_id].done():
        user_tasks[user_id] = asyncio.create_task(
            process_queue(context, user_id)
        )


async def process_queue(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    await asyncio.sleep(3)

    queue = user_queues.get(user_id, [])
    total = len(queue)

    if total == 0:
        return

    chat_id = queue[0]["chat_id"]

    progress_message = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔴 0% | Начинаю обработку файлов: {total}"
    )

    processed = 0

    while user_queues.get(user_id):
        item = user_queues[user_id].pop(0)

        document = item["document"]
        mode = item["mode"]

        input_path = None
        output_path = None

        try:
            percent = int((processed / total) * 100)
            emoji = get_progress_emoji(percent)

            await progress_message.edit_text(
                f"{emoji} {percent}% | Обрабатываю файл {processed + 1} из {total}\n"
                f"{document.file_name}"
            )

            tg_file = await document.get_file()

            safe_name = document.file_name.replace("/", "_").replace("\\", "_")
            input_path = os.path.join(tempfile.gettempdir(), safe_name)

            await tg_file.download_to_drive(input_path)

            if mode == "Zvonok":
                numbers = process_zvonok(input_path)
                output_name = safe_name.replace(".xlsx", "_zvonok_result.txt")
            else:
                numbers = process_gudman(input_path)
                output_name = safe_name.replace(".xlsx", "_gudman_result.txt")

            output_path = os.path.join(tempfile.gettempdir(), output_name)

            with open(output_path, "w", encoding="utf-8") as f:
                for number in numbers:
                    f.write(str(number) + "\n")

            with open(output_path, "rb") as file:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=file,
                    filename=output_name,
                    caption=(
                        f"Готово ✅\n"
                        f"Файл: {document.file_name}\n"
                        f"Режим: {mode}\n"
                        f"Найдено номеров: {len(numbers)}"
                    )
                )

        except Exception as e:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Ошибка при обработке файла {document.file_name}:\n{e}"
            )

        finally:
            if input_path and os.path.exists(input_path):
                os.remove(input_path)

            if output_path and os.path.exists(output_path):
                os.remove(output_path)

        processed += 1

    await progress_message.edit_text(
        "✅ 100% | Готово, все файлы обработаны"
    )


def get_progress_emoji(percent):
    if percent < 25:
        return "🔴"
    elif percent < 50:
        return "🟠"
    elif percent < 75:
        return "🟡"
    elif percent < 100:
        return "🟢"
    else:
        return "✅"


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не найден")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            choose_mode
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_file
        )
    )

    print("🚀 Бот запущен")

    app.run_polling()


if __name__ == "__main__":
    main()
