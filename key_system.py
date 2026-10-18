"""Premium personal API-key management for Zinn AI.

Only hashes are persisted. The raw generated key is sent to the owner once and is
never retrievable later. API calls use the same AI pipeline, owner request limit,
and provider budgets as Telegram messages.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("zinn-ai.plugins.keys")
MAX_PERSONAL_KEYS = max(1, min(int(os.getenv("ZINN_MAX_PERSONAL_KEYS", "10") or "10"), 100))


def _core():
    import app
    return app


def _now() -> str:
    return datetime.now(ZoneInfo("Asia/Dhaka")).isoformat(timespec="seconds")


def _key_hash(raw: str) -> str:
    return hashlib.sha256(("zinn-ai-personal-api-v1:" + raw).encode("utf-8")).hexdigest()


def _new_key() -> str:
    return "zinn_live_" + secrets.token_urlsafe(32)


def _ensure_local_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS personal_api_keys (
        key_id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL, key_hash TEXT NOT NULL UNIQUE,
        prefix TEXT NOT NULL, label TEXT NOT NULL, created_at TEXT NOT NULL,
        revoked INTEGER NOT NULL DEFAULT 0, last_used_at TEXT NOT NULL DEFAULT '')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS personal_api_usage_daily (
        day TEXT NOT NULL, key_id TEXT NOT NULL, requests INTEGER NOT NULL DEFAULT 0,
        successes INTEGER NOT NULL DEFAULT 0, estimated_tokens INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(day,key_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS personal_api_usage_all (
        key_id TEXT PRIMARY KEY, requests INTEGER NOT NULL DEFAULT 0,
        successes INTEGER NOT NULL DEFAULT 0, estimated_tokens INTEGER NOT NULL DEFAULT 0)""")


def _db():
    c = _core()
    return c._db_connect()


def create_key(owner_id: int, label: str, *, enforce_limit: bool = True) -> tuple[dict[str, Any], str]:
    c = _core()
    label = re.sub(r"[\r\n\t]+", " ", label.strip())[:40] or "Personal app"
    current = list_keys(owner_id, include_revoked=False)
    if enforce_limit and len(current) >= MAX_PERSONAL_KEYS:
        raise ValueError(f"Active key limit reached ({MAX_PERSONAL_KEYS}). Revoke an unused key first.")
    raw = _new_key()
    digest = _key_hash(raw)
    key_id = "zk_" + secrets.token_hex(5)
    record = {
        "key_id": key_id, "owner_id": int(owner_id), "key_hash": digest,
        "prefix": raw[:18], "label": label, "created_at": _now(),
        "revoked": False, "last_used_at": "",
    }
    if c.FIREBASE_ENABLED:
        record_ref = c._fb_ref(f"api_keys/records/{key_id}")
        index_ref = c._fb_ref(f"api_keys/hash_index/{digest}")
        try:
            record_ref.set(record)
            # Hash is hex, valid as a Realtime Database key.
            index_ref.set(key_id)
        except Exception:
            # Avoid leaving a visible orphan key if writing the hash index fails.
            try:
                record_ref.delete()
                index_ref.delete()
            except Exception:
                pass
            raise
    else:
        conn = _db()
        try:
            _ensure_local_tables(conn)
            conn.execute(
                "INSERT INTO personal_api_keys(key_id,owner_id,key_hash,prefix,label,created_at,revoked,last_used_at) VALUES(?,?,?,?,?,?,0,'')",
                (key_id, int(owner_id), digest, record["prefix"], label, record["created_at"]),
            )
            conn.commit()
        finally:
            conn.close()
        log.warning("Personal API-key persistence is using local SQLite; configure Firebase for persistent keys on Render.")
    return record, raw


def find_key(raw: str) -> dict[str, Any] | None:
    if not isinstance(raw, str) or len(raw) < 30 or len(raw) > 200 or not raw.startswith("zinn_live_"):
        return None
    c = _core()
    digest = _key_hash(raw)
    if c.FIREBASE_ENABLED:
        index_ref = c._fb_ref(f"api_keys/hash_index/{digest}")
        key_id = index_ref.get() if index_ref else None
        if not key_id:
            return None
        row = c._fb_ref(f"api_keys/records/{key_id}").get()
        if not isinstance(row, dict) or row.get("key_hash") != digest or row.get("revoked"):
            return None
        return row
    conn = _db()
    try:
        _ensure_local_tables(conn)
        row = conn.execute(
            "SELECT key_id,owner_id,key_hash,prefix,label,created_at,revoked,last_used_at FROM personal_api_keys WHERE key_hash=?",
            (digest,),
        ).fetchone()
        if not row or row[6]:
            return None
        cols = ("key_id", "owner_id", "key_hash", "prefix", "label", "created_at", "revoked", "last_used_at")
        return dict(zip(cols, row))
    finally:
        conn.close()


def list_keys(owner_id: int | None = None, include_revoked: bool = True) -> list[dict[str, Any]]:
    c = _core()
    if c.FIREBASE_ENABLED:
        rows = c._fb_ref("api_keys/records").get() or {}
        items = [value for value in rows.values() if isinstance(value, dict)] if isinstance(rows, dict) else []
    else:
        conn = _db()
        try:
            _ensure_local_tables(conn)
            rows = conn.execute("SELECT key_id,owner_id,key_hash,prefix,label,created_at,revoked,last_used_at FROM personal_api_keys").fetchall()
            cols = ("key_id", "owner_id", "key_hash", "prefix", "label", "created_at", "revoked", "last_used_at")
            items = [dict(zip(cols, row)) for row in rows]
        finally:
            conn.close()
    result = []
    for item in items:
        if owner_id is not None and int(item.get("owner_id", -1)) != int(owner_id):
            continue
        if not include_revoked and bool(item.get("revoked")):
            continue
        # Always remove hashes before passing records to a caller or formatter.
        safe = {k: v for k, v in item.items() if k != "key_hash"}
        result.append(safe)
    result.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return result


def revoke_key(owner_id: int, key_id: str) -> bool:
    c = _core()
    if c.FIREBASE_ENABLED:
        ref = c._fb_ref(f"api_keys/records/{key_id}")
        record = ref.get() if ref else None
        if not isinstance(record, dict) or int(record.get("owner_id", -1)) != int(owner_id) or record.get("revoked"):
            return False
        ref.update({"revoked": True, "revoked_at": _now()})
        return True
    conn = _db()
    try:
        _ensure_local_tables(conn)
        cur = conn.execute(
            "UPDATE personal_api_keys SET revoked=1 WHERE key_id=? AND owner_id=? AND revoked=0",
            (key_id, int(owner_id)),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def rotate_key(owner_id: int, key_id: str) -> tuple[dict[str, Any], str] | None:
    existing = next((x for x in list_keys(owner_id, include_revoked=False) if x["key_id"] == key_id), None)
    if not existing:
        return None
    # Create replacement before revoking the original, so a limit failure leaves the old key usable.
    replacement, raw = create_key(owner_id, str(existing.get("label") or "Personal app") + " rotated", enforce_limit=False)
    if not revoke_key(owner_id, key_id):
        revoke_key(owner_id, replacement["key_id"])
        return None
    return replacement, raw


def record_request(key_id: str) -> None:
    c = _core()
    day = c.dhaka_day()
    if c.FIREBASE_ENABLED:
        for path in (f"usage/keys_api/{day}/{key_id}", f"usage/all/keys_api/{key_id}"):
            ref = c._fb_ref(path)
            def update(current):
                current = dict(current or {})
                current["requests"] = int(current.get("requests", 0) or 0) + 1
                current.setdefault("successes", 0)
                current.setdefault("estimated_tokens", 0)
                return current
            ref.transaction(update)
        return
    conn = _db()
    try:
        _ensure_local_tables(conn)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO personal_api_usage_daily(day,key_id,requests) VALUES(?,?,1) ON CONFLICT(day,key_id) DO UPDATE SET requests=requests+1", (day, key_id))
        conn.execute("INSERT INTO personal_api_usage_all(key_id,requests) VALUES(?,1) ON CONFLICT(key_id) DO UPDATE SET requests=requests+1", (key_id,))
        conn.commit()
    finally:
        conn.close()


def record_success(key_id: str, estimated_tokens: int) -> None:
    c = _core()
    day = c.dhaka_day()
    amount = max(0, int(estimated_tokens))
    if c.FIREBASE_ENABLED:
        for path in (f"usage/keys_api/{day}/{key_id}", f"usage/all/keys_api/{key_id}"):
            ref = c._fb_ref(path)
            def update(current):
                current = dict(current or {})
                current["successes"] = int(current.get("successes", 0) or 0) + 1
                current["estimated_tokens"] = int(current.get("estimated_tokens", 0) or 0) + amount
                current.setdefault("requests", 0)
                return current
            ref.transaction(update)
        return
    conn = _db()
    try:
        _ensure_local_tables(conn)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO personal_api_usage_daily(day,key_id,successes,estimated_tokens) VALUES(?,?,1,?) ON CONFLICT(day,key_id) DO UPDATE SET successes=successes+1,estimated_tokens=estimated_tokens+excluded.estimated_tokens", (day, key_id, amount))
        conn.execute("INSERT INTO personal_api_usage_all(key_id,successes,estimated_tokens) VALUES(?,1,?) ON CONFLICT(key_id) DO UPDATE SET successes=successes+1,estimated_tokens=estimated_tokens+excluded.estimated_tokens", (key_id, amount))
        conn.commit()
    finally:
        conn.close()


def touch_key(key_id: str) -> None:
    c = _core()
    stamp = _now()
    if c.FIREBASE_ENABLED:
        c._fb_ref(f"api_keys/records/{key_id}").update({"last_used_at": stamp})
        return
    conn = _db()
    try:
        _ensure_local_tables(conn)
        conn.execute("UPDATE personal_api_keys SET last_used_at=? WHERE key_id=?", (stamp, key_id))
        conn.commit()
    finally:
        conn.close()


def get_key_usage(key_id: str) -> dict[str, int]:
    c = _core()
    day = c.dhaka_day()
    if c.FIREBASE_ENABLED:
        daily = c._fb_ref(f"usage/keys_api/{day}/{key_id}").get() or {}
        total = c._fb_ref(f"usage/all/keys_api/{key_id}").get() or {}
        return {
            "daily_requests": int(daily.get("requests", 0) or 0),
            "daily_successes": int(daily.get("successes", 0) or 0),
            "daily_estimated_tokens": int(daily.get("estimated_tokens", 0) or 0),
            "all_requests": int(total.get("requests", 0) or 0),
            "all_successes": int(total.get("successes", 0) or 0),
            "all_estimated_tokens": int(total.get("estimated_tokens", 0) or 0),
        }
    conn = _db()
    try:
        _ensure_local_tables(conn)
        d = conn.execute("SELECT requests,successes,estimated_tokens FROM personal_api_usage_daily WHERE day=? AND key_id=?", (day, key_id)).fetchone() or (0, 0, 0)
        a = conn.execute("SELECT requests,successes,estimated_tokens FROM personal_api_usage_all WHERE key_id=?", (key_id,)).fetchone() or (0, 0, 0)
        return {"daily_requests": int(d[0]), "daily_successes": int(d[1]), "daily_estimated_tokens": int(d[2]), "all_requests": int(a[0]), "all_successes": int(a[1]), "all_estimated_tokens": int(a[2])}
    finally:
        conn.close()


def format_key_usage_report() -> str:
    rows = list_keys(include_revoked=True)
    c = _core()
    lines = ["", "④ 🔐 PERSONAL API KEY CENTER", f"   • Configured keys: {len(rows)} total · {sum(not bool(r.get('revoked')) for r in rows)} active"]
    if not rows:
        lines.append("   • No personal API keys created yet. Use /key create <name> in private chat.")
    else:
        for idx, row in enumerate(rows, start=1):
            stat = get_key_usage(str(row["key_id"]))
            state = "⛔ revoked" if row.get("revoked") else "✅ active"
            lines.extend([
                f"   {idx}. {row.get('label', 'Personal app')} · {row['key_id']} · {state}",
                f"      • Today: {stat['daily_requests']:,} requests / {stat['daily_successes']:,} successful · approx {stat['daily_estimated_tokens']:,} tokens",
                f"      • All-time: {stat['all_requests']:,} requests / {stat['all_successes']:,} successful · approx {stat['all_estimated_tokens']:,} tokens",
            ])
    lines.extend([
        "   • API and Telegram calls share provider request/token safety budgets.",
        "   • API usage totals above are per-key; provider usage above is the combined AI-engine usage.",
        "   • Raw API secrets are never shown in usage reports.",
    ])
    return "\n".join(lines)


def _present_key_once(raw: str, record: dict[str, Any]) -> str:
    return (
        "╭━━━ 🔐 ZINN AI · PERSONAL API ━━━╮\n"
        f"✅ Key created: {record['label']}\n"
        f"🆔 Key ID: {record['key_id']}\n\n"
        "🔑 Your API key (shown only once):\n"
        f"{raw}\n\n"
        "⚠️ Eta private rakho. GitHub/public chat/screenshot-e dio na. Bot shudhu key hash save kore—pore full key abar dekhano jabe na.\n\n"
        "🌐 Endpoint: POST /v1/chat\n"
        "🔒 Auth header: Authorization: Bearer YOUR_KEY\n"
        "📊 Usage: GET /v1/usage\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
    )


async def handle_command(message: dict[str, Any], text: str, **_: Any) -> bool:
    parts = text.strip().split(maxsplit=2)
    command = parts[0].split("@", 1)[0].lower() if parts else ""
    if command not in {"/key", "/keys", "/revoke", "/uses"}:
        return False
    c = _core()
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    user_id = sender.get("id") if isinstance(sender.get("id"), int) else None
    chat_id = chat.get("id")
    if chat.get("type") != "private" or chat_id != user_id:
        # Never create/show keys or aggregate usage inside a group.
        if isinstance(user_id, int) and user_id in c.ADMIN_USER_IDS:
            try:
                await c.send_text(user_id, "🔐 Key management group-e use kora jabe na. Amar sathe private chat-e /key dao.")
            except Exception:
                pass
        await c.send_text(int(chat_id), "🔐 API key commands security-r jonno private chat-e use koro.")
        return True
    if not isinstance(user_id, int) or user_id not in c.ADMIN_USER_IDS:
        await c.send_text(chat_id, "⛔ Personal API key management admin-only.")
        return True

    if command == "/uses":
        try:
            await c.send_text(chat_id, c.format_usage_report())
        except Exception as exc:
            log.warning("Combined usage report unavailable (%s)", type(exc).__name__)
            await c.send_text(chat_id, "Usage report ekhon pawa jacche na. Database connection check kore abar try koro.")
        return True
    if command == "/keys":
        try:
            records = list_keys(user_id, include_revoked=True)
        except Exception as exc:
            log.warning("API key listing failed (%s)", type(exc).__name__)
            await c.send_text(chat_id, "Key storage ekhon saraa dicche na. Firebase/SQLite connection check kore abar try koro.")
            return True
        if not records:
            reply = "🔐 Ekhono kono personal API key nei. /key create <name> diye prothom key banao."
        else:
            rows = ["╭━━ 🔑 YOUR PERSONAL API KEYS ━━╮"]
            for row in records:
                state = "⛔ revoked" if row.get("revoked") else "✅ active"
                rows.append(f"• {row.get('label')} · {row['key_id']} · {state}")
                rows.append(f"  Prefix: {row.get('prefix', '')}… · Created: {row.get('created_at', '')}")
                rows.append(f"  Last used: {row.get('last_used_at') or 'Not used yet'}")
            rows.extend(["", f"Active limit: {sum(not bool(r.get('revoked')) for r in records)}/{MAX_PERSONAL_KEYS}", "Full keys never appear here; use /key rotate <key_id> to replace a key.", "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"])
            reply = "\n".join(rows)
        await c.send_text(chat_id, reply)
        return True

    action = parts[1].lower() if len(parts) > 1 else "help"
    target = parts[2].strip() if len(parts) > 2 else ""
    if action == "create":
        try:
            record, raw = create_key(user_id, target or "Personal app")
            await c.send_text(chat_id, _present_key_once(raw, record))
        except ValueError as exc:
            await c.send_text(chat_id, str(exc))
        except Exception as exc:
            log.warning("API key creation failed (%s)", type(exc).__name__)
            await c.send_text(chat_id, "API key create kora jayni. Firebase/SQLite connection check kore abar try koro.")
        return True
    if action == "revoke" or command == "/revoke":
        target_id = target if action == "revoke" else (parts[1] if len(parts) > 1 else "")
        if not re.fullmatch(r"zk_[a-f0-9]{10}", target_id):
            await c.send_text(chat_id, "Format: /key revoke zk_xxxxxxxxxx")
            return True
        if revoke_key(user_id, target_id):
            await c.send_text(chat_id, f"✅ Key `{target_id}` revoked. Ekhon theke ei key diye API use kora jabe na.")
        else:
            await c.send_text(chat_id, "Ei active key tomar account-e khuje pelam na.")
        return True
    if action == "rotate":
        if not re.fullmatch(r"zk_[a-f0-9]{10}", target):
            await c.send_text(chat_id, "Format: /key rotate zk_xxxxxxxxxx")
            return True
        try:
            rotated = rotate_key(user_id, target)
            if not rotated:
                await c.send_text(chat_id, "Key rotate kora jayni. Check koro key active kina.")
            else:
                record, raw = rotated
                await c.send_text(chat_id, "🔁 Old key revoke kore replacement create kora hoyeche.\n\n" + _present_key_once(raw, record))
        except Exception as exc:
            log.warning("API key rotation failed (%s)", type(exc).__name__)
            await c.send_text(chat_id, "Key rotate kora jayni. Storage connection check kore abar try koro.")
        return True
    await c.send_text(
        chat_id,
        "╭━━━ 🔐 ZINN AI · KEY CONTROL ━━━╮\n"
        "/key create <name> — create a private API key\n"
        "/keys — list status/prefix, never full secrets\n"
        "/key revoke <key_id> — revoke immediately\n"
        "/key rotate <key_id> — replace and revoke old key\n"
        "/uses — combined AI usage + per-key usage\n\n"
        "Only the full generated key is shown once. Keep it private.\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯",
    )
    return True


def _extract_key(request: Request) -> str:
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-zinn-key", "").strip()


async def api_chat(request: Request):
    c = _core()
    raw = _extract_key(request)
    try:
        record = find_key(raw)
    except Exception as exc:
        log.warning("API key verification storage failure (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="API key storage unavailable; request was stopped safely")
    if not record:
        raise HTTPException(status_code=401, detail="Invalid or revoked Zinn API key")
    if int(record.get("owner_id", -1)) not in c.ADMIN_USER_IDS:
        raise HTTPException(status_code=403, detail="This API key owner is no longer authorized")
    try:
        raw_body = await request.body()
        if len(raw_body) > 32_000:
            raise HTTPException(status_code=413, detail="Request body is too large")
        payload = json.loads(raw_body)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=422, detail="'message' must be a non-empty string")
    message = message.strip()
    if len(message) > c.MAX_INPUT_CHARS:
        raise HTTPException(status_code=413, detail=f"Message exceeds {c.MAX_INPUT_CHARS} characters")
    owner_id = int(record["owner_id"])
    if c.is_rate_limited(owner_id):
        raise HTTPException(status_code=429, detail="Rate limit reached; wait a minute and retry")
    try:
        allowed = await __import__("asyncio").to_thread(c.reserve_user_request, owner_id)
    except Exception as exc:
        log.warning("API user quota check failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Usage database unavailable; request was stopped safely")
    if not allowed:
        raise HTTPException(status_code=429, detail="Daily user limit reached; reset is at Bangladesh midnight")

    key_id = str(record["key_id"])
    try:
        record_request(key_id)
        await __import__("asyncio").to_thread(touch_key, key_id)
    except Exception as exc:
        log.warning("API key usage storage failure (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="API usage storage unavailable; request was stopped safely")
    session_raw = str(payload.get("session_id") or "default")[:64]
    session = re.sub(r"[^a-zA-Z0-9_-]", "_", session_raw) or "default"
    session_digest = hashlib.sha256(f"{key_id}:{session}".encode()).hexdigest()[:15]
    context_id = int(session_digest, 16)
    c.touch_chat(context_id, context_id)
    try:
        loaded = await c.ensure_chat_loaded(context_id)
        if not loaded:
            raise HTTPException(status_code=503, detail="Conversation storage unavailable; retry later")
        async with c.chat_locks[context_id]:
            async with c.processing_semaphore:
                answer = await c.get_ai_reply(context_id, message)
                c.chat_history[context_id].append({"role": "user", "content": message[-c.MAX_INPUT_CHARS:]})
                c.chat_history[context_id].append({"role": "assistant", "content": answer})
                await c.persist_chat_history(context_id)
        try:
            amount = c.estimate_tokens(message) + c.estimate_tokens(answer)
            await __import__("asyncio").to_thread(record_success, key_id, amount)
        except Exception as exc:
            log.warning("API key usage success metrics failed (%s)", type(exc).__name__)
        return JSONResponse({
            "id": "resp_" + secrets.token_hex(8),
            "object": "zinn.response",
            "created": int(time.time()),
            "model": "zinn-ai-auto",
            "output": {"text": answer},
            "usage": {"estimated_tokens": c.estimate_tokens(message) + c.estimate_tokens(answer), "note": "Estimate only; provider metadata is tracked separately when available."},
        })
    except c.UsageLimitReached:
        raise HTTPException(status_code=429, detail="Shared Gemini/Groq safety budget exhausted for today")
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("Personal API request failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="AI provider temporarily unavailable; retry later")


async def api_usage(request: Request):
    try:
        record = find_key(_extract_key(request))
    except Exception as exc:
        log.warning("API usage lookup storage failure (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="API key storage unavailable")
    if not record or int(record.get("owner_id", -1)) not in _core().ADMIN_USER_IDS:
        raise HTTPException(status_code=401, detail="Invalid or revoked Zinn API key")
    return JSONResponse({
        "key_id": record["key_id"], "label": record.get("label"),
        "usage": get_key_usage(str(record["key_id"])),
        "quota_policy": "Shared with Telegram owner daily limit and provider safety budgets.",
    })


def register(manager: Any) -> None:
    manager.on("command", handle_command)
    manager.app.add_api_route("/v1/chat", api_chat, methods=["POST"], name="personal_api_chat")
    manager.app.add_api_route("/v1/usage", api_usage, methods=["GET"], name="personal_api_usage")
