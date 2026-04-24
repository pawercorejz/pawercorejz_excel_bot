import os
import re
import pandas as pd
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь Excel файл (.xlsx)")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document

    if not doc.file_name.endswith(".xlsx"):
        await update.message.reply_text("Нужен файл .xlsx")
        return

    file = await doc.get_file()
    path = f"/tmp/{doc.file_name}"
    await file.download_to_drive(path)

    df = pd.read_excel(path)

    good = df[df["Статус звонка"].astype(str).str.strip() == "Закончен удачно"]

    numbers = (
        good["Номер телефона"]
        .astype(str)
        .apply(lambda x: re.sub(r"\D", "", x))
        .tolist()
    )

    out = "/tmp/result.txt"

    with open(out, "w") as f:
        for n in numbers:
            f.write(n + "\n")

    with open(out, "rb") as f:
        await update.message.reply_document(f, filename="numbers.txt")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.run_polling()

if __name__ == "__main__":
    main()