import os
import random
import re
import logging
import asyncio
from threading import Thread
from flask import Flask
from typing import Optional
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("caption_bot")

# বটের ঘুম আটকানোর জন্য Flask সার্ভার
app_flask = Flask(__name__)
@app_flask.route('/')
def home():
    return "Caption Bot is running perfectly! 🚀"

def run_server():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# একাধিক টোকেন রিড করার ফাংশন
def get_tokens():
    tokens = []
    for i in range(1, 50):
        token = os.getenv(f"BOT_TOKEN_{i}")
        if token:
            tokens.append(token)
    single_token = os.getenv("BOT_TOKEN")
    if single_token and single_token not in tokens:
        tokens.append(single_token)
    return tokens


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
        "hashtags": ["#Attitude", "#Savage", "#Boss", "#Confidence", "#SwagStatus", "#NoFilter", "#StayReal"],
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
        "hashtags": ["#Love", "#Couple", "#InLove", "#Romance", "#SoulMate", "#TogetherForever", "#LoveStory"],
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
        "hashtags": ["#Sad", "#Alone", "#BrokenHeart", "#Pain", "#DeepThoughts", "#Healing"],
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
        "hashtags": ["#Motivation", "#Grind", "#Success", "#Hustle", "#GoalDigger", "#NeverGiveUp", "#MindsetMatters"],
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
        "hashtags": ["#Gaming", "#Gamer", "#GameOn", "#Esports", "#PlayerOne", "#GG"],
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
        "hashtags": ["#Travel", "#Wanderlust", "#Explore", "#TravelGram", "#AdventureAwaits"],
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
        "hashtags": ["#Funny", "#Comedy", "#Meme", "#Humor", "#LOL"],
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
        "hashtags": ["#Vibes", "#Mood", "#InstaGood", "#Blessed", "#DailyLife"],
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
# COMMAND HANDLERS (UPDATED WELCOME MESSAGE)
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_first_name = escape_md_v2(update.effective_user.first_name if update.effective_user else "there")
    welcome_text = (
        f"🔥 *Welcome {user_first_name} to Caption Bot\\!* 🔥\n\n"
        "✨ I am your personal AI assistant to generate awesome, eye\\-catching social media captions with matching hashtags instantly\\.\n\n"
        "📌 *How to use me:*\n"
        "Just send a command like this:\n"
        "`/caption sunset at the beach`\n"
        "`/caption gym motivation`\n"
        "`/caption my cute cat`\n\n"
        "📂 *Features:*\n"
        "• Attitude, Love, Sad, Motivation, Gaming, Travel & more\\!\n"
        "• One\\-tap copy blocks & direct share options\\.\n\n"
        "👉 *Tap /categories to explore styles or start typing your topic right now\\!*"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 View Categories", callback_data="show_categories")],
        [InlineKeyboardButton("⚡ Quick Help", callback_data="help_callback")]
    ])
    
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "*📖 How to use Caption Bot*\n\n"
        "*/caption* `<topic or mood>`\n"
        "Generates a caption \\+ hashtags for whatever you type\\.\n"
        "Example: `/caption gym day`\n\n"
        "*/categories*\n"
        "Shows all available caption styles\\.\n\n"
        "*/start*\n"
        "Shows the welcome message again\\."
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

    lines.append("\nTap a category below for a sample caption, or use `/caption <your topic>`\\.")
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
        await update.message.reply_text("⚠️ That topic is a bit too long — please keep it under 100 characters.")
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
        await update.message.reply_text("😕 Something went wrong while generating your caption. Please try again.")

async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤔 I didn't quite get that. Try `/caption <your topic>` or /help for a full guide.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

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
            await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)

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
            hashtags = random.sample(CATEGORIES[category_key]["hashtags"], k=min(3, len(CATEGORIES[category_key]["hashtags"])))
            text = (
                f"*{escape_md_v2(CATEGORIES[category_key]['label'])} sample:*\n\n"
                f"{escape_md_v2(sample_caption)}\n\n"
                f"{escape_md_v2(' '.join(hashtags))}\n\n"
                f"Want one for a real topic? Try `/caption <your topic>`"
            )
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

        elif action == "show_categories":
            await categories_command(update, context)

        elif action == "help_callback":
            help_text = (
                "*📖 How to use Caption Bot*\n\n"
                "*/caption* `<topic or mood>`\n"
                "Generates a caption \\+ hashtags for whatever you type\\.\n"
                "Example: `/caption gym day`"
            )
            await query.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)

    except Exception:
        logger.exception("Error handling button callback")
        await query.message.reply_text("😕 Something went wrong handling that button.")


# =====================================================================
# MAIN FUNCTION
# =====================================================================

async def main():
    Thread(target=run_server, daemon=True).start()
    
    tokens = get_tokens()
    if not tokens:
        logger.error("No tokens found! Please set BOT_TOKEN or BOT_TOKEN_1 in environment variables.")
        return

    for token in tokens:
        app = Application.builder().token(token).concurrent_updates(True).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("categories", categories_command))
        app.add_handler(CommandHandler("caption", caption_command))
        app.add_handler(CallbackQueryHandler(button_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("A caption bot instance started successfully and polling!")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
