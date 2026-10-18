# Zinn AI Premium — Plugin Edition

Zinn AI uses the same shared AI engine for Telegram chat and personal API requests: Gemini first, then Groq fallback. The deployment remains a FastAPI webhook for Render.

## Package layout

```text
app.py
plugin_loader.py
requirements.txt
README.md
plugins/
  __init__.py
  key_system.py
  reaction_system.py
```

`app.py` owns the Telegram webhook, model routing, shared provider/user budgets, chat history, and the usage engine. `plugin_loader.py` automatically discovers each non-underscored `plugins/*.py` file on startup. A plugin must implement `register(manager)` and can attach routes or handlers. Add a new trusted plugin file and redeploy; no fixed plugin-count limit is coded and `app.py` does not need editing for ordinary additions. Runtime memory/CPU and external quotas are still finite. Plugins are executable Python code—only deploy code you trust.

## Deploy on Render

Put **all** package files/folders in the root of your GitHub repository (not only `app.py`). Set:

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`

Required environment variables:

- `TG_BOT_TOKEN` — BotFather bot token
- At least one provider key: `GEMINI_API_KEY_1`…`GEMINI_API_KEY_5` and/or `GROQ_API_KEY_1`…`GROQ_API_KEY_5` (legacy `GEMINI_API_KEY` / `GROQ_API_KEY` are still supported)
- `ZINN_ADMIN_IDS` — comma-separated Telegram user IDs allowed to create/revoke personal API keys and view usage; include your own numeric Telegram ID

Recommended for persistent history, counters, and API-key records across Render restarts:

- `FIREBASE_DATABASE_URL`
- `FIREBASE_CREDENTIALS_JSON` (service account JSON string) or `FIREBASE_SERVICE_ACCOUNT_JSON`
- `ZINN_FIREBASE_ROOT=/zinn_ai` (optional; defaults to `/zinn_ai`)

Other optional settings: `GEMINI_MODEL`, `GROQ_MODEL`, `GROQ_VISION_MODEL`, `ZINN_MAX_PERSONAL_KEYS` (default 10, max 100), `USER_DAILY_REQUEST_LIMIT` (default 100), `USER_REQUESTS_PER_MINUTE` (default 8), `GEMINI_DAILY_REQUEST_LIMIT`, `GROQ_DAILY_REQUEST_LIMIT`, `GEMINI_DAILY_TOKEN_BUDGET`, and `GROQ_DAILY_TOKEN_BUDGET`.

Do not commit tokens, provider keys, Firebase credentials, or generated Zinn API keys to GitHub. Configure secrets in Render Environment settings.

## Private-chat reactions

The `reaction_system.py` plugin adds occasional context-matched emoji reactions to a user's **private** messages only. It deliberately never reacts to messages in groups or channels. The classifier is lightweight and local (Bangla/Banglish/English sentiment, questions, success, humour, affection, and longer substantive messages) so it does not spend an extra paid Gemini/Groq request just to choose an emoji. Very short acknowledgements and commands are ignored. Actual reaction support depends on Telegram Bot API/chat permissions; failures are safely ignored and do not stop replies.

## Personal API keys

Only configured admins can manage keys, and management commands work only in the bot's private chat:

- `/key` — help
- `/key create <name>` — create a new personal API key (full key shown once)
- `/keys` — list labels, IDs, prefix, status, last-used timestamp; never reveals full secrets
- `/key revoke <key_id>` — revoke immediately
- `/key rotate <key_id>` — create a replacement and revoke the old key
- `/uses` — full shared usage report plus per-key usage
- `/usage` — existing bot-wide report, now extended with personal API statistics

Keys use a `zinn_live_...` format. Only a SHA-256 digest and non-secret metadata are stored. If the one-time secret is lost, rotate the key. Revoked keys stop working on the next request. Active keys are limited per owner (default 10).

### API endpoints

`POST /v1/chat`

Headers:

```http
Authorization: Bearer zinn_live_YOUR_PRIVATE_KEY
Content-Type: application/json
```

Body:

```json
{
  "message": "Explain photosynthesis in simple Bangla",
  "session_id": "my-app-user-01"
}
```

`session_id` is optional; it separates chat history per client/session. The response is JSON with the answer in `output.text`. The API does not let clients override Zinn's system prompt or provider credentials.

`GET /v1/usage` uses the same Bearer header and returns only that key's request/success/estimated-token statistics.

### Quota sharing (important)

Telegram chats and `/v1/chat` use the same `get_ai_reply()` model-routing pipeline. They share the same configured Gemini/Groq provider request/token safety budgets and the key owner's daily request allowance; API calls do not get a separate quota pool. When the owner's daily request limit or both providers' safety limits are exhausted, the corresponding Telegram/API requests stop until the next Bangladesh-local day, subject to real provider availability/quota. API usage counters are per key; `/uses` shows them alongside the combined provider counters. The per-key token figure is an estimate; provider-reported token metadata is tracked separately in the global report.

For cross-restart persistence, configure Firebase. Without Firebase, local SQLite is used as a fallback and Render's ephemeral filesystem may not preserve records across replacement/redeploys.

## Safety and limitations

- API keys are high-entropy, owner-managed credentials. Do not share them. Revoke compromised keys immediately.
- The API is intended for the configured admin/owner(s); key creation checks `ZINN_ADMIN_IDS` and requests are rejected when a key owner is no longer authorized.
- Shared provider limits are bot-side safety budgets, not guarantees of Google's/Groq's external quotas.
- `GET /health` reports basic status and how many plugins loaded. It does not disclose secret values.
- Model IDs and third-party API quotas can change; confirm the model available to your account if a provider starts rejecting requests.
