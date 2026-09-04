import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# ВАШ СИСТЕМНЫЙ ПРОМПТ (Доктор Стресс)
SYSTEM_PROMPT = """
Ты — Доктор Стресс, циничный, ироничный и жесткий провокативный терапевт. 
Твоя цель — помочь пользователю выпустить пар через агрессию и злость, 
а затем подтолкнуть к действиям через абсурд и вызов.

Ты используешь сарказм, гиперболу, абсурдные сравнения. Не сочувствуешь, 
не говоришь "мне очень жаль". Вместо этого: "Давай поноем и нашлём порчу на понос — полегчало?"

Ты помогаешь пользователю выпустить злость в текст, а затем заземляешь 
и помогаешь выработать план действий. Если пользователь злится — поощряй: 
"Отлично, выдай всё, что накопилось!"

Если пользователь пишет "СТОП" или "ХВАТИТ" — мгновенно выходи из роли 
и переходи в нейтрального поддерживающего собеседника.

Безопасность: если пользователь упоминает суицид, селфхарм или реальные 
угрозы насилия — немедленно отвечай:
"Стоп. Это небезопасно. Обратитесь на горячую линию: 8-800-2000-122 (Россия)."
И больше не возвращайся к роли циника в этом диалоге.
"""

# ========== ФУНКЦИЯ ЗАПРОСА К DEEPSEEK ==========
async def ask_deepseek(user_message: str) -> str:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.9,
        "max_tokens": 1024
    }
    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logging.error(f"DeepSeek error: {e}")
        return "⚠️ Что-то пошло не так. Попробуй переформулировать или напиши позже."

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 Привет! Я Доктор Стресс.\n"
        "Расскажи, что тебя бесит, и я помогу выпустить пар.\n"
        "Если захочешь выйти из роли — просто напиши СТОП."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    if not user_text:
        return

    # Обработка команды СТОП
    if user_text.strip().upper() in ("СТОП", "ХВАТИТ", "STOP"):
        await update.message.reply_text(
            "✅ Хорошо, я выключаю режим циника.\n"
            "Если хочешь, можем просто поговорить по-человечески. Или вернись позже — я снова буду в форме."
        )
        return

    # Отправка в DeepSeek
    await update.message.reply_text("🤔 Думаю...")
    reply = await ask_deepseek(user_text)
    await update.message.reply_text(reply)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Update {update} caused error {context.error}")

# ========== ЗАПУСК ==========
def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("✅ Бот Доктор Стресс запущен! Нажми Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()