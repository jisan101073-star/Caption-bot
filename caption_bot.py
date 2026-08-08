import os
import random
import logging
import asyncio
import sqlite3
from threading import Thread
from flask import Flask
from typing import List
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    BotCommand,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# 1. LOGGING & FLASK SERVER
# =====================================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("caption_bot")

app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Caption Assistant Bot is running 24/7! 🚀"

def run_server():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# =====================================================================
# 2. SQLITE DATABASE (States & Storage)
# =====================================================================
DB_FILE = "caption_bot.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS favorites (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        caption TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_state (
                        user_id INTEGER PRIMARY KEY,
                        category TEXT,
                        language TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats (
                        key TEXT PRIMARY KEY,
                        value INTEGER)''')
    cursor.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('total_generated', 0)")
    conn.commit()
    conn.close()

init_db()

def set_user_state(user_id: int, category: str = None, language: str = None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT category, language FROM user_state WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    cur_cat = category if category is not None else (row[0] if row else "aesthetic")
    cur_lang = language if language is not None else (row[1] if row else "english")
    
    cursor.execute('''INSERT OR REPLACE INTO user_state (user_id, category, language) 
                      VALUES (?, ?, ?)''', (user_id, cur_cat, cur_lang))
    conn.commit()
    conn.close()

def get_user_state(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT category, language FROM user_state WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"category": row[0], "language": row[1]}
    return {"category": "aesthetic", "language": "english"}

def db_increment_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE stats SET value = value + 1 WHERE key = 'total_generated'")
    conn.commit()
    conn.close()

# =====================================================================
# 3. EXPANDED PRE-DEFINED CATEGORIES & CAPTIONS DATA
# =====================================================================
CATEGORIES = {
    "aesthetic": {
        "label": "✨ Aesthetic Caption",
        "templates": {
            "short": ["Living my best life in silence. ✨", "Soft colors and quiet moments.", "Pure soul, peaceful mind."],
            "medium": ["Some moments in life cannot be measured by time, but by how deeply they touch your soul.", "Creating a life that feels good on the inside, not just one that looks good on the outside."],
            "long": ["In a world full of noise, finding peace in the little details is an art. Let your mind wander where the Wi-Fi is weak and your heart feels completely at home."]
        },
        "hashtags": ["#Aesthetic", "#Vibes", "#Peaceful", "#Mood", "#ExplorePage"]
    },
    "stylish": {
        "label": "💎 Stylish Caption",
        "templates": {
            "short": ["Classy is when you have a lot to say but you stay silent. 🖤", "Born to stand out, never to fit in.", "Elegance is an attitude."],
            "medium": ["I don't compete for a spot, I create my own lane. Watch and learn.", "Too glam to give a damn, too chic to repeat."],
            "long": ["Style is a way to say who you are without having to speak. Keep your heels, head, and standards high because standard is something you never compromise."]
        },
        "hashtags": ["#Stylish", "#Classy", "#Elegance", "#Swag", "#BossLife"]
    },
    "islamic": {
        "label": "🌙 Islamic Caption",
        "templates": {
            "short": ["Verily, with hardship comes ease. 🌙", "Trust Allah's perfect timing.", "Alhamdulillah always."],
            "medium": ["Do not despair, for Allah is with those who have patience through every storm.", "Keep your heart pure and intentions sincere for the sake of Allah alone."],
            "long": ["No matter how dark the night is, the morning light of hope given by Allah will always find its way to your soul. Trust His plan blindly."]
        },
        "hashtags": ["#Islamic", "#Allah", "#Quran", "#Dua", "#Alhamdulillah"]
    },
    "motivation": {
        "label": "🔥 Motivation & Gym",
        "templates": {
            "short": ["Sweat today, shine tomorrow. 🔥", "Be stronger than your excuses.", "Hustle in silence, let success make the noise."],
            "medium": ["The body achieves what the mind believes. Push past your limits every single day.", "Hard work beats talent when talent doesn't work hard."],
            "long": ["Success isn't given to you on a silver platter, you have to earn it through blood, sweat, and relentless discipline every single day of your life."]
        },
        "hashtags": ["#Motivation", "#GymLife", "#Hustle", "#Fitness", "#HardWork"]
    },
    "success": {
        "label": "🚀 Success & Hustle",
        "templates": {
            "short": ["Focus on the goal. 🚀", "Building an empire from scratch.", "Dream big, work hard."],
            "medium": ["Don't stop when you're tired, stop when you're done. Your future self will thank you.", "Success is not overnight; it's a small daily progress adding up."],
            "long": ["They will laugh at your dreams until you succeed, then they will ask how you did it. Keep your head down and let your achievements do all the talking."]
        },
        "hashtags": ["#Success", "#Entrepreneur", "#Mindset", "#Goals", "#HustleHard"]
    },
    "friendship": {
        "label": "🤝 Friendship & Friends",
        "templates": {
            "short": ["Partners in crime. 🤝", "Good times + Crazy friends = Great memories.", "Chosen family."],
            "medium": ["We didn't realize we were making memories, we just knew we were having fun together.", "True friends are never apart, maybe in distance but never in heart."],
            "long": ["A real friend is one who walks in when the rest of the world walks out. Grateful for the ones who know all my flaws and still choose to stay."]
        },
        "hashtags": ["#Friendship", "#BestFriends", "#Memories", "#SquadGoals", "#Brotherhood"]
    },
    "sad": {
        "label": "😢 Sad Caption",
        "templates": {
            "short": ["Some wounds never truly heal.", "Smiling outside, breaking inside.", "Silent tears speak the loudest."],
            "medium": ["It hurts when the person who gave you the best memories becomes a memory themselves.", "Not every broken heart shows visible scars on the skin."],
            "long": ["Sometimes you just need to disconnect from the world and let yourself feel everything, because holding onto fake smiles hurts way more than real tears."]
        },
        "hashtags": ["#Sad", "#Heartbroken", "#Alone", "#DeepThoughts", "#Pain"]
    },
    "funny": {
        "label": "😂 Funny Caption",
        "templates": {
            "short": ["I need a 6-month vacation, twice a year. 😂", "Error 404: Bio not found.", "Born to rest, forced to work."],
            "medium": ["I'm not lazy, I'm just on energy-saving mode until further notice.", "My bed and I are deeply in love, but my alarm clock is jealous."],
            "long": ["I put the 'pro' in procrastinate. If laziness was an Olympic sport, I would definitely win the gold medal without even standing up from my couch."]
        },
        "hashtags": ["#Funny", "#Humor", "#LaughOutLoud", "#Relatable", "#Vibes"]
    },
    "attitude": {
        "label": "😎 Attitude Caption",
        "templates": {
            "short": ["I don't chase, I attract. 😎", "My attitude is based on how you treat me.", "Unmatched energy only."],
            "medium": ["I am who I am. Your approval is neither required nor desired.", "Treat me like a king and I'll treat you like a queen, treat me like a game and I'll show you how it's played."],
            "long": ["People will always judge your journey without knowing your struggles. Let them talk, because your success will answer all their questions permanently."]
        },
        "hashtags": ["#Attitude", "#Savage", "#King", "#Confidence", "#Fearless"]
    },
    "travel": {
        "label": "✈️ Travel & Nature",
        "templates": {
            "short": ["Collect moments, not things. ✈️", "Born to roam, world is my home.", "Escape the ordinary."],
            "medium": ["To travel is to live, and nature has the best therapy for a tired soul.", "The view is always worth the steep climb."],
            "long": ["Traveling opens your mind, fills your heart with wonder, and leaves you with stories that last a lifetime. Let's find some beautiful places to get lost."]
        },
        "hashtags": ["#Travel", "#Nature", "#Wanderlust", "#Explorer", "#Adventure"]
    },
    "couple": {
        "label": "❤️ Couple & Love",
        "templates": {
            "short": ["My favorite person. ❤️", "You + Me = Forever.", "Home is wherever you are."],
            "medium": ["Every love story is beautiful, but ours is my absolute favorite piece of art.", "You are my today and all of my tomorrows."],
            "long": ["I never truly understood what it meant to find my home in another person until the day I met you. Holding your hand is my safest place on earth."]
        },
        "hashtags": ["#CoupleGoals", "#Love", "#Soulmate", "#Forever", "#TrueLove"]
    }
}

def generate_batch_captions(cat_key: str, lang: str, offset: int = 0) -> List[str]:
    cat_data = CATEGORIES.get(cat_key, CATEGORIES["aesthetic"])
    all_templates = []
    
    for size in ["short", "medium", "long"]:
        for t in cat_data["templates"][size]:
            size_badge = "📌 [Short]" if size == "short" else ("📝 [Medium]" if size == "medium" else "📜 [Long]")
            all_templates.append((t, size_badge))
            
    generated = []
    pool = all_templates * 4
    random.seed(hash(cat_key) + offset)
    random.shuffle(pool)
    
    for i in range(10):
        template_text, size_badge = pool[i % len(pool)]
        caption = template_text
        
        if lang == "bangla":
            caption = f"✨ সুন্দর একটি মুহূর্ত। {caption}"
        elif lang == "banglish":
            caption = f"Mast vibe! {caption}"
            
        tags = " ".join(random.sample(cat_data["hashtags"], k=min(4, len(cat_data["hashtags"]))))
        full_text = f"{size_badge} {caption}\n\n{tags}"
        generated.append(full_text)
        
    return generated

# =====================================================================
# 4. BOT HANDLERS (Flow like Name Maker Bot)
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    name = update.effective_user.first_name if update.effective_user else "Friend"
    set_user_state(user_id, category="aesthetic", language="english")
    
    welcome_text = (
        f"✨ <b>Welcome {name} to Caption Maker Bot!</b> ✨\n\n"
        "Main aapke liye best Aesthetic, Stylish, Islamic, Motivation, Sad, Funny aur Attitude captions generate kar sakta hoon.\n\n"
        "👇 <b>Niche diye gaye button se option select karein:</b>"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Make Caption", callback_data="make_caption")],
        [InlineKeyboardButton("⭐ Saved Captions", callback_data="show_saved")]
    ])
    
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    elif update.callback_query:
        await update.callback_query.message.edit_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    try:
        if data == "main_menu":
            await start(update, context)
            
        elif data == "make_caption":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🇬🇧 English", callback_data="lang_english")],
                [InlineKeyboardButton("🇧🇩 Bangla", callback_data="lang_bangla")],
                [InlineKeyboardButton("💬 Banglish", callback_data="lang_banglish")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ])
            await query.message.edit_text(
                "🌐 <b>Kripya language select karein:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            
        elif data.startswith("lang_"):
            lang = data.split("_")[1]
            set_user_state(user_id, language=lang)
            
            # Categories button layout (2 columns for neat design)
            keys = list(CATEGORIES.keys())
            kb_buttons = []
            for i in range(0, len(keys), 2):
                row = [InlineKeyboardButton(CATEGORIES[keys[i]]["label"], callback_data=f"cat_{keys[i]}")]
                if i + 1 < len(keys):
                    row.append(InlineKeyboardButton(CATEGORIES[keys[i+1]]["label"], callback_data=f"cat_{keys[i+1]}"))
                kb_buttons.append(row)
                
            kb_buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
            kb = InlineKeyboardMarkup(kb_buttons)
            
            await query.message.edit_text(
                f"✅ <b>Language:</b> {lang.capitalize()}\n\n👇 <b>Please choose a category below to see designs:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            
        elif data.startswith("cat_"):
            cat_key = data.split("_")[1]
            set_user_state(user_id, category=cat_key)
            
            st = get_user_state(user_id)
            lang = st["language"]
            
            captions = generate_batch_captions(cat_key, lang, offset=0)
            cat_label = CATEGORIES[cat_key]["label"]
            
            header = f"📁 <b>Category:</b> {cat_label}\n🌐 <b>Language:</b> {lang.capitalize()}\n📄 <b>Page:</b> 1 (10 Captions)\n\n👇 <b>Click on any caption text below to copy:</b>"
            list_text = header + "\n\n" + "\n\n-------------------\n\n".join([f"<b>{idx+1}.</b> <code>{c}</code>" for idx, c in enumerate(captions)])
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Next ➡️ (More 10)", callback_data=f"page|{cat_key}|1")],
                [InlineKeyboardButton("🔄 New Category", callback_data="lang_" + lang), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ])
            
            db_increment_stats()
            await query.message.edit_text(list_text, parse_mode=ParseMode.HTML, reply_markup=kb)
            
        elif data.startswith("page|"):
            parts = data.split("|")
            cat_key = parts[1]
            page_num = int(parts[2])
            next_page = page_num + 1
            if next_page > 5:
                next_page = 1
                
            st = get_user_state(user_id)
            lang = st["language"]
            
            captions = generate_batch_captions(cat_key, lang, offset=next_page)
            cat_label = CATEGORIES[cat_key]["label"]
            
            header = f"📁 <b>Category:</b> {cat_label}\n🌐 <b>Language:</b> {lang.capitalize()}\n📄 <b>Page:</b> {next_page}/5 (10 Captions)\n\n👇 <b>Click on any caption text below to copy:</b>"
            list_text = header + "\n\n" + "\n\n-------------------\n\n".join([f"<b>{idx+1}.</b> <code>{c}</code>" for idx, c in enumerate(captions)])
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Next ➡️ (More 10)", callback_data=f"page|{cat_key}|{next_page}")],
                [InlineKeyboardButton("🔄 New Category", callback_data="lang_" + lang), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ])
            await query.message.edit_text(list_text, parse_mode=ParseMode.HTML, reply_markup=kb)
            
        elif data == "show_saved":
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
            await query.message.edit_text("⭐ <b>Saved Captions feature is coming soon!</b>", parse_mode=ParseMode.HTML, reply_markup=kb)
            
    except Exception as e:
        logger.exception("Callback error: %s", e)

# =====================================================================
# 5. SETUP COMMANDS & MAIN
# =====================================================================
async def setup_commands(application: Application):
    commands = [
        BotCommand("start", "বট শুরু করুন ও মেনু দেখুন"),
    ]
    await application.bot.set_my_commands(commands)

async def main():
    Thread(target=run_server, daemon=True).start()
    
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("No BOT_TOKEN found in environment variables!")
        return

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))

    await app.initialize()
    await setup_commands(app)
    await app.start()
    app.updater.start_polling(drop_pending_updates=True)
    logger.info("Caption Maker Bot is running with expanded categories!")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.main(main())
