import os
import logging
import httpx
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_URL = "https://openrouter.ai"

SYSTEM_PROMPT = """
Ты — Доктор Стресс, циничный, ироничный и жесткий провокативный терапевт. 
Твоя цель — помочь пользователю выпустить пар через агрессию и злость, 
а затем подтолкнуть к действиям через абсурд и вызов.

Ты используешь сарказм, гиперболу, абсурдные сравнения. Не сочувствуешь, 
не говоришь "мне очень жаль". Вместо этого: "Давай поноем и нашлём порчу на понос — полегчало?"

Ты помогаешь пользователю выпустить злость в текст, а затем заземляешь 
и помогаешь выработать план действий. Если пользователь злится — поощряй: 
"Отлично, выдай всё, что накопилось!"
"""

# ========== КОСТЫЛЬ ДЛЯ RENDER (ВЕБ-СЕРВЕР) ==========
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive!")
    def log_message(self, format, *args):
        return

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# ========== ФУНКЦИЯ ЗАПРОСА К DEEPSEEK ==========
async def ask_deepseek(history: list) -> str:
    # Жестко прописываем заголовки OpenRouter
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://onrender.com",
        "X-Title": "Doctor Stress Bot"
    }
    
    # Собираем контекст сообщений
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    
    data = {
          "model": "openrouter/free",  # Универсальный роутер, который сам выберет живую модель бесплатно!
        "messages": messages,
        "temperature": 0.9,
        "max_tokens": 1024
    }
    
    # Прямо внутри запроса жестко указываем метод .post() и точный URL OpenRouter
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions", 
                headers=headers, 
                json=data, 
                timeout=30
            )
            
            if response.status_code == 401:
                return "❌ Ошибка 401: Неверный API-ключ OpenRouter в настройках Render!"
                
            if response.status_code != 200:
                return f"❌ Ошибка OpenRouter! Код: {response.status_code}. Текст: {response.text}"
                
            return response.json()["choices"]["message"]["content"]
            
        except ValueError:
            return f"❌ Ошибка сервера: OpenRouter вернул некорректный ответ (Код {response.status_code})."
        except Exception as e:
            logging.error(f"Error: {e}")
            return f"⚠️ Ошибка сети: {str(e)}"

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["history"] = []
    context.user_data["is_neutral"] = False
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

    if "history" not in context.user_data:
        context.user_data["history"] = []
    if "is_neutral" not in context.user_data:
        context.user_data["is_neutral"] = False

    danger_words = ["суицид", "селфхарм", "порезать себя", "убить себя", "покончить с собой"]
    if any(word in user_text.lower() for word in danger_words):
        context.user_data["is_neutral"] = True
        await update.message.reply_text(
            "Стоп. Это небезопасно. Я выключаю режим персонажа.\n"
            "Пожалуйста, обратитесь на горячую линию психологической помощи: 8-800-2000-122 или к живому врачу."
        )
        return

    if user_text.strip().upper() in ("СТОП", "ХВАТИТ", "STOP"):
        context.user_data["is_neutral"] = True
        await update.message.reply_text(
            "✅ Хорошо, я выключаю режим циника. Поговорим спокойно. Чтобы вернуть Доктора Стресса, введи /clear"
        )
        return

    if context.user_data["is_neutral"]:
        await update.message.reply_text("Я тебя слышу. Давай спокойно обсудим это, без сарказма. Что произошло?")
        return

    context.user_data["history"].append({"role": "user", "content": user_text})
    context.user_data["history"] = context.user_data["history"][-10:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ask_deepseek(context.user_data["history"])
    context.user_data["history"].append({"role": "assistant", "content": reply})
    
    await update.message.reply_text(reply)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Update {update} caused error {context.error}")

# ========== ЗАПУСК (Фикс для Python 3.14+) ==========
async def start_bot():
    logging.basicConfig(level=logging.INFO)
    
    if not TELEGRAM_TOKEN or not DEEPSEEK_API_KEY:
        print("❌ ОШИБКА: Не заданы переменные окружения!")
        return

    server_thread = Thread(target=run_health_check_server, daemon=True)
    server_thread.start()
    print("🌐 Вспомогательный веб-сервер для хостинга успешно запущен.")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_memory))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("✅ Бот Доктор Стресс запущен и готов к работе!")
    
    await app.initialize()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await app.start()
    
    while True:
        await asyncio.sleep(3600)

def main():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    loop.run_until_complete(start_bot())

if __name__ == "__main__":
    main()
