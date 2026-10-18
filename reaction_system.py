"""Private-chat contextual reactions. This plugin never reacts in groups/channels.

The classifier is deliberately local and lightweight: no second paid model call is
made per message, so reactions do not consume additional Gemini/Groq tokens.
"""
from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("zinn-ai.plugins.reactions")

_SKIP = {
    "hi", "hello", "hey", "ok", "okay", "hmm", "hmmm", "accha", "assa", "thik",
    "thik ache", "valo", "bhalo", "hya", "ha", "yes", "no", "na", "thanks", "thank you",
    "ধন্যবাদ", "হ্যাঁ", "না", "আচ্ছা", "ঠিক আছে", "হুম", "হুমম", "ওকে", "হাই",
}
_SAD = re.compile(r"মন খারাপ|খারাপ লাগ|ভালো লাগছে না|কষ্ট|কাঁদ|একলা লাগ|ভেঙে পড়|sad|unhappy|depressed|heartbroken|miss you|miss kori|miss kortesi|kharap lagt|mon kharap|koshto|eka lage", re.I)
_HAPPY = re.compile(r"সফল|হয়ে গেছে|হয়েছে|পাস করেছি|জিতেছি|অনেক খুশি|খুশি লাগ|অভিনন্দন|congrat|success|passed|i did it|hoise|hoye gese|hoyeche|khushi|yay|finally done|got selected", re.I)
_FUNNY = re.compile(r"হাসি|মজার|ফানি|জোক|হাহা|lol|lmao|rofl|haha|😂|🤣|funny|joke|meme", re.I)
_LOVE = re.compile(r"ভালোবাসি|ভালোবাসা|প্রেম|প্রিয় মানুষ|প্রিয় মানুষ|miss you|love you|i love|crush|romantic|valobashi|bhalobashi|prem|jaan|jan re", re.I)
_QUESTION = re.compile(r"\?|কেন|কিভাবে|কীভাবে|কেনো|what|why|how|which|who|kivabe|keno|ki kore", re.I)
_ACK = re.compile(r"^(?:h+a+i+|h+e+y+|h+m+|o+k+|o+k+a+y+|accha|assa|thik|valo|bhalo|hya|ha|na|yes|no|hmm+|হুম+|আচ্ছা|ঠিক আছে|হ্যাঁ|না|ওকে)[.!?\s🙂😊👋❤️👍🙏]*$", re.I)


def choose_reaction(text: str) -> str | None:
    value = (text or "").strip()
    if not value or value.startswith("/"):
        return None
    folded = value.casefold().strip()
    if folded in _SKIP or _ACK.fullmatch(value) or len(value) < 9:
        return None
    # Most personal tone gets priority before generic interesting-message rules.
    if _SAD.search(value):
        return "🫂" if len(value) < 100 else "🥺"
    if _HAPPY.search(value):
        return "🎉"
    if _FUNNY.search(value):
        return "😂"
    if _LOVE.search(value):
        return "❤️"
    if _QUESTION.search(value) and len(value) >= 18:
        return "🤔"
    # A long, specific thought/story may merit a reaction; ordinary short chat won't.
    if len(value) >= 90:
        return "💡" if "?" not in value else "👀"
    return None


async def handle_private_message(message: dict[str, Any], text: str, **_: Any) -> None:
    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        return
    message_id = message.get("message_id")
    chat_id = chat.get("id")
    if not isinstance(message_id, int) or not isinstance(chat_id, int):
        return
    emoji = choose_reaction(text)
    if not emoji:
        return
    # Fail softly: unsupported reaction permissions must never stop the AI reply.
    import app as core
    try:
        await core.telegram_call(
            "setMessageReaction",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": [{"type": "emoji", "emoji": emoji}],
                "is_big": False,
            },
            timeout=4.0,
        )
    except Exception as exc:
        log.debug("Private message reaction skipped (%s)", type(exc).__name__)


def register(manager: Any) -> None:
    manager.on("private_message", handle_private_message)
