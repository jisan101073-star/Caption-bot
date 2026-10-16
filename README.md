# Zinn AI — Telegram Mini AI Assistant

A Telegram bot with Gemini as the primary AI provider and Groq as an automatic backup. It supports general chat, captions, translation, and coding help. It uses Telegram webhooks for Render Web Service deployment.

## Files

- `app.py` — bot and webhook server
- `requirements.txt` — Python dependencies

## Before deploying

1. Make sure your Telegram bot exists in BotFather and copy its bot token privately.
2. Get a Gemini API key and/or a Groq API key. Keep both private.
3. Never place API keys or bot tokens in GitHub files, screenshots, public chats, or this README.

## Deploy on Render from GitHub

1. Put `app.py` and `requirements.txt` in the **root** of your GitHub repository.
2. In Render, choose **New → Web Service** and connect the `zinn-ai-bot` repository.
3. Choose the **Free** instance for testing.
4. Set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Add Environment Variables in Render (use the exact names below):
   - `TG_BOT_TOKEN` = your BotFather token
   - `GEMINI_API_KEY` = your Gemini key
   - `GROQ_API_KEY` = your Groq key (optional but recommended as backup)
   - `GEMINI_MODEL` = `gemini-3.8-flash` (optional; this is the default in the code)
   - `GROQ_MODEL` = `openai/gpt-oss-20b` (optional; this is the default in the code)
6. Press **Create Web Service** / **Deploy** and watch the Logs. The app registers the Telegram webhook automatically when Render provides its public HTTPS URL.
7. Open your Telegram bot and send `/start`.

## Features and commands

- `/start` — welcome screen and menu
- `/help` — how to use the bot
- `/clear` — clear the in-memory AI conversation context for your chat
- `/mode` — return to general chat
- Buttons: Caption, Translate, Code Help, Chat

## Notes

- The bot is public: anyone who finds it can send messages. API usage and free-tier quotas still apply. The code includes a basic limit of 8 AI requests per chat per minute and a 3,500-character input cap.
- The chat context is stored only in the running process's memory; it resets when Render restarts or spins down. The code does not intentionally write conversation history to a database or filesystem.
- Render Free web services can spin down after 15 minutes without inbound HTTP traffic. After inactivity, the first Telegram update may take longer to process while the service wakes up.
- Gemini/Groq model IDs and provider quotas can change. If a model stops working, update its environment variable to a model currently enabled for your API account.
- If only one provider key is set, the bot will use that provider. If both are set, it tries Gemini first and Groq if Gemini fails.
