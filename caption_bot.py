import os
import random
import logging
import sqlite3
import html
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
    return "AI Caption Bot is running 24/7! 🚀"

def run_server():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# =====================================================================
# 2. SQLITE DATABASE
# =====================================================================
DB_FILE = "caption_bot.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_state (
                        user_id INTEGER PRIMARY KEY,
                        category TEXT,
                        language TEXT)''')
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

# =====================================================================
# 3. AI-STYLE DYNAMIC CAPTION GENERATOR ENGINE (No Limits, Pure AI Style)
# =====================================================================
AI_VOCAB = {
    "aesthetic": {
        "label": "✨ Aesthetic Caption",
        "subjects": {
            "english": ["silent moments", "soft golden hours", "peaceful vibes", "quiet soul", "dreamy skies", "minimalist days", "cozy corners", "slow living"],
            "bangla": ["শান্ত মুহূর্ত", "সোনালী গোধূলি", "শান্ত পরিবেশ", "বিশুদ্ধ আত্মা", "স্বপ্নীল আকাশ", "সহজ জীবন", "আরামদায়ক কোণ", "ধীর জীবনযাপন"],
            "banglish": ["shanto muhurto", "golden hours", "peaceful vibe", "pure soul", "dreamy sky", "slow living", "cozy vibe", "quiet mind"]
        },
        "actions": {
            "english": ["finding beauty in", "healing through", "creating a world of", "embracing the magic of", "getting lost in", "discovering peace with"],
            "bangla": ["সৌন্দর্য খুঁজছি", "নিরাময় পাচ্ছি", "দুনিয়া গড়ছি", "ম্যাজিক উপভোগ করছি", "হারিয়ে যাচ্ছি", "শান্তি খুঁজে নিচ্ছি"],
            "banglish": ["beauty khujchi", "healing pacchi", "magic feel korchi", "hariye jachi", "shanti pacchi"]
        },
        "hashtags": ["#Aesthetic", "#Vibes", "#Peaceful", "#Mood", "#Explore", "#Soul", "#Minimal", "#Magic"]
    },
    "stylish": {
        "label": "💎 Stylish Caption",
        "subjects": {
            "english": ["my own standards", "unmatched class", "royal attitude", "pure elegance", "boss energy", "silent power", "iconic vibe", "bold moves"],
            "bangla": ["আমার নিজস্ব স্ট্যান্ডার্ড", "তুলনাহীন ক্লাস", "রাজকীয় অ্যাটিটিউড", "বিশুদ্ধ সৌন্দর্য", "বস্ এনার্জি", "নীরব ক্ষমতা", "আইকনিক ভাইব", "বোল্ড পদক্ষেপ"],
            "banglish": ["nijer standard", "unmatched class", "royal attitude", "pure elegance", "boss energy", "silent power", "iconic vibe", "bold moves"]
        },
        "actions": {
            "english": ["dominating the game with", "walking through life with", "setting the rules using", "shining bright with", "leaving traces of"],
            "bangla": ["গেম ডোমিনেট করছি", "জীবন কাটাচ্ছি", "নিয়ম তৈরি করছি", "উজ্জ্বল হচ্ছি", "চিহ্ন রেখে যাচ্ছি"],
            "banglish": ["game dominate korchi", "jibon kacchi", "rule banacchi", "ujjwal hocchi", "sign rekhe jachi"]
        },
        "hashtags": ["#Stylish", "#Classy", "#Elegance", "#Swag", "#BossLife", "#Attitude", "#Iconic", "#Elite"]
    },
    "islamic": {
        "label": "🌙 Islamic Caption",
        "subjects": {
            "english": ["Allah's perfect plan", "pure patience (Sabr)", "divine blessings", "faithful heart", "endless mercy", "silent prayers (Dua)", "guided soul", "Alhamdulillah moments"],
            "bangla": ["আল্লাহর নিখুঁত পরিকল্পনা", "ধৈর্য (সবর)", "রহমত", "বিশ্বাসী মন", "অফুরন্ত দয়া", "নীরব দোয়া", "পথপ্রাপ্ত আত্মা", "আলহামদুলিল্লাহ মুহূর্ত"],
            "banglish": ["Allah r plan", "sabr", "blessing", "faithful heart", "endless mercy", "silent dua", "guided soul", "Alhamdulillah"]
        },
        "actions": {
            "english": ["finding ultimate peace in", "trusting completely on", "growing closer to faith through", "accepting destiny with", "seeking mercy via"],
            "bangla": ["পরম শান্তি পাচ্ছি", "সম্পূর্ণ ভরসা রাখছি", "ঈমানের কাছে যাচ্ছি", "তাকদির মেনে নিচ্ছি", "দয়া চাচ্ছি"],
            "banglish": ["ultimate shanti pacchi", "vorosa rakhchi", "iman barachi", "takdir accept korchi", "doya chacchi"]
        },
        "hashtags": ["#Islamic", "#Allah", "#Quran", "#Dua", "#Alhamdulillah", "#Sabr", "#Faith", "#Jannah"]
    },
    "motivation": {
        "label": "🔥 Motivation & Gym",
        "subjects": {
            "english": ["pure hustle", "heavy iron", "unbreakable grind", "endless sweat", "beast mode", "silent dedication", "focused mind", "limitless power"],
            "bangla": ["কঠোর পরিশ্রম", "ভারী লোহা", "অদম্য চেষ্টা", "অফুরন্ত ঘাম", "বিস্ট মোড", "নীরব ডেডিকেশন", "ফোকাসড মন", "অসীম শক্তি"],
            "banglish": ["pure hustle", "heavy iron", "grind", "endless sweat", "beast mode", "silent dedication", "focused mind", "power"]
        },
        "actions": {
            "english": ["crushing limits with", "building a legacy via", "pushing boundaries through", "dominating the workout with", "transforming pain into"],
            "bangla": ["সীমা ভেঙে দিচ্ছি", "লিগেসি গড়ছি", "বাধা অতিক্রম করছি", "ওয়ার্কআউট ডোমিনেট করছি", "কষ্টকে রূপান্তর করছি"],
            "banglish": ["limit break korchi", "legacy banacchi", "baba cross korchi", "workout dominate korchi", "pain transform korchi"]
        },
        "hashtags": ["#Motivation", "#GymLife", "#Fitness", "#Hustle", "#HardWork", "#BeastMode", "#FitnessGoals", "#Grind"]
    },
    "sad": {
        "label": "😢 Sad Caption",
        "content": {
            "english": [
                "Some wounds never truly heal, they just teach us how to hide the pain.",
                "Smiling on the outside while a storm rages quietly inside.",
                "Silent tears always speak the loudest truths of a broken heart.",
                "It hurts when the best memories turn into the heaviest memories.",
                "Not every broken soul shows visible scars on the outside.",
                "Disconnecting from the world to let the heavy feelings settle down.",
                "Carrying the deepest scars behind the quietest personality.",
                "The hardest thing is letting go of someone who meant everything."
            ],
            "bangla": [
                "কিছু ক্ষত কখনো শুকায় না, শুধু লুকিয়ে রাখতে শেখায়।",
                "বাইরে হাসি আর ভেতরে নীরব ঝড় বয়ে যায়।",
                "নীরব অশ্রু সবসময় ভাঙা হৃদয়ের সবচেয়ে বড় সত্য বলে দেয়।",
                "সেরা স্মৃতিগুলো যখন সবচেয়ে ভারী স্মৃতির বোঝা হয়ে দাঁড়ায় তখন কষ্ট হয়।",
                "সব ভাঙা মনের ক্ষত চোখে দেখা যায় না।",
                "ভারী অনুভূতিগুলো শান্ত করতে পৃথিবী থেকে একটু দূরে সরে থাকা।",
                "সবচেয়ে শান্ত স্বভাবের মানুষটাই সবচেয়ে গভীর কষ্ট বয়ে বেড়ায়।",
                "সবচেয়ে কাছের মানুষকে ছেড়ে দেওয়াটাই সবচেয়ে কঠিন।"
            ],
            "banglish": [
                "Kisu khoto kokhono sukabe na, shudhu lukate shikhay.",
                "Baire hasi kintu vetore vanga jhor.",
                "Nirob osru shobcheye boro sotti bole.",
                "Best memory jokhon heavy memory hoye jay.",
                "Sob vanga moner khoto baire dekha jay na.",
                "Heavy feelings shanto korte dunya theke dure.",
                "Deepest pain gulo niyei silent thaka.",
                "Sobcheye dear manushke chere dewa tough."
            ]
        },
        "hashtags": ["#Sad", "#Heartbroken", "#Alone", "#Pain", "#DeepThoughts", "#Lonely", "#Broken", "#Tears"]
    },
    "funny": {
        "label": "😂 Funny Caption",
        "content": {
            "english": [
                "I need a 6-month vacation, twice a year to survive this.",
                "Error 404: Motivation not found. Please try again later.",
                "Born to rest, forced to wake up early and work.",
                "My bed and I have a great relationship, but my alarm is jealous.",
                "I put the 'pro' in procrastinate like a absolute champion.",
                "I follow a strict seafood diet: I see food, and I eat it instantly.",
                "Whispering to my WiFi router so it works faster for me.",
                "Life is short, smile while you still have all your teeth."
            ],
            "bangla": [
                "বেঁচে থাকার জন্য আমার বছরে দুবার ৬ মাসের ছুটি দরকার।",
                "এরর ৪০৪: কোনো মোটিভেশন পাওয়া যায়নি। পরে আবার চেষ্টা করুন।",
                "বিশ্রামের জন্য জন্ম, ভোরে উঠে কাজ করার জন্য নয়।",
                "আমার বিছানা আর আমার প্রেম গাঢ়, শুধু অ্যালার্ম ঘড়িটা হিংসা করে।",
                "প্রোক্রাস্টিনেশনে আমি একদম প্রো-লেভেলের চ্যাম্পিয়ন।",
                "আমি কড়া ডায়েট ফলো করি: খাবার দেখি আর খেয়ে ফেলি।",
                "ওয়াইফাই রাউটারের সাথে ফিসফিস করি যেন ও একটু দ্রুত চলে।",
                "জীবন খুব ছোট, যতদিন দাঁত আছে প্রাণ খুলে হাসুন।"
            ],
            "banglish": [
                "Bochore du bar 6 maser holiday lagbe bachar jonno.",
                "Error 404: Motivation not found. pore try koro.",
                "Born to rest, forced to wake up early.",
                "Bed r amar relation strong, alarm jealous.",
                "Procrastination e ami ekta pro champion.",
                "Seafood diet follow kori: khabar dekhi r khai.",
                "WiFi router ke request kori fast kaj korar jonno.",
                "Jibon choto, dat thakte haste thako."
            ]
        },
        "hashtags": ["#Funny", "#Humor", "#Laugh", "#Relatable", "#Vibes", "#Joke", "#Meme", "#Lazy"]
    },
    "attitude": {
        "label": "😎 Attitude Caption",
        "content": {
            "english": ["I don't chase anything, I attract what belongs to me.", "My attitude is purely a reflection of how you treat me.", "Unmatched energy, zero tolerance for fake vibes.", "I am who I am; your approval was never requested."],
            "bangla": ["আমি কোনো কিছুর পেছনে ধাওয়া করি না, যা আমার প্রাপ্য তা আকর্ষণ করি।", "আপনার আচরণের ওপর আমার অ্যাটিটিউড নির্ভর করে।", "অনন্য এনার্জি, ফেক মানুষের জন্য জিরো টলারেন্স।", "আমি যেমন তেমনই; আপনার অনুমোদনের কোনো প্রয়োজন নেই।"],
            "banglish": ["Ami chase kori na, attract kori.", "Attitude depend kore apnar behavior er upor.", "Unmatched energy, zero tolerance for fake.", "Ami jemon temon, approval dorkar nei."]
        },
        "hashtags": ["#Attitude", "#Savage", "#King", "#Confidence", "#Fearless", "#Boss", "#Alpha", "#Ego"]
    },
    "travel": {
        "label": "✈️ Travel & Nature",
        "content": {
            "english": ["Collecting moments, breathtaking views, and endless memories.", "Born to roam free, the entire world is my permanent home.", "Escaping the ordinary to find peace deep in nature."],
            "bangla": ["সুন্দর মুহূর্ত, অসাধারণ ভিউ আর অফুরন্ত স্মৃতি জমিয়ে রাখছি।", "স্বাধীনভাবে ঘুরে বেড়ানোর জন্ম, এই পৃথিবীই আমার আসল ঘর।", "প্রকৃতির মাঝে শান্তি খুঁজতে সাধারণ রুটিন থেকে একটু পালিয়ে যাওয়া।"],
            "banglish": ["Moment collect korchi, awesome view r memory.", "Gure beranor jonmo, dunya amar home.", "Escape ordinary life and enjoy nature."]
        },
        "hashtags": ["#Travel", "#Nature", "#Wanderlust", "#Explorer", "#Adventure", "#Trip", "#Views", "#Escape"]
    },
    "couple": {
        "label": "❤️ Couple & Love",
        "content": {
            "english": ["My absolute favorite person in this entire universe.", "You plus me equals a forever kind of love story.", "Home is wherever I am holding your safe hands."],
            "bangla": ["পুরো মহাবিশ্বের মধ্যে আমার সবচেয়ে পছন্দের মানুষটি তুমি।", "তুমি আর আমি মিলে আমাদের প্রেমের গল্পটি চিরকালের।", "তোমার নিরাপদ হাত দুটো ধরে থাকাই আমার আসল ঘর।"],
            "banglish": ["Universe er maje my favorite person tumi.", "You + me = forever love story.", "Home is where I hold your hands."]
        },
        "hashtags": ["#CoupleGoals", "#Love", "#Soulmate", "#Forever", "#TrueLove", "#Partner", "#Romance", "#Us"]
    }
}

def generate_ai_captions(cat_key: str, lang: str, page: int = 1) -> List[str]:
    cat_data = AI_VOCAB.get(cat_key, AI_VOCAB["aesthetic"])
    generated = []
    
    # If the category has pre-built rich content (like Sad, Funny)
    if "content" in cat_data:
        pool = cat_data["content"].get(lang, cat_data["content"]["english"])
        random.seed(hash(cat_key + lang) + page)
        shuffled = list(pool)
        random.shuffle(shuffled)
        for i in range(12):
            text = shuffled[i % len(shuffled)]
            if page > 1:
                text = f"{text} ✨"
            tags = " ".join(random.sample(cat_data["hashtags"], k=4))
            generated.append(html.escape(f"{text}\n\n{tags}"))
        return generated

    # For other categories, dynamically combine AI vocabularies for infinite unique variations
    subjects = cat_data["subjects"].get(lang, cat_data["subjects"]["english"])
    actions = cat_data["actions"].get(lang, cat_data["actions"]["english"])
    
    random.seed(hash(cat_key + lang) + page)
    
    for i in range(12):
        subj = random.choice(subjects)
        act = random.choice(actions)
        
        if lang == "bangla":
            text = f"জীবন মানেই {subj}, যেখানে আমরা {act} এগিয়ে যাচ্ছি। (v{page})"
        elif lang == "banglish":
            text = f"Always focused on {subj}, while {act} with pure passion! [Page {page}]"
        else:
            text = f"Embracing the power of {subj} while {act} every single day. (Edition {page})"
            
        tags = " ".join(random.sample(cat_data["hashtags"], k=4))
        generated.append(html.escape(f"{text}\n\n{tags}"))
        
    return generated

# =====================================================================
# 4. BOT HANDLERS (Clean English Interface, Multi-Language Generator)
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        name = update.effective_user.first_name if update.effective_user else "Friend"
        set_user_state(user_id, category="aesthetic", language="english")
        
        welcome_text = (
            f"✨ <b>Welcome {html.escape(name)} to AI Caption Bot!</b> ✨\n\n"
            "I can generate unlimited AI-powered captions in English, Bangla, and Banglish for your posts.\n\n"
            "👇 <b>Please select an option below:</b>"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✍️ Generate Captions", callback_data="make_caption")],
            [InlineKeyboardButton("⭐ Saved Captions", callback_data="show_saved")]
        ])
        
        if update.message:
            await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        elif update.callback_query:
            await update.callback_query.message.edit_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception as e:
        logger.exception("Error in start handler: %s", e)

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
                "🌐 <b>Please select your target caption language:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            
        elif data.startswith("lang_"):
            lang = data.split("_")[1]
            set_user_state(user_id, language=lang)
            
            keys = list(AI_VOCAB.keys())
            kb_buttons = []
            for i in range(0, len(keys), 2):
                row = [InlineKeyboardButton(AI_VOCAB[keys[i]]["label"], callback_data=f"cat_{keys[i]}")]
                if i + 1 < len(keys):
                    row.append(InlineKeyboardButton(AI_VOCAB[keys[i+1]]["label"], callback_data=f"cat_{keys[i+1]}"))
                kb_buttons.append(row)
                
            kb_buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
            kb = InlineKeyboardMarkup(kb_buttons)
            
            await query.message.edit_text(
                f"✅ <b>Language Set:</b> {lang.capitalize()}\n\n👇 <b>Now choose a category:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            
        elif data.startswith("cat_"):
            cat_key = data.split("_")[1]
            set_user_state(user_id, category=cat_key)
            
            st = get_user_state(user_id)
            lang = st["language"]
            
            captions = generate_ai_captions(cat_key, lang, page=1)
            cat_label = AI_VOCAB[cat_key]["label"]
            
            header = f"🤖 <b>AI Category:</b> {cat_label}\n🌐 <b>Language:</b> {lang.capitalize()}\n📄 <b>Page:</b> 1 (Unlimited AI Generation)\n\n👇 <b>Click any caption text to copy:</b>"
            list_text = header + "\n\n" + "\n\n-------------------\n\n".join([f"<b>{idx+1}.</b> <code>{c}</code>" for idx, c in enumerate(captions)])
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Generate More 🔄 (Next Page)", callback_data=f"page|{cat_key}|2")],
                [InlineKeyboardButton("🔄 Change Category", callback_data="lang_" + lang), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ])
            
            await query.message.edit_text(list_text, parse_mode=ParseMode.HTML, reply_markup=kb)
            
        elif data.startswith("page|"):
            parts = data.split("|")
            cat_key = parts[1]
            page_num = int(parts[2])
            
            st = get_user_state(user_id)
            lang = st["language"]
            
            captions = generate_ai_captions(cat_key, lang, page=page_num)
            cat_label = AI_VOCAB[cat_key]["label"]
            
            next_page = page_num + 1
            
            header = f"🤖 <b>AI Category:</b> {cat_label}\n🌐 <b>Language:</b> {lang.capitalize()}\n📄 <b>Page:</b> {page_num} (Unlimited AI Generation)\n\n👇 <b>Click any caption text to copy:</b>"
            list_text = header + "\n\n" + "\n\n-------------------\n\n".join([f"<b>{idx+1}.</b> <code>{c}</code>" for idx, c in enumerate(captions)])
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Generate More 🔄 (Next Page)", callback_data=f"page|{cat_key}|{next_page}")],
                [InlineKeyboardButton("🔄 Change Category", callback_data="lang_" + lang), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ])
            await query.message.edit_text(list_text, parse_mode=ParseMode.HTML, reply_markup=kb)
            
        elif data == "show_saved":
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
            await query.message.edit_text("⭐ <b>Saved Captions feature is coming soon!</b>", parse_mode=ParseMode.HTML, reply_markup=kb)
            
    except Exception as e:
        logger.exception("Callback error: %s", e)

# =====================================================================
# 5. MAIN FUNCTION
# =====================================================================
def main():
    Thread(target=run_server, daemon=True).start()
    
    token = os.getenv("BOT_TOKEN1")
    if not token:
        logger.error("No BOT_TOKEN1 found in environment variables!")
        return

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("AI Caption Maker Bot is running successfully!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
