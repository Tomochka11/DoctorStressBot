import os
import logging
import httpx  # Заменили синхронный requests на асинхронный httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
# На Render ключи должны называться именно так в настройках Environment Variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

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
"""

# ========== ФУНКЦИЯ ЗАПРОСА К DEEPSEEK С ПАМЯТЬЮ ==========
async def ask_deepseek(history: list) -> str:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Собираем полный пакет данных: системный промпт + вся история сообщений юзера
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    
    data = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.9,
        "max_tokens": 1024
    }
    
    # Использование асинхронного клиента httpx не блокирует бота для других людей
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(DEEPSEEK_URL, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logging.error(f"DeepSeek error: {e}")
            return "⚠️ Что-то пошло не так у меня в мозгах. Попробуй переформулировать или напиши позже."

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # При старте или перезапуске очищаем историю диалога
    context.user_data["history"] = []
    context.user_data["is_neutral"] = False  # Флаг выхода из роли циника
    
    await update.message.reply_text(
        "🧠 Привет! Я Доктор Стресс.\n"
        "Расскажи, что тебя бесит, и я помогу выпустить пар.\n"
        "Если захочешь выйти из роли — просто напиши СТОП.\n"
        "Сбросить память диалога: /clear"
    )

async def clear_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["history"] = []
    context.user_data["is_neutral"] = False
    await update.message.reply_text("🧼 Память очищена. Можешь начинать бесить меня заново.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    if not user_text:
        return

    # Инициализация истории, если её нет в памяти текущего юзера
    if "history" not in context.user_data:
        context.user_data["history"] = []
    if "is_neutral" not in context.user_data:
        context.user_data["is_neutral"] = False

    # 1. СТРОГИЙ ФИЛЬТР БЕЗОПАСНОСТИ НА БЭКЕНДЕ
    danger_words = ["суицид", "селфхарм", "порезать себя", "убить себя", "покончить с собой", "вскрыть вены"]
    if any(word in user_text.lower() for word in danger_words):
        context.user_data["is_neutral"] = True  # Навсегда отключаем циника для этой сессии
        await update.message.reply_text(
            "Стоп. Это небезопасно. Я выключаю режим персонажа.\n"
            "Пожалуйста, обратитесь на горячую линию психологической помощи: 8-800-2000-122 (Россия) или к живому врачу."
        )
        return

    # 2. ОБРАБОТКА КОМАНДЫ СТОП
    if user_text.strip().upper() in ("СТОП", "ХВАТИТ", "STOP"):
        context.user_data["is_neutral"] = True
        await update.message.reply_text(
            "✅ Хорошо, я выключаю режим циника.\n"
            "Если хочешь, можем просто поговорить по-человечески. Чтобы вернуть Доктора Стресса, введи /clear"
        )
        return

    # 3. ЕСЛИ БОТ В НЕЙТРАЛЬНОМ РЕЖИМЕ
    if context.user_data["is_neutral"]:
        # Обычный поддерживающий ответ без ИИ, либо можно слать в DeepSeek с другим промптом
        await update.message.reply_text("Я тебя слышу. Давай спокойно обсудим это, без сарказма. Что произошло?")
        return

    # Добавляем сообщение пользователя в память (ограничим историю последними 10 репликами, чтобы не тратить токены)
    context.user_data["history"].append({"role": "user", "content": user_text})
    context.user_data["history"] = context.user_data["history"][-10:]

    # Отправка в DeepSeek
    # Отправляем "Бот печатает...", чтобы пользователь видел активность
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    reply = await ask_deepseek(context.user_data["history"])
    
    # Добавляем ответ ИИ в историю, чтобы он помнил свои слова
    context.user_data["history"].append({"role": "assistant", "content": reply})
    
    await update.message.reply_text(reply)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Update {update} caused error {context.error}")

# ========== ЗАПУСК ==========
def main():
    logging.basicConfig(level=logging.INFO)
    
    # Проверка обязательных переменных перед стартом
    if not TELEGRAM_TOKEN or not DEEPSEEK_API_KEY:
        print("❌ ОШИБКА: Не заданы переменные окружения TELEGRAM_BOT_TOKEN или DEEPSEEK_API_KEY!")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_memory))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("✅ Бот Доктор Стресс запущен и готов к тестам!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
