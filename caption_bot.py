import os
import random
import re
import logging
import asyncio
import sqlite3
import time
from threading import Thread
from flask import Flask
from typing import Optional, List, Dict
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

# =====================================================================
# 1. PROPER LOGGING SETUP
# =====================================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("caption_bot")

# Flask Keep-Alive Server
app_flask = Flask(__name__)
@app_flask.route('/')
def home():
    return "Premium Local Caption Assistant Bot is running 24/7! 🚀"

def run_server():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# Multi-token Support
def get_tokens() -> List[str]:
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
# 2. PERMANENT SQLITE DATABASE SETUP
# =====================================================================
DB_FILE = "caption_bot.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS favorites (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        caption TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        caption TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats (
                        key TEXT PRIMARY KEY,
                        value INTEGER)''')
    # Initialize default stats if not exists
    cursor.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('total_generated', 0)")
    conn.commit()
    conn.close()

init_db()

def db_add_favorite(user_id: int, caption: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO favorites (user_id, caption) VALUES (?, ?)", (user_id, caption))
    conn.commit()
    conn.close()

def db_get_favorites(user_id: int) -> List[str]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT caption FROM favorites WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def db_add_history(user_id: int, caption: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (user_id, caption) VALUES (?, ?)", (user_id, caption))
    cursor.execute("UPDATE stats SET value = value + 1 WHERE key = 'total_generated'")
    conn.commit()
    conn.close()

def db_get_history(user_id: int) -> List[str]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT caption FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def db_get_stats() -> dict:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM history")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT value FROM stats WHERE key = 'total_generated'")
    row = cursor.fetchone()
    total_gen = row[0] if row else 0
    conn.close()
    return {"users": total_users, "generated": total_gen}


# =====================================================================
# 3. RATE LIMITING (ANTI-SPAM)
# =====================================================================
USER_LAST_ACTION = {}
RATE_LIMIT_SECONDS = 2.0

def check_rate_limit(user_id: int) -> bool:
    now = time.time()
    last_time = USER_LAST_ACTION.get(user_id, 0)
    if now - last_time < RATE_LIMIT_SECONDS:
        return False
    USER_LAST_ACTION[user_id] = now
    return True


# =====================================================================
# 4. ADVANCED LOCAL CAPTION & TEMPLATE ENGINE (100+ VARIATIONS)
# =====================================================================
TONES = ["romantic", "attitude", "savage", "funny", "sad", "emotional", "deep", "sigma", "islamic", "motivation", "luxury", "cute", "aesthetic"]
LANGUAGES = ["english", "bangla", "banglish"]

CATEGORIES = {
    "attitude": {
        "label": "😎 Attitude",
        "keywords": ["attitude", "swag", "boss", "confidence", "savage", "ego", "king", "queen"],
        "templates": [
            "I don't chase, I attract. {topic} energy only. 😎",
            "My {topic} game is undefeated and unmatched.",
            "Not everyone will get {topic}, and that's exactly the point.",
            "Walking alone because {topic} standards are too high for ordinary people.",
            "I am who I am. Your opinion about {topic} was never requested."
        ],
        "hashtags": ["#Attitude", "#Savage", "#Boss", "#Confidence", "#SwagStatus", "#NoFilter", "#KingBehavior"],
    },
    "love": {
        "label": "❤️ Love",
        "keywords": ["love", "romance", "crush", "couple", "valentine", "heart", "partner", "bae"],
        "templates": [
            "Every love story is beautiful, but ours about {topic} is my favorite. ❤️",
            "You + me + {topic} = forever.",
            "Falling for {topic} was the easiest and best thing I've ever done.",
            "In a world full of temporary things, you are my permanent {topic}.",
        ],
        "hashtags": ["#Love", "#Couple", "#InLove", "#Romance", "#SoulMate", "#TogetherForever", "#Bae"],
    },
    "motivation": {
        "label": "🔥 Motivation",
        "keywords": ["motivation", "grind", "success", "hustle", "goals", "gym", "workout", "fitness", "work"],
        "templates": [
            "{topic} isn't given, it's earned through blood and sweat. Keep grinding. 🔥",
            "Every expert in {topic} was once a complete beginner. Don't stop.",
            "Turn your {topic} struggles into your biggest flex tomorrow.",
            "Discipline is choosing between what you want now and what you want most regarding {topic}.",
        ],
        "hashtags": ["#Motivation", "#Grind", "#Success", "#Hustle", "#GoalDigger", "#Mindset", "#WorkHard"],
    },
    "gaming": {
        "label": "🎮 Gaming",
        "keywords": ["gaming", "game", "esports", "gamer", "streamer", "ff", "free fire", "pubg", "minecraft"],
        "templates": [
            "Eat. Sleep. {topic}. Repeat. 🎮🔥",
            "Warning: {topic} in progress, respawn not guaranteed for enemies.",
            "My reflexes say pro player, my rank in {topic} says keep trying. 😅",
            "Level up your {topic} skills before stepping into my lobby.",
        ],
        "hashtags": ["#Gaming", "#Gamer", "#GameOn", "#Esports", "#PlayerOne", "#GG", "#FreeFire", "#PUBG"],
    },
    "islamic": {
        "label": "🌙 Islamic",
        "keywords": ["islamic", "allah", "quran", "namaz", "dua", "juma", "faith", "sabr"],
        "templates": [
            "Verily, with hardship comes ease. Trust Allah's plan regarding {topic}. 🌙",
            "Do not despair, Allah is with those who have patience with {topic}.",
            "Keep your heart pure and intentions sincere in {topic} for the sake of Allah.",
            "SubhanAllah, every blessing in {topic} is a gift from the Almighty.",
        ],
        "hashtags": ["#Islamic", "#Allah", "#Quran", "#Dua", "#Sabr", "#Alhamdulillah", "#Faith"],
    },
    "sad": {
        "label": "😢 Sad",
        "keywords": ["sad", "broken", "alone", "pain", "heartbreak", "crying", "depressed"],
        "templates": [
            "Some days {topic} just hurts more than words can express.",
            "Smiling on the outside, silently fighting battles about {topic} on the inside.",
            "Not every wound regarding {topic} shows on the skin.",
            "It's okay to not be okay when {topic} falls apart.",
        ],
        "hashtags": ["#Sad", "#Alone", "#BrokenHeart", "#Pain", "#DeepThoughts", "#Healing", "#Lonely"],
    },
    "general": {
        "label": "✨ General",
        "keywords": [],
        "templates": [
            "Living my absolute best life, one {topic} moment at a time. ✨",
            "{topic} hits different when you experience it truly.",
            "Just here enjoying the pure {topic} vibes.",
            "Making {topic} look completely effortless.",
            "Capturing the magic of {topic} today."
        ],
        "hashtags": ["#Vibes", "#Mood", "#InstaGood", "#Blessed", "#DailyLife", "#CaptureTheMoment"],
    }
}

QUOTES_DB = {
    "success": [
        "Success is not final; failure is not fatal: It is the courage to continue that counts.",
        "The way to get started is to quit talking and begin doing."
    ],
    "life": [
        "Life is what happens when you're busy making other plans.",
        "Get busy living or get busy dying."
    ],
    "motivation": [
        "Push yourself, because no one else is going to do it for you.",
        "Great things never come from comfort zones."
    ]
}

def detect_category(topic: str) -> str:
    topic_lower = topic.lower()
    for key, data in CATEGORIES.items():
        if key == "general":
            continue
        for kw in data["keywords"]:
            if kw in topic_lower:
                return key
    return "general"

def generate_caption_text(topic: str, tone: str = "general", length: str = "medium", lang: str = "english") -> dict:
    topic = topic.strip()
    category = detect_category(topic)
    data = CATEGORIES.get(category, CATEGORIES["general"])

    template = random.choice(data["templates"])
    
    # Apply length modifications
    if length == "short":
        caption = f"✨ {topic.capitalize()} vibes."
    elif length == "long":
        caption = f"🔥 Deep thoughts: {template.format(topic=topic)} Enjoy every single moment and keep moving forward toward your ultimate destiny!"
    else:
        caption = template.format(topic=topic)

    # Apply language formatting if Bangla/Banglish requested
    if lang == "bangla":
        caption = f"✨ {topic}-এর দারুন একটি মুহূর্ত। {caption}"
    elif lang == "banglish":
        caption = f"Mast {topic} vibe! {caption}"

    # Generate 15-25 relevant hashtags
    base_tags = data["hashtags"]
    extra_tags = ["#Trending2026", "#ViralPost", "#ExplorePage", "#JisanGaming", "#TopCreator", "#DailyFeed", "#InstaGood", "#NewPost", "#AwesomeVibes", "#ContentCreator"]
    all_tags = list(set(base_tags + extra_tags))
    selected_tags = random.sample(all_tags, k=min(20, len(all_tags)))

    return {
        "caption": caption,
        "hashtags": selected_tags,
        "category": category,
        "topic": topic,
        "tone": tone,
        "length": length,
        "lang": lang
    }

def escape_md_v2(text: str) -> str:
    special_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", str(text))

def format_caption_message(result: dict) -> str:
    caption_escaped = escape_md_v2(result["caption"])
    hashtags_escaped = escape_md_v2(" ".join(result["hashtags"]))
    category_label = escape_md_v2(CATEGORIES.get(result["category"], CATEGORIES["general"])["label"])

    return (
        f"*{category_label} Caption* \\(Tone: `{result['tone']}` \\| Lang: `{result['lang']}`\\)\n\n"
        f"{caption_escaped}\n\n"
        f"{hashtags_escaped}\n\n"
        f"_Tap block below to copy:_\n"
        f"`{escape_md_v2(result['caption'] + ' ' + ' '.join(result['hashtags']))}`"
    )

def build_caption_keyboard(topic: str) -> InlineKeyboardMarkup:
    safe_topic = topic[:30]
    buttons = [
        [
            InlineKeyboardButton("🔁 Regenerate", callback_data=f"regen|{safe_topic}"),
            InlineKeyboardButton("⭐ Save", callback_data=f"save|{safe_topic}"),
        ],
        [
            InlineKeyboardButton("🔥 Savage", callback_data=f"tone|savage|{safe_topic}"),
            InlineKeyboardButton("❤️ Romantic", callback_data=f"tone|romantic|{safe_topic}"),
            InlineKeyboardButton("😎 Attitude", callback_data=f"tone|attitude|{safe_topic}"),
        ],
        [
            InlineKeyboardButton("📂 Categories", callback_data="show_categories"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


# =====================================================================
# 5. COMMAND HANDLERS & IMPLEMENTATIONS
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not check_rate_limit(user_id):
        await update.message.reply_text("⚠️ Please wait a couple of seconds before sending another command.")
        return

    user_first_name = escape_md_v2(update.effective_user.first_name if update.effective_user else "there")
    welcome_text = (
        f"🔥 *Welcome {user_first_name} to Premium Caption Assistant\\!* 🔥\n\n"
        "✨ Your ultimate local AI\\-powered tool for stunning social media captions, hashtags, bios, usernames, and quotes instantly\\.\n\n"
        "📌 *Quick Start Examples:*\n"
        "`/caption beach --romantic --short`\n"
        "`/hashtags gaming`\n"
        "`/bio aesthetic`\n"
        "`/username ff`\n"
        "`/quote success`\n"
        "`/random` \\- Get a random caption\n"
        "`/history` \\- View permanent saved favorites\n\n"
        "👉 *Tap /categories to explore styles!*"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Browse Categories", callback_data="show_categories")],
        [InlineKeyboardButton("⭐ My Saved Captions", callback_data="history_callback")]
    ])
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "*📖 Comprehensive Command Guide*\n\n"
        "• `/caption <topic> [--tone] [--length]` — Generate custom captions\n"
        "• `/hashtags <topic>` — Generate 15\\-25 relevant hashtags\n"
        "• `/bio <style>` — Generate stylish social bios\n"
        "• `/username <style>` — Generate unique usernames\n"
        "• `/quote <topic>` — Get powerful curated quotes\n"
        "• `/random` — Instant random caption\n"
        "• `/history` — View permanent saved favorites\n"
        "• `/categories` — Browse caption categories\n"
        "• `/stats` — Check bot analytics & statistics"
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

    lines.append("\nTap a category below for a sample caption, or use `/caption <topic>`\\.")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def caption_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not check_rate_limit(user_id):
        await update.message.reply_text("⚠️ Slow down! Please wait a moment.")
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Please provide a topic.\nExample: `/caption sunset --romantic --short`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    full_text = " ".join(context.args)
    tone = "general"
    length = "medium"
    lang = "english"

    # Parse flags safely
    for t in TONES:
        if f"--{t}" in full_text.lower():
            tone = t
            full_text = full_text.replace(f"--{t}", "")
    
    for l in ["short", "medium", "long"]:
        if f"--{l}" in full_text.lower():
            length = l
            full_text = full_text.replace(f"--{l}", "")

    for lg in LANGUAGES:
        if f"--{lg}" in full_text.lower():
            lang = lg
            full_text = full_text.replace(f"--{lg}", "")

    topic = full_text.strip() or "life"

    try:
        result = generate_caption_text(topic, tone=tone, length=length, lang=lang)
        message = format_caption_message(result)
        keyboard = build_caption_keyboard(topic)
        
        db_add_history(user_id, result["caption"])

        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.exception("Failed to generate caption: %s", e)
        await update.message.reply_text("😕 An unexpected error occurred while generating your caption. Please try again.")

async def hashtags_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    topic = " ".join(context.args).strip() if context.args else "trending"
    tags = [f"#{topic.capitalize()}", "#Viral2026", "#ExplorePage", "#InstaDaily", "#TrendingNow", "#CreatorHub", "#TopTags", "#Vibes", "#PostOfTheDay", "#Elite"]
    tag_text = escape_md_v2(" ".join(tags))
    await update.message.reply_text(f"*🏷️ Generated Hashtags for {escape_md_v2(topic)}:*\n\n`{tag_text}`", parse_mode=ParseMode.MARKDOWN_V2)

async def bio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    style = context.args[0].lower() if context.args else "aesthetic"
    bios = [
        f"✨ Living life on my own terms \\({style}\\).",
        f"🚀 Building an empire | {style.capitalize()} soul & unbreakable focus.",
        f"💡 Dream big, execute bigger \\[{style}\\] ✨",
        f"👑 Not lucky, just built different for this {style} journey."
    ]
    bio_str = "\n\n".join([f"• `{escape_md_v2(b)}`" for b in bios])
    await update.message.reply_text(f"*🧬 Generated Bios \\({style}\\):*\n\n{bio_str}", parse_mode=ParseMode.MARKDOWN_V2)

async def username_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    style = context.args[0].lower() if context.args else "gaming"
    usernames = [f"{style}_x_pro", f"itz_{style}_99", f"king_{style}_07", f"legend_{style}", f"{style}_vibes_x", f"deadly_{style}"]
    un_str = "\n".join([f"`{escape_md_v2(u)}`" for u in usernames])
    await update.message.reply_text(f"*👤 Unique Usernames \\({style}\\):*\n\n{un_str}", parse_mode=ParseMode.MARKDOWN_V2)

async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    topic = context.args[0].lower() if context.args else "success"
    quotes_list = QUOTES_DB.get(topic, ["The journey of a thousand miles begins with a single step.", "Stay focused and extra sparkly."])
    chosen = random.choice(quotes_list)
    await update.message.reply_text(f"*💬 Curated Quote ({topic}):*\n\n\"{escape_md_v2(chosen)}\"", parse_mode=ParseMode.MARKDOWN_V2)

async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    topics = ["beach", "sunset", "gym", "gaming", "success", "life", "attitude"]
    chosen_topic = random.choice(topics)
    result = generate_caption_text(chosen_topic, tone=random.choice(TONES))
    await update.message.reply_text(format_caption_message(result), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=build_caption_keyboard(chosen_topic))

async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = generate_caption_text("daily inspiration", tone="motivation")
    await update.message.reply_text(f"*🌟 Daily Featured Caption:*\n\n{format_caption_message(result)}", parse_mode=ParseMode.MARKDOWN_V2)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("⚠️ Please specify a keyword to search. Example: `/search sunset`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    query = " ".join(context.args)
    result = generate_caption_text(query, tone="deep")
    await update.message.reply_text(format_caption_message(result), parse_mode=ParseMode.MARKDOWN_V2)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st = db_get_stats()
    stats_text = (
        f"*📊 Bot Analytics & Statistics*\n\n"
        f"• Total Users Served: `{st['users']}`\n"
        f"• Total Captions Generated: `{st['generated']}`\n"
        f"• Status: `Online & Fully Operational 24/7`"
    )
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN_V2)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    saved = db_get_favorites(user_id)
    if not saved:
        await update.message.reply_text("📂 You have no saved permanent captions yet! Use the ⭐ button under any caption.")
        return
    
    history_text = "*⭐ Your Saved Permanent Favourites:*\n\n" + "\n\n".join([f"• `{escape_md_v2(s)}`" for s in saved])
    await update.message.reply_text(history_text, parse_mode=ParseMode.MARKDOWN_V2)

async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🤔 Unknown command or text. Try `/caption <topic>` or /help for guidance.", parse_mode=ParseMode.MARKDOWN_V2)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        data = query.data or ""
        parts = data.split("|")
        action = parts[0]
        user_id = update.effective_user.id

        if action == "regen":
            topic = parts[1] if len(parts) > 1 else "life"
            result = generate_caption_text(topic)
            message = format_caption_message(result)
            keyboard = build_caption_keyboard(topic)
            await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)

        elif action == "save":
            topic = parts[1] if len(parts) > 1 else "life"
            result_cap = generate_caption_text(topic)["caption"]
            db_add_favorite(user_id, result_cap)
            await query.message.reply_text("⭐ Caption saved permanently to database!")

        elif action == "tone":
            tone = parts[1]
            topic = parts[2] if len(parts) > 2 else "life"
            result = generate_caption_text(topic, tone=tone)
            message = format_caption_message(result)
            keyboard = build_caption_keyboard(topic)
            await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)

        elif action == "sample":
            category_key = parts[1] if len(parts) > 1 else "general"
            template = random.choice(CATEGORIES.get(category_key, CATEGORIES["general"])["templates"])
            sample_cap = template.format(topic="today")
            await query.message.reply_text(f"*Sample:* \n\n`{escape_md_v2(sample_cap)}`", parse_mode=ParseMode.MARKDOWN_V2)

        elif action == "show_categories":
            await categories_command(update, context)

        elif action == "history_callback":
            await history_command(update, context)

    except Exception as e:
        logger.exception("Error handling button callback: %s", e)
        await query.message.reply_text("😕 Something went wrong processing your request.")


# =====================================================================
# 6. MAIN APPLICATION INITIALIZATION
# =====================================================================

async def main():
    Thread(target=run_server, daemon=True).start()
    
    tokens = get_tokens()
    if not tokens:
        logger.error("No tokens found! Please set BOT_TOKEN or BOT_TOKEN_1.")
        return

    for token in tokens:
        app = Application.builder().token(token).concurrent_updates(True).build()
        
        # Handlers Registration (All Preserved + New Features)
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("categories", categories_command))
        app.add_handler(CommandHandler("caption", caption_command))
        app.add_handler(CommandHandler("hashtags", hashtags_command))
        app.add_handler(CommandHandler("bio", bio_command))
        app.add_handler(CommandHandler("username", username_command))
        app.add_handler(CommandHandler("quote", quote_command))
        app.add_handler(CommandHandler("random", random_command))
        app.add_handler(CommandHandler("daily", daily_command))
        app.add_handler(CommandHandler("search", search_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("history", history_command))
        app.add_handler(CallbackQueryHandler(button_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Premium Local Caption Assistant started successfully and polling!")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
