import os
import random
import logging
import asyncio
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
    return "Caption Assistant Bot is running 24/7! 🚀"

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
# 3. CATEGORIES & MULTI-LANGUAGE CAPTIONS DATA
# =====================================================================
CATEGORIES = {
    "aesthetic": {
        "label": "✨ Aesthetic Caption",
        "content": {
            "english": [
                "Living my best life in silence.", "Soft colors and quiet moments.", "Pure soul, peaceful mind.",
                "Some moments in life cannot be measured by time, but by how deeply they touch your soul.",
                "Creating a life that feels good on the inside, not just one that looks good on the outside.",
                "In a world full of noise, finding peace in the little details is an art.",
                "Lost in thoughts where the Wi-Fi is weak and the mind is clear.",
                "Chasing sunsets and quiet state of minds.",
                "Letting things flow naturally and accepting whatever comes.",
                "Simplicity is the ultimate sophistication of a peaceful soul."
            ],
            "bangla": [
                "নীরবতায় নিজের সেরা জীবনটা উপভোগ করছি।", "নরম রং আর কিছু শান্ত মুহূর্ত।", "বিশুদ্ধ আত্মা, শান্ত মন।",
                "জীবনের কিছু মুহূর্ত সময় দিয়ে মাপা যায় না, সেগুলো হৃদয়কে গভীরভাবে ছুঁয়ে যায়।",
                "এমন একটা জীবন তৈরি করছি যা ভেতর থেকে সুন্দর লাগে, শুধু বাইরে থেকে নয়।",
                "হাজারো কোলাহলের মাঝেও ছোট ছোট জিনিসে শান্তি খুঁজে পাওয়া একটি শিল্প।",
                "এমন জায়গায় হারিয়ে যেতে ইচ্ছে করে যেখানে নেটওয়ার্ক নেই কিন্তু মন শান্ত আছে।",
                "সূর্যাস্ত আর এক শান্ত মনের সন্ধানে।",
                "সবকিছু স্বাভাবিকভাবে হতে দেওয়া এবং যা আসে তা মেনে নেওয়া।",
                "সরলতাই একটি শান্ত আত্মার আসল সৌন্দর্য।"
            ],
            "banglish": [
                "Nirobotay nijer best life enjoy korchi.", "Soft colors r kisu shanto muhurto.", "Pure soul, peaceful mind.",
                "Jiboner kisu muhurto somoy diye mapha jay na, egula hridoyke chheye jay.",
                "Emon ekta jibon toiri korchi ja vetor theke sundor lage.",
                "Noise er maje chuto chuto jinise shanti khuje paoa ekta art.",
                "Emon jaygay hariye jete iccha kore jekhane mon shanto thake.",
                "Sunset r shanto moner khoje.",
                "Sobkichu naturally hote dewa r accept kora.",
                "Saroltay ekta shanto moner asol beauty."
            ]
        },
        "hashtags": ["#Aesthetic", "#Vibes", "#Peaceful", "#Mood", "#Explore", "#Soul"]
    },
    "stylish": {
        "label": "💎 Stylish Caption",
        "content": {
            "english": [
                "Classy is when you have a lot to say but you stay silent.", "Born to stand out, never to fit in.", "Elegance is an attitude.",
                "I don't compete for a spot, I create my own lane. Watch and learn.",
                "Too glam to give a damn, too chic to repeat.",
                "Style is a way to say who you are without having to speak.",
                "Keep your heels, head, and standards high.",
                "Walking like I own the place because confidence is key.",
                "Not arrogant, just aware of my worth.",
                "Turning dreams into plans and visions into reality with style."
            ],
            "bangla": [
                "ক্লাসি হলো সেটাই যখন আপনার অনেক কিছু বলার থাকলেও আপনি চুপ থাকেন।", "সবাইর সাথে মিলে যাওয়ার জন্য নয়, আলাদাভাবে চমকানোর জন্য জন্ম।",
                "সৌন্দর্য হলো একটা মানসিকতা।", "আমি কোনো জায়গার জন্য প্রতিযোগিতা করি না, নিজের রাস্তা নিজেই তৈরি করি।",
                "খুব বেশি পরোয়া করি না, স্টাইলে অনন্য।", "স্টাইল হলো কথা না বলেই নিজেকে প্রকাশ করার মাধ্যম।",
                "আপনার হিল, মাথা এবং মান সবসময় উঁচুতে রাখুন।", "আত্মবিশ্বাসই আসল শক্তি, তাই নিজের মতো চলুন।",
                "অহংকারী নই, নিজের মূল্য সম্পর্কে সচেতন।", "স্টাইলের সাথে স্বপ্নগুলোকে বাস্তবে রূপ দিচ্ছেন।"
            ],
            "banglish": [
                "Classy hoche seta jokhon onek kisu bolar thake kintu chup thaken.",
                "Sobai r sathe milte na, alada bhabe chokate jonmo.",
                "Elegance ekta attitude.", "Competition kori na, nijer lane nije banai.",
                "Too glam to give a damn, too chic to repeat.",
                "Style hocche kotha na bole nijeke express korar way.",
                "Head r standard hamesha uchu rakho.",
                "Confidence is key, tai nijer moto chol.",
                "Arrogant na, nijer worth jani.",
                "Dream ke style er sathe reality te convert korchi."
            ]
        },
        "hashtags": ["#Stylish", "#Classy", "#Elegance", "#Swag", "#BossLife", "#Attitude"]
    },
    "islamic": {
        "label": "🌙 Islamic Caption",
        "content": {
            "english": [
                "Verily, with hardship comes ease.", "Trust Allah's perfect timing.", "Alhamdulillah always for everything.",
                "Do not despair, for Allah is with those who have patience.",
                "Keep your heart pure and intentions sincere for the sake of Allah.",
                "No matter how dark the night is, Allah's light will guide you.",
                "Sabr is a tree with bitter roots but extremely sweet fruits.",
                "Put your trust in Allah and He will handle the rest.",
                "Every second is a new chance to turn back to the Creator.",
                "When you have Allah, you have everything you will ever need."
            ],
            "bangla": [
                "নিঃসন্দেহে কষ্টের সাথেই স্বস্তি রয়েছে।", "আল্লাহর নিখুঁত পরিকল্পনার ওপর ভরসা রাখুন।", "সবকিছুর জন্য সর্বদা আলহামদুলিল্লাহ।",
                "নিরাশ হবেন না, নিশ্চয়ই আল্লাহ ধৈর্যশীলদের সাথে আছেন।", "আল্লাহর সন্তুষ্টির জন্য নিজের অন্তরকে পবিত্র ও সৎ রাখুন।",
                "রাত যত গভীরই হোক না কেন, আল্লাহর আলো আপনাকে পথ দেখাবে।",
                "সবরের গাছটির শেকড় তিতা হলেও এর ফল অত্যন্ত মিষ্টি হয়।",
                "আপনার সব ভরসা আল্লাহর ওপর রাখুন, বাকিটা তিনিই সামলাবেন।",
                "প্রতিটি সেকেন্ডই স্রষ্টার দিকে ফিরে আসার নতুন সুযোগ।",
                "আপনার সাথে যখন আল্লাহ আছেন, তখন আপনার আর কিছুর প্রয়োজন নেই।"
            ],
            "banglish": [
                "Nishondehe koshtor sathe shosti royeche.", "Allah r nikhut timing er opor vorosa rakho.",
                "Sobkichur jonno alhamdulillah.", "Nirash hobe na, Allah dhurjoshiil der sathe achen.",
                "Antor pobitro rakho Allah r waste.", "Raat jotoi ghor hok, Allah r alo path dekhabe.",
                "Sabr er fol khubi mishti hoy.", "Vorosa Allah r opor rakho, baki tini dekhben.",
                "Proti second creator er dike fire ashar sujog.",
                "Jokhon Allah achen sathe, ar kichur dorkar nei."
            ]
        },
        "hashtags": ["#Islamic", "#Allah", "#Quran", "#Dua", "#Alhamdulillah", "#Sabr"]
    },
    "motivation": {
        "label": "🔥 Motivation & Gym",
        "content": {
            "english": [
                "Sweat today, shine tomorrow.", "Be stronger than your excuses.", "Hustle in silence, let success make the noise.",
                "The body achieves what the mind believes.", "Hard work beats talent when talent doesn't work hard.",
                "Push yourself because no one else is going to do it for you.",
                "Your only limit is you.", "Build your body, sharpen your mind, conquer the day.",
                "Pain is temporary, pride is forever.", "Wake up with determination, go to bed with satisfaction."
            ],
            "bangla": [
                "আজ ঘাম ঝরাও, কাল উজ্জ্বল হয়ে ওঠো।", "তোমার অজুহাতগুলোর চেয়েও শক্তিশালী হও।", "নীরবতা দিয়ে পরিশ্রম করো, সফলতা শব্দ করবে।",
                "শরীর সেটাই অর্জন করে যা মন বিশ্বাস করে।", "প্রতিভা যখন পরিশ্রম করে না, তখন পরিশ্রমী প্রতিভা হার মানায়।",
                "নিজেকে ধাক্কা দাও, কারণ অন্য কেউ তোমার হয়ে এটা করবে না।", "তোমার একমাত্র সীমাবদ্ধতা তুমি নিজেই।",
                "শরীর গড়ো, মন ধারালো করো, দিনটি জয় করো।", "কষ্ট সাময়িক, গর্ব চিরকালের।", "দৃঢ়সংকল্প নিয়ে ঘুম থেকে ওঠো, তৃপ্তি নিয়ে ঘুমাতে যাও।"
            ],
            "banglish": [
                "Aj gham jhorao, kal उज्ज्वल hou.", "Ojuhat er cheye strong hou.", "Hustle in silence, success make noise.",
                "Body seta pay ja mon biswas kore.", "Hard work beats talent.", "Nijeke push koro, keu kore dibe na.",
                "Nijer limit nije fix koro.", "Body build koro, mind sharp koro.",
                "Pain temporary, pride forever.", "Determination niye utho, satisfaction niye ghumao."
            ]
        },
        "hashtags": ["#Motivation", "#GymLife", "#Fitness", "#Hustle", "#HardWork", "#BeastMode"]
    },
    "sad": {
        "label": "😢 Sad Caption",
        "content": {
            "english": [
                "Some wounds never truly heal.", "Smiling outside, breaking inside.", "Silent tears speak the loudest.",
                "It hurts when the best memories become the most painful memories.",
                "Not every broken heart shows visible scars.",
                "Sometimes you just need to disconnect from the world and let it out.",
                "The deepest people carry the heaviest scars.",
                "It's hard to forget someone who gave you so much to remember.",
                "Trying to fix a broken soul with fake smiles.",
                "Lonely nights and heavy thoughts."
            ],
            "bangla": [
                "কিছু ক্ষত কখনো পুরোপুরি শুকায় না।", "বাইরে হাসি, ভেতরে ভেঙে যাওয়া।", "নীরব অশ্রু সবচেয়ে জোরে কথা বলে।",
                "সবচেয়ে সুন্দর স্মৃতিগুলো যখন সবচেয়ে বেশি কষ্টের কারণ হয়ে দাঁড়ায়, তখন খুব কষ্ট হয়।",
                "প্রতিটি ভাঙা হৃদয়ের ক্ষত চোখে দেখা যায় না।", "মাঝে মাঝে পৃথিবী থেকে একটু বিচ্ছিন্ন হয়ে একা থাকতে ইচ্ছে করে।",
                "সবচেয়ে গভীর মনের মানুষেরাই সবচেয়ে বেশি কষ্ট বহন করে।", "যাকে ভুলে যাওয়া অসম্ভব, তাকে নিয়ে স্মৃতিগুলো বয়ে চলা কঠিন।",
                "মিথ্যা হাসির আড়ালে একটি ভাঙা মন লুকানোর চেষ্টা।", "অন্ধকার রাত আর ভারী কিছু চিন্তা।"
            ],
            "banglish": [
                "Kisu khoto kokhono sukabe na.", "Baire hasi, vetore ভেঙে jawa.", "Nirob osru sobcheye jore kotha bole.",
                "Sundor smritigula jokhon painful hoye jay.", "Protiti vanga hridoyer khoto dekha jay na.",
                "Majhe majhe dunya theke dure thakte iccha kore.", "Deep manushgula heavy pain carry kore.",
                "Take bhula tough je onek kotha diyechilo.", "Fake smile diye mon lukanor chesta.",
                "Lonely night ar heavy thoughts."
            ]
        },
        "hashtags": ["#Sad", "#Heartbroken", "#Alone", "#Pain", "#DeepThoughts", "#Lonely"]
    },
    "funny": {
        "label": "😂 Funny Caption",
        "content": {
            "english": [
                "I need a 6-month vacation, twice a year.", "Error 404: Bio not found.", "Born to rest, forced to work.",
                "I'm not lazy, I'm on energy-saving mode.", "My bed and I are in a committed relationship, but my alarm clock is jealous.",
                "I put the 'pro' in procrastinate.", "I follow a strict seafood diet: I see food and I eat it.",
                "Common sense is not a gift, it's a punishment because you have to deal with people who don't have it.",
                "I whisper to my WiFi router hoping it works faster.", "Life is short, smile while you still have teeth."
            ],
            "bangla": [
                "আমার বছরে দুবার ৬ মাসের ছুটি দরকার।", "এরর ৪০৪: বায়ো পাওয়া যায়নি।", "বিশ্রামের জন্য জন্ম, কাজের জন্য বাধ্য।",
                "আমি অলস নই, আমি এনার্জি সেভিং মোডে আছি।", "আমার বিছানার সাথে আমার গভীর প্রেম, কিন্তু আমার অ্যালার্ম ঘড়িটা ঈর্ষা করে।",
                "আমি প্রোক্রাস্টিনেশনে একদম প্রফেশনাল।", "আমি কড়া ডায়েট ফলো করি: খাবার দেখি আর খেয়ে ফেলি।",
                "কমন সেন্স কোনো উপহার নয়, এটা একটা শাস্তি কারণ যাদের নাই তাদের সামলাতে হয়।",
                "ওয়াইফাই রাউটারের সাথে ফিসফিস করে কথা বলি যেন ও দ্রুত কাজ করে।",
                "জীবন ছোট, দাঁত থাকতে থাকতে হাসিখুশি থাকুন।"
            ],
            "banglish": [
                "Amar bochore du bar 6 maser holiday lagbe.", "Error 404: Bio not found.", "Born to rest, forced to work.",
                "Alos na, energy saving mode e achi.", "Bed r amar relation deep, kintu alarm jealous.",
                "Procrastination e ami pro.", "Seafood diet follow kori: khabar dekhi r khai.",
                "Common sense kono gift na, shasti.", "WiFi router ke request kori fast kaj korar jonno.",
                "Jibon choto, dat thakte haste thako."
            ]
        },
        "hashtags": ["#Funny", "#Humor", "#Laugh", "#Relatable", "#Vibes", "#Joke"]
    },
    "attitude": {
        "label": "😎 Attitude Caption",
        "content": {
            "english": [
                "I don't chase, I attract.", "My attitude is based on how you treat me.", "Unmatched energy only.",
                "I am who I am, your approval is not required.", "Treat me like a king and I'll treat you like a legend.",
                "Let them talk, my success will answer.", "I don't have an attitude, I have standards.",
                "Born to express, not to impress anyone.", "Fearless mind and an unbothered soul.",
                "If you don't like me, that's your problem, not mine."
            ],
            "bangla": [
                "আমি ধাওয়া করি না, আকর্ষণ করি।", "আপনার আচরণের ওপর নির্ভর করে আমার অ্যাটিটিউড।", "শুধু অসাধারণ এনার্জি পছন্দ করি।",
                "আমি যেমন তেমনই, আপনার অনুমোদনের প্রয়োজন নেই।", "আমার সাথে রাজার মতো আচরণ করুন, আমি লিজেন্ডের মতো দেখাবো।",
                "তাদের কথা বলতে দিন, আমার সফলতা জবাব দেবে।", "আমার কোনো অহংকার নেই, আমার কিছু নিজস্ব স্ট্যান্ডার্ড আছে।",
                "কাউকে ইমপ্রেস করতে নয়, নিজের মতো প্রকাশ করতে জন্ম।", "ভয়হীন মন আর একদম কেয়ারহীন আত্মা।",
                "আপনি যদি আমাকে পছন্দ না করেন, সেটা আমার নয় আপনার সমস্যা।"
            ],
            "banglish": [
                "Ami chase kori na, attract kori.", "Nijer attitude depend kore apnar behavior er upor.",
                "Unmatched energy only.", "Ami jemon temon, apnar approval lagbe na.",
                "King treat korle legend treat paben.", "Tara kotha boluk, success reply dibe.",
                "Attitude na, amar standard ache.", "Kakeo impress korte na, nijer moto thakte jonmo.",
                "Fearless mind r unbothered soul.", "Pochondo na hole apnar problem, amar na."
            ]
        },
        "hashtags": ["#Attitude", "#Savage", "#King", "#Confidence", "#Fearless", "#Boss"]
    },
    "travel": {
        "label": "✈️ Travel & Nature",
        "content": {
            "english": [
                "Collect moments, not things.", "Born to roam, the world is my home.", "Escape the ordinary.",
                "To travel is to live, and nature has the best therapy.", "The view is always worth the climb.",
                "Let's find some beautiful places to get lost.", "Adventure awaits, go find it.",
                "Nature is not a place to visit, it is home.", "Footsteps on sand, breeze in the hair.",
                "Traveling – it leaves you speechless, then turns you into a storyteller."
            ],
            "bangla": [
                "জিনিসপত্র নয়, সুন্দর মুহূর্তগুলো জমা করুন।", "ঘুরে বেড়ানোর জন্ম, পৃথিবী আমার বাড়ি।", "সাধারণ জীবন থেকে একটু পালিয়ে বাঁচুন।",
                "ভ্রমণ মানেই বেঁচে থাকা, আর প্রকৃতির কাছে রয়েছে সেরা থেরাপি।", "পাহাড় চড়ার কষ্ট শেষে ভিউ সবসময় অসাধারণ হয়।",
                "চলুন এমন কিছু সুন্দর জায়গায় হারিয়ে যাই।", "অ্যাডভেঞ্চার অপেক্ষা করছে, খুঁজে নিন।",
                "প্রকৃতি বেড়ানোর জায়গা নয়, এটি আমাদের আসল ঘর।", "বালুর ওপর পায়ের ছাপ, চুলে বইছে শীতল বাতাস।",
                "ভ্রমণ আপনাকে প্রথমে বাকরুদ্ধ করে, তারপর গল্পকার বানিয়ে দেয়।"
            ],
            "banglish": [
                "Jinispotro na, muhurto jomo koro.", "Gure beranor jonmo, dunya amar home.",
                "Escape the ordinary.", "Travel manei life, nature best therapy.",
                "View সবসময় worth thake.", "Cholo kothao hariye jai.",
                "Adventure wait korche.", "Nature kono place na, home.",
                "Footsteps on sand, breeze in hair.", "Travel leave you speechless then storyteller."
            ]
        },
        "hashtags": ["#Travel", "#Nature", "#Wanderlust", "#Explorer", "#Adventure", "#Trip"]
    },
    "couple": {
        "label": "❤️ Couple & Love",
        "content": {
            "english": [
                "My favorite person in the entire world.", "You + Me = Forever.", "Home is wherever you are.",
                "Every love story is beautiful, but ours is my favorite.", "You are my today and all of my tomorrows.",
                "Holding your hand is my safest place on earth.", "My heart beats in rhythm with yours.",
                "Luckiest person to have you by my side.", "Side by side, heart to heart.",
                "Forever is a long time, but I wouldn't mind spending it with you."
            ],
            "bangla": [
                "পুরো পৃথিবীর মধ্যে আমার সবচেয়ে পছন্দের মানুষটি তুমি।", "তুমি + আমি = চিরকাল।", "তুমি যেখানেই থাকো না কেন, সেটাই আমার বাড়ি।",
                "সব প্রেমের গল্পই সুন্দর, তবে আমাদেরটা আমার সবচেয়ে প্রিয়।", "তুমি আমার আজকের দিন এবং আমার সব আগামীকাল।",
                "তোমার হাত ধরে থাকা পৃথিবীর সবচেয়ে নিরাপদ জায়গা।", "আমার হৃদয় তোমার হৃদয়ের সাথে তাল মিলিয়ে স্পন্দিত হয়।",
                "তোমাকে পাশে পেয়ে আমি পৃথিবীর সবচেয়ে ভাগ্যবান।", "পাশাপাশি, হৃদয়ে হৃদয়ে।",
                "চিরকাল অনেক লম্বা সময়, তবুও তোমার সাথে তা কাটাতে আমার একটুও আপত্তি নেই।"
            ],
            "banglish": [
                "Puro duniar maje amar favorite person tumi.", "You + Me = Forever.", "Home jekhane tumi aco.",
                "Sob love story sundor, kintu amader ta best.", "Tumi amar aj r sob tomorrows.",
                "Tomar hath dhore thaka safe place.", "Heartbeat match kore tomar sathe.",
                "Luckiest person tumake peye.", "Side by side, heart to heart.",
                "Forever onek lamba, tobu tomar sathe katate raji."
            ]
        },
        "hashtags": ["#CoupleGoals", "#Love", "#Soulmate", "#Forever", "#TrueLove", "#Partner"]
    }
}

def generate_batch_captions(cat_key: str, lang: str, page: int = 1) -> List[str]:
    cat_data = CATEGORIES.get(cat_key, CATEGORIES["aesthetic"])
    pool = cat_data["content"].get(lang, cat_data["content"]["english"])
    
    generated = []
    # Unlimited variation generation using seed offset
    random.seed(hash(cat_key + lang) + page)
    shuffled_pool = list(pool)
    random.shuffle(shuffled_pool)
    
    for i in range(15):  # 15 captions per page, click next page for infinite new ones
        base_text = shuffled_pool[i % len(shuffled_pool)]
        if page > 1:
            base_text = f"{base_text} (v{page})"
            
        tags = " ".join(random.sample(cat_data["hashtags"], k=min(4, len(cat_data["hashtags"]))))
        full_text = html.escape(f"{base_text}\n\n{tags}")
        generated.append(full_text)
        
    return generated

# =====================================================================
# 4. BOT HANDLERS
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        name = update.effective_user.first_name if update.effective_user else "Friend"
        set_user_state(user_id, category="aesthetic", language="english")
        
        welcome_text = (
            f"✨ <b>Welcome {html.escape(name)} to Caption Maker Bot!</b> ✨\n\n"
            "I can generate the best Aesthetic, Stylish, Islamic, Motivation, Sad, Funny, Attitude, Travel and Couple captions for you.\n\n"
            "👇 <b>Please select an option below:</b>"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✍️ Make Caption", callback_data="make_caption")],
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
                "🌐 <b>Please select your preferred language:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            
        elif data.startswith("lang_"):
            lang = data.split("_")[1]
            set_user_state(user_id, language=lang)
            
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
                f"✅ <b>Language:</b> {lang.capitalize()}\n\n👇 <b>Please choose a category below:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            
        elif data.startswith("cat_"):
            cat_key = data.split("_")[1]
            set_user_state(user_id, category=cat_key)
            
            st = get_user_state(user_id)
            lang = st["language"]
            
            captions = generate_batch_captions(cat_key, lang, page=1)
            cat_label = CATEGORIES[cat_key]["label"]
            
            header = f"📁 <b>Category:</b> {cat_label}\n🌐 <b>Language:</b> {lang.capitalize()}\n📄 <b>Page:</b> 1 (Unlimited)\n\n👇 <b>Click on any caption text to copy:</b>"
            list_text = header + "\n\n" + "\n\n-------------------\n\n".join([f"<b>{idx+1}.</b> <code>{c}</code>" for idx, c in enumerate(captions)])
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Next Page ➡️", callback_data=f"page|{cat_key}|2")],
                [InlineKeyboardButton("🔄 Change Category", callback_data="lang_" + lang), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ])
            
            db_increment_stats()
            await query.message.edit_text(list_text, parse_mode=ParseMode.HTML, reply_markup=kb)
            
        elif data.startswith("page|"):
            parts = data.split("|")
            cat_key = parts[1]
            page_num = int(parts[2])
            
            st = get_user_state(user_id)
            lang = st["language"]
            
            captions = generate_batch_captions(cat_key, lang, page=page_num)
            cat_label = CATEGORIES[cat_key]["label"]
            
            next_page = page_num + 1  # Infinite pages without limit
            
            header = f"📁 <b>Category:</b> {cat_label}\n🌐 <b>Language:</b> {lang.capitalize()}\n📄 <b>Page:</b> {page_num} (Unlimited)\n\n👇 <b>Click on any caption text to copy:</b>"
            list_text = header + "\n\n" + "\n\n-------------------\n\n".join([f"<b>{idx+1}.</b> <code>{c}</code>" for idx, c in enumerate(captions)])
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Next Page ➡️", callback_data=f"page|{cat_key}|{next_page}")],
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

    logger.info("Caption Maker Bot is running successfully!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
