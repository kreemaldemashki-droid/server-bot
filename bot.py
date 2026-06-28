import os
import re
import asyncio
import sqlite3
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from openai import OpenAI

# ==========================================
# 1. تحميل المتغيرات
# ==========================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER")
MAX_DISCOUNT = float(os.getenv("MAX_DISCOUNT", 0.10))
COMPANY_NAME = os.getenv("COMPANY_NAME", "Target Media")

# ==========================================
# 2. الأسعار (بالدولار)
# ==========================================
BASE_PRICES = {
    "موقع شخصي (احترافي)": 150,
    "موقع شخصي (عادي)": 100,
    "موقع مدرسة إلكترونية": 500,
    "موقع عقارات": 400,
    "موقع متجر إلكتروني": 300,
    "تطبيقات": 150,
    "موقع عيادات": 400,
    "موقع متجر أو بائع جملة": 400,
    "موقع مشفى": 2000,
    "مواقع أخرى": 400,
}

ADDON_PRICES = {
    "هوية مخصصة": 50,
    "AI": 100,
    "موشن جرافيك": 100,
    "شات ذكي": 50,
    "منتدى": 50,
}

DESIGN_PRICES = {"إعلان": 15, "شعار": 20, "كاروسيل": 10}
MEDIA_PRICES = {"ريل": 100, "برومو": 150, "مونتاج على لحن": 50, "فيديو AI (دقيقة)": 35}

# ==========================================
# 3. البوت
# ==========================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==========================================
# 4. DeepSeek
# ==========================================
ai_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1")

def build_system_prompt():
    return f"""
أنت بوت مبيعات وخدمة عملاء لشركة **{COMPANY_NAME}**.

🎯 مهمتك الأساسية:
- فهم احتياجات العميل بدقة.
- حساب السعر بناءً على الأسعار المعلنة بالدولار ($).
- عرض السعر بوضوح ودون مبالغة.

📋 الأسعار الأساسية (بالدولار):
{str(BASE_PRICES)}

➕ الميزات الإضافية (فقط للمواقع):
{str(ADDON_PRICES)}

🎨 التصميم (بالدولار): {str(DESIGN_PRICES)}
🎬 المونتاج (بالدولار): {str(MEDIA_PRICES)}

📦 خطة البيع حسب نوع الخدمة:

**إذا طلب العميل موقعاً (موقع، متجر، عقارات، عيادات، مشفى، مدرسة، إلخ):**
1. احسب السعر الأساسي للموقع.
2. اسأل عن الإضافات واحدة تلو الأخرى (هوية مخصصة، شات ذكي، منتدى، موشن جرافيك، AI).
3. كل إضافة لها سعر محدد.
4. اعرض السعر النهائي (الأساسي + الإضافات).

**إذا طلب العميل خدمة أخرى (تصميم، مونتاج، تصوير، تسويق، ترويج):**
1. احسب السعر حسب الطلب (بدون إضافات).
2. اعرض السعر النهائي مباشرة.
3. **لا تسأل عن إضافات** لأنها غير متوفرة لهذه الخدمات.

💬 التفاوض على السعر:
- **لا تبدأ بالتفاوض أبداً** إلا إذا طلب العميل ذلك.
- إذا قال العميل: "السعر غالي"، "بدي خصم"، "كثير"، "غالية"، "سعر كثير"، "تخفيض"، هنا فقط تبدأ بالتفاوض.
- طريقة التفاوض:
  - ابدأ بتقديم خصم 5%.
  - إذا أصر العميل، قدم 10% كحد أقصى.
  - لا تقدم أكثر من 10% تحت أي ظرف.

📞 واتساب: {WHATSAPP_NUMBER}

🔹 جميع الأسعار بالدولار الأمريكي ($)
🔹 الإضافات متوفرة فقط للمواقع
🔹 لا تسأل عن إضافات لخدمات التصميم أو المونتاج أو التصوير أو التسويق
🔹 لا تتحدث عن الخصم إلا إذا طلب العميل ذلك
🔹 الخصم الأقصى 10%
"""

def ask_deepseek(user_message, history):
    messages = [{"role": "system", "content": build_system_prompt()}] + history + [{"role": "user", "content": user_message}]
    try:
        r = ai_client.chat.completions.create(model="deepseek-chat", messages=messages, temperature=0.7, max_tokens=1500)
        return r.choices[0].message.content
    except Exception as e:
        return f"⚠️ خطأ: {e}"

# ==========================================
# 5. قاعدة البيانات
# ==========================================
def get_conn():
    return sqlite3.connect("target_media_bot.db")

def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                service_type TEXT,
                details TEXT,
                original_price REAL,
                final_price REAL,
                discount REAL,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                role TEXT,
                content TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)
        conn.commit()

def save_client(telegram_id, username, full_name, phone=None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO clients (telegram_id, username, full_name, phone) VALUES (?, ?, ?, ?)", (telegram_id, username, full_name, phone))
        conn.commit()
        return c.lastrowid

def save_conversation(client_id, role, content):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO conversations (client_id, role, content) VALUES (?, ?, ?)", (client_id, role, content))
        conn.commit()

def extract_phone(text):
    m = re.search(r'\b\d{9,15}\b', text)
    return m.group(0) if m else None

# ==========================================
# 6. منطق البوت
# ==========================================
sessions = {}

@dp.message(Command("start"))
async def start_cmd(m: Message):
    await m.answer(
        f"🌟 Welcome to **{COMPANY_NAME}**!\n"
        "Tell me what you need.\n\n"
        f"أهلاً بك في {COMPANY_NAME}!\n"
        "أخبرني ماذا تحتاج؟\n\n"
        "💰 جميع الأسعار بالدولار الأمريكي ($)"
    )

@dp.message()
async def handle(m: Message):
    uid = m.from_user.id
    text = m.text
    username = m.from_user.username or "بدون"
    full_name = m.from_user.full_name

    if uid not in sessions:
        sessions[uid] = []

    reply = ask_deepseek(text, sessions[uid])
    client_id = save_client(uid, username, full_name)
    save_conversation(client_id, "user", text)
    save_conversation(client_id, "assistant", reply)

    sessions[uid].append({"role": "user", "content": text})
    sessions[uid].append({"role": "assistant", "content": reply})

    await m.answer(reply)

    phone = extract_phone(text)
    if phone or "تم استلام" in reply:
        await notify_admin(m, reply, text)

async def notify_admin(m: Message, bot_reply: str, user_text: str):
    try:
        notification = (
            f"📢 New Order - {COMPANY_NAME}!\n"
            f"👤 {m.from_user.full_name}\n"
            f"🆔 @{m.from_user.username or 'بدون'}\n"
            f"📝 {user_text[:200]}\n"
            f"🤖 {bot_reply[:200]}"
        )
        await m.bot.send_message(ADMIN_USERNAME, notification)
        print(f"✅ تم إرسال الإشعار إلى {ADMIN_USERNAME}")
    except Exception as e:
        print(f"⚠️ Error: {e}")

# ==========================================
# 7. تشغيل البوت
# ==========================================
async def main():
    init_db()
    print("=" * 50)
    print(f"🚀 {COMPANY_NAME} Bot is now running...")
    print("💰 All prices are in USD ($)")
    print("📌 Add-ons only for websites")
    print("=" * 50)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())