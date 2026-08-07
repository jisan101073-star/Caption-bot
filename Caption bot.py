#!/usr/bin/env python3
"""
=====================================================================
 Telegram Caption Bot
=====================================================================
A production-ready Telegram bot that generates creative social-media
captions (with hashtags) for a topic/mood the user provides.

Library : python-telegram-bot (v20+, async API)
Install : pip install python-telegram-bot==21.*
---------------------------------------------------------------------
"""

import logging
import os
import random
import re
from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =====================================================================
# CONFIGURATION
# =====================================================================

# Web বা App-এর Environment Variable থেকে টোকেন রিড করবে
BOT_TOKEN: Optional[str] = os.getenv("BOT_TOKEN")

# Optional: AI API key
CAPTION_AI_API_KEY: Optional[str] = os.getenv("CAPTION_AI_API_KEY")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("caption_bot")


# =====================================================================
# CAPTION DATA: categories, templates, and hashtags
# =====================================================================
CATEGORIES = {
    "attitude": {
        "label": "😎 Attitude",
        "keywords": ["attitude", "swag", "boss", "confidence", "savage"],
        "templates": [
            "I don't chase, I attract. {topic} energy only. 😎",
            "My {topic} game is undefeated.",
            "Not everyone will get {topic}, and that's exactly the point.",
            "Silent, savage, and never sorry about {topic}.",
        ],
        "hashtags": [
            "#Attitude", "#Savage", "#Boss", "#Confidence", "#SwagStatus",
            "#NoFilter", "#StayReal",
        ],
    },
    "love": {
        "label": "❤️ Love",
        "keywords": ["love", "romance", "crush", "couple", "valentine"],
        "templates": [
            "Every love story is beautiful, but ours about {topic} is my favorite.",
            "You + me + {topic} = forever.",
            "Falling for {topic} was the easiest thing I've ever done. ❤️",
            "{topic} looks better with you in the picture.",
        ],
        "hashtags": [
            "#Love", "#Couple", "#InLove", "#Romance", "#SoulMate",
            "#TogetherForever", "#LoveStory",
        ],
    },
    "sad": {
        "label": "😢 Sad",
        "keywords": ["sad", "broken", "alone", "pain", "heartbreak"],
        "templates": [
            "Some days {topic} just hurts more than others.",
            "Smiling on the outside, thinking about {topic} on the inside.",
            "Not every wound about {topic} shows on the skin.",
            "It's okay to not be okay about {topic} sometimes.",
        ],
        "hashtags": [
            "#Sad", "#Alone", "#BrokenHeart", "#Pain", "#DeepThoughts",
            "#Healing",
        ],
    },
    "motivation": {
        "label": "🔥 Motivation",
        "keywords": ["motivation", "grind", "success", "hustle", "goals"],
        "templates": [
            "{topic} isn't given, it's earned. Keep grinding. 🔥",
            "Every expert in {topic} was once a beginner. Don't stop.",
            "Turn your {topic} into your biggest flex.",
            "Discipline today, {topic} tomorrow.",
        ],
        "hashtags": [
            "#Motivation", "#Grind", "#Success", "#Hustle", "#GoalDigger",
            "#NeverGiveUp", "#MindsetMatters",
        ],
    },
    "gaming": {
        "label": "🎮 Gaming",
        "keywords": ["gaming", "game", "esports", "gamer", "streamer"],
        "templates": [
            "Eat. Sleep. {topic}. Repeat. 🎮",
            "Warning: {topic} in progress, respawn not guaranteed.",
            "My reflexes say pro, my rank says {topic}. 😅",
            "Level up your {topic}, then talk to me.",
        ],
        "hashtags": [
            "#Gaming", "#Gamer", "#GameOn", "#Esports", "#PlayerOne",
            "#GG",
        ],
    },
    "travel": {
        "label": "✈️ Travel",
        "keywords": ["travel", "trip", "vacation", "wanderlust", "explore"],
        "templates": [
            "Collecting memories, not things — starting with {topic}.",
            "{topic} looks even better in person. ✈️",
            "Some people travel to find themselves, I travel for {topic}.",
            "Passport stamped, heart full of {topic}.",
        ],
        "hashtags": [
            "#Travel", "#Wanderlust", "#Explore", "#TravelGram",
            "#AdventureAwaits",
        ],
    },
    "funny": {
        "label": "😂 Funny",
        "keywords": ["funny", "joke", "meme", "humor", "comedy"],
        "templates": [
            "My relationship with {topic} is complicated, mostly funny.",
            "{topic}: because adulting is hard and laughing is free. 😂",
            "I put the 'pro' in procrastinating about {topic}.",
            "Life update: still bad at {topic}, still hilarious about it.",
        ],
        "hashtags": [
            "#Funny", "#Comedy", "#Meme", "#Humor", "#LOL",
        ],
    },
    "general": {
        "label": "✨ General",
        "keywords": [],
        "templates": [
            "Living my best life, one {topic} moment at a time. ✨",
            "{topic} hits different today.",
            "Just here for the {topic} vibes.",
            "Making {topic} look effortless.",
        ],
        "hashtags": [
            "#Vibes", "#Mood", "#InstaGood", "#Blessed", "#DailyLife",
        ],
    },
}

GENERAL_HASHTAGS = ["#CaptionBot", "#InstaCaption", "#SocialMedia"]


# =====================================================================
# CAPTION GENERATION LOGIC
# =====================================================================

def detect_category(topic: str) -> str:
    topic_lower = topic.lower()
    for key, data in CATEGORIES.items():
        for keyword in data["keywords"]:
            if keyword in topic_lower:
                return key
    return "general"


def generate_caption(topic: str) -> dict:
    topic = topic.strip()
    category = detect_category(topic)
    data = CATEGORIES[category]

    template = random.choice(data["templates"])
    caption = template.format(topic=topic)

    hashtags = random.sample(data["hashtags"], k=min(4, len(data["hashtags"])))
    hashtags += random.sample(GENERAL_HASHTAGS, k=min(2, len(GENERAL_HASHTAGS)))

    return {
        "caption": caption,
        "hashtags": hashtags,
        "category": category,
        "topic": topic,
    }


def escape_md_v2(text: str) -> str:
    special_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", text)


def format_caption_message(result: dict) -> str:
    caption_escaped = escape_md_v2(result["caption"])
    hashtags_escaped = escape_md_v2(" ".join(result["hashtags"]))
    category_label = escape_md_v2(CATEGORIES[result["category"]]["label"])

    return (
        f"*{category_label} Caption*\n\n"
        f"{caption_escaped}\n\n"
        f"{hashtags_escaped}\n\n"
        f"_Tap the caption block below to copy it easily:_\n"
        f"`{escape_md_v2(result['caption'] + ' ' + ' '.join(result['hashtags']))}`"
    )


def build_caption_keyboard(topic: str) -> InlineKeyboardMarkup:
    safe_topic = topic[:50]
    buttons = [
        [
            InlineKeyboardButton("🔁 Generate Another", callback_data=f"regen|{safe_topic}"),
            InlineKeyboardButton("📤 Share", callback_data=f"share|{safe_topic}"),
        ],
        [
            InlineKeyboardButton("📂 Browse Categories", callback_data="show_categories"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


# =====================================================================
# COMMAND HANDLERS
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_first_name = update.effective_user.first_name if update.effective_user else "there"
    welcome_text = (
        f"👋 Hey {user_first_name}, welcome to *Caption Bot*\\!\n\n"
        "I turn any topic, mood, or keyword into a ready\\-to\\-post "
        "social media caption \\(with hashtags included\\) ✨\n\n"
        "*Quick start:*\n"
        "`/caption sunset at the beach`\n"
        "`/caption Monday motivation`\n\n"
        "*Other commands:*\n"
        "📂 /categories \\- see available caption styles\n"
        "❓ /help \\- full usage guide\n\n"
        "Try it now — send me a topic with /caption 👇"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "*📖 How to use Caption Bot*\n\n"
        "*/caption* `<topic or mood>`\n"
        "Generates a caption \\+ hashtags for whatever you type\\.\n"
        "Example: `/caption gym day`\n\n"
        "*/categories*\n"
        "Shows all available caption styles \\(Attitude, Love, Sad, "
        "Motivation, Gaming, Travel, Funny, General\\)\\.\n\n"
        "*/start*\n"
        "Shows the welcome message again\\.\n\n"
        "*Buttons under each caption:*\n"
        "🔁 Generate Another \\- get a fresh caption for the same topic\n"
        "📤 Share \\- get a forward\\-ready copy of the caption\n"
        "📂 Browse Categories \\- jump to the category list\n\n"
        "Tip: mention a mood word \\(e\\.g\\. _love_, _sad_, _gaming_\\) "
        "in your topic and I'll auto\\-match the right style\\!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)


async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["*📂 Available Caption Categories*\n"]
    buttons = []
    row = []
    for key, data in CATEGORIES.items():
        if key == "general":
            continue
        lines.append(f"{escape_md_v2(data['label'])}")
        row.append(InlineKeyboardButton(data["label"], callback_data=f"sample|{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    lines.append(
        "\nTap a category below for a sample caption, or use "
        "`/caption <your topic>` to generate your own\\."
    )
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def caption_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "⚠️ Please tell me a topic or mood to caption.\n\n"
            "Example: `/caption weekend getaway`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    topic = " ".join(context.args).strip()

    if len(topic) > 100:
        await update.message.reply_text(
            "⚠️ That topic is a bit too long — please keep it under 100 characters."
        )
        return

    try:
        result = generate_caption(topic)
        message = format_caption_message(result)
        keyboard = build_caption_keyboard(topic)
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Failed to generate caption for topic=%r", topic)
        await update.message.reply_text(
            "😕 Something went wrong while generating your caption. Please try again."
        )


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤔 I didn't quite get that. Try `/caption <your topic>` or /help for a full guide.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# =====================================================================
# BUTTON (CALLBACK QUERY) HANDLER
# =====================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        data = query.data or ""
        action, _, payload = data.partition("|")

        if action == "regen":
            topic = payload or "your day"
            result = generate_caption(topic)
            message = format_caption_message(result)
            keyboard = build_caption_keyboard(topic)
            await query.edit_message_text(
                message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard
            )

        elif action == "share":
            topic = payload or "your day"
            result = generate_caption(topic)
            share_text = f"{result['caption']} {' '.join(result['hashtags'])}"
            await query.message.reply_text(
                "📤 *Here's your caption, ready to forward or copy:*\n\n"
                f"`{escape_md_v2(share_text)}`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

        elif action == "sample":
            category_key = payload if payload in CATEGORIES else "general"
            sample_topic = "today"
            template = random.choice(CATEGORIES[category_key]["templates"])
            sample_caption = template.format(topic=sample_topic)
            hashtags = random.sample(
                CATEGORIES[category_key]["hashtags"],
                k=min(3, len(CATEGORIES[category_key]["hashtags"])),
            )
            text = (
                f"*{escape_md_v2(CATEGORIES[category_key]['label'])} sample:*\n\n"
                f"{escape_md_v2(sample_caption)}\n\n"
                f"{escape_md_v2(' '.join(hashtags))}\n\n"
                f"Want one for a real topic? Try `/caption <your topic>`"
            )
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

        elif action == "show_categories":
            await categories_command(update, context)

        else:
            logger.warning("Unknown callback_data received: %s", data)

    except Exception:
        logger.exception("Error handling button callback (data=%r)", query.data)
        await query.message.reply_text(
            "😕 Something went wrong handling that button. Please try again."
        )


# =====================================================================
# GLOBAL ERROR HANDLER
# =====================================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception while processing an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "😕 Oops, something unexpected happened on my end. Please try again."
            )
        except Exception:
            logger.exception("Failed to notify user about an earlier error.")


# =====================================================================
# APPLICATION ENTRY POINT
# =====================================================================

def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "ERROR: BOT_TOKEN is missing. Please provide it through the web/environment."
        )

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("caption", caption_command))

    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
    application.add_error_handler(error_handler)

    logger.info("Caption Bot is starting (polling mode)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
