import asyncio
import json
import logging
import os
import random
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ================= SOZLAMALAR =================
ADMIN_ID = 6792311422  # <-- O'zingizning raqamli Telegram ID'ingizni kiriting
QUESTIONS_FILE = Path("questions.json")
USERS_FILE = Path("users.json")
GROUP_SIZE = 50

RAW_TOKEN = os.getenv("BOT_TOKEN", "9260798734:AAH6ZRChgfmp7gphSKV1i-gp9WwDE3aJXsM").strip().strip('"').strip("'")
if not RAW_TOKEN or ":" not in RAW_TOKEN:
    raise ValueError(
        "❌ XATO: BOT_TOKEN topilmadi yoki noto'g'ri! "
        "Render -> Environment bo'limida BOT_TOKEN ni to'g'ri kiriting."
    )

bot = Bot(token=RAW_TOKEN)
dp = Dispatcher()

# Har bir foydalanuvchi uchun faol test holati:
# user_id -> {"questions": [...], "index": 0, "correct": 0, "group_label": "..."}
active_quizzes: dict[int, dict] = {}


# ================= BAZA VA FOYDALANUVCHILAR =================
def load_questions() -> list[dict]:
    if not QUESTIONS_FILE.exists():
        raise FileNotFoundError(f"{QUESTIONS_FILE} fayli topilmadi!")

    raw = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items = raw.get("questions", [])
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    normalized: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        q_text = (item.get("question") or item.get("text") or "").strip()
        options = item.get("options") or item.get("answers") or []
        correct = item.get("correct_option")
        if correct is None:
            correct = item.get("answer")
        if correct is None:
            correct = item.get("correct")

        if not q_text or not isinstance(options, list) or len(options) < 2:
            continue

        clean_options = [str(opt).strip() for opt in options if str(opt).strip()]
        if len(clean_options) < 2:
            continue

        correct_idx = 0
        if isinstance(correct, int):
            if 0 <= correct < len(clean_options):
                correct_idx = correct
        elif isinstance(correct, str):
            c_clean = correct.strip()
            if c_clean in clean_options:
                correct_idx = clean_options.index(c_clean)
            elif c_clean.isdigit() and 0 <= int(c_clean) < len(clean_options):
                correct_idx = int(c_clean)

        normalized.append(
            {
                "question": q_text,
                "options": clean_options,
                "correct_index": correct_idx,
            }
        )

    logging.info("✅ %d ta savol muvaffaqiyatli yuklandi.", len(normalized))
    return normalized


ALL_QUESTIONS: list[dict] = load_questions()


def load_users() -> dict:
    if USERS_FILE.exists():
        try:
            data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as exc:
            logging.warning("users.json o'qishda xatolik: %s", exc)
    return {}


def save_users(users: dict) -> None:
    USERS_FILE.write_text(
        json.dumps(users, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def track_and_notify(message: types.Message) -> None:
    user = message.from_user
    if not user:
        return

    users = load_users()
    uid = str(user.id)
    is_new = uid not in users

    users[uid] = {
        "id": user.id,
        "full_name": user.full_name,
        "username": user.username or "",
    }
    save_users(users)

    if is_new and ADMIN_ID and user.id != ADMIN_ID:
        username_text = f"@{user.username}" if user.username else "username yo'q"
        try:
            await bot.send_message(
                ADMIN_ID,
                "🆕 <b>Yangi foydalanuvchi!</b>\n"
                f"👤 Ism: {user.full_name}\n"
                f"🔗 Username: {username_text}\n"
                f"🆔 ID: <code>{user.id}</code>\n"
                f"📊 Jami foydalanuvchilar: {len(users)} ta",
                parse_mode="HTML",
            )
        except Exception as exc:
            logging.warning("Adminga xabar yuborilmadi: %s", exc)


# ================= KLAVIATURALAR =================
def build_groups_keyboard(total: int) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    current_row: list[KeyboardButton] = []

    for start in range(1, total + 1, GROUP_SIZE):
        end = min(start + GROUP_SIZE - 1, total)
        btn = KeyboardButton(text=f"📘 {start}–{end}")
        current_row.append(btn)
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    rows.append([KeyboardButton(text=f"📚 Barcha savollar (1–{total})")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def build_options_keyboard(shuffled_options: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for opt in shuffled_options:
        rows.append([KeyboardButton(text=opt)])
    rows.append([KeyboardButton(text="🛑 Testni to'xtatish")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


# ================= TEST MANTIG'I =================
def prepare_shuffled_slice(start_idx: int, end_idx: int) -> list[dict]:
    sliced = ALL_QUESTIONS[start_idx:end_idx]
    picked = random.sample(sliced, len(sliced))

    prepared: list[dict] = []
    for q in picked:
        correct_text = q["options"][q["correct_index"]]
        shuffled_opts = random.sample(q["options"], len(q["options"]))
        new_correct_idx = shuffled_opts.index(correct_text)
        prepared.append(
            {
                "question": q["question"],
                "options": shuffled_opts,
                "correct_index": new_correct_idx,
            }
        )
    return prepared


async def send_current_question(message: types.Message, user_id: int) -> None:
    session = active_quizzes.get(user_id)
    if not session:
        await message.answer(
            "Guruhni tanlang:",
            reply_markup=build_groups_keyboard(len(ALL_QUESTIONS)),
        )
        return

    idx = session["index"]
    questions = session["questions"]

    if idx >= len(questions):
        total_q = len(questions)
        correct_q = session["correct"]
        percent = round((correct_q / total_q) * 100, 1) if total_q else 0.0
        group_label = session["group_label"]
        del active_quizzes[user_id]

        await message.answer(
            f"🏁 <b>Test yakunlandi!</b> ({group_label})\n\n"
            f"✅ To'g'ri javoblar: <b>{correct_q} / {total_q}</b>\n"
            f"📈 Natija: <b>{percent}%</b>\n\n"
            "Yana boshqa guruhni tanlashingiz mumkin:",
            parse_mode="HTML",
            reply_markup=build_groups_keyboard(len(ALL_QUESTIONS)),
        )
        return

    current_q = questions[idx]
    text = (
        f"<b>{session['group_label']}</b> | Savol <b>{idx + 1}/{len(questions)}</b>\n\n"
        f"{current_q['question']}"
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=build_options_keyboard(current_q["options"]),
    )


# ================= BUYRUQLAR VA HANDLERLAR =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    await track_and_notify(message)
    if message.from_user:
        active_quizzes.pop(message.from_user.id, None)

    total = len(ALL_QUESTIONS)
    await message.answer(
        "👋 Assalomu alaykum!\n"
        "<b>Hayot faoliyati xavfsizligi</b> fani bo'yicha test botiga xush kelibsiz.\n\n"
        f"📊 Bazada jami <b>{total} ta</b> savol mavjud.\n"
        "Savollar va javob variantlari har safar tasodifiy tartibda aralashtiriladi.\n"
        "Kerakli guruhni tanlang:",
        parse_mode="HTML",
        reply_markup=build_groups_keyboard(total),
    )


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    users = load_users()
    if not users:
        await message.answer("Hali foydalanuvchilar yo'q.")
        return

    lines = [f"📊 <b>Foydalanuvchilar soni:</b> {len(users)} ta\n"]
    for idx, u in enumerate(users.values(), start=1):
        uname = f"@{u['username']}" if u.get("username") else "username yo'q"
        lines.append(f"{idx}. {u['full_name']} ({uname}) — <code>{u['id']}</code>")

    full_text = "\n".join(lines)
    for i in range(0, len(full_text), 4000):
        await message.answer(full_text[i : i + 4000], parse_mode="HTML")


@dp.message()
async def handle_messages(message: types.Message) -> None:
    if not message.from_user or not message.text:
        return

    user_id = message.from_user.id
    text = message.text.strip()
    total = len(ALL_QUESTIONS)

    if text == "🛑 Testni to'xtatish":
        session = active_quizzes.pop(user_id, None)
        if session:
            await message.answer(
                f"🛑 Test to'xtatildi. To'g'ri javoblar: <b>{session['correct']} / {session['index']}</b>",
                parse_mode="HTML",
                reply_markup=build_groups_keyboard(total),
            )
        else:
            await message.answer(
                "Guruhni tanlang:",
                reply_markup=build_groups_keyboard(total),
            )
        return

    if text.startswith("📚 Barcha savollar"):
        active_quizzes[user_id] = {
            "questions": prepare_shuffled_slice(0, total),
            "index": 0,
            "correct": 0,
            "group_label": f"1–{total}",
        }
        await send_current_question(message, user_id)
        return

    if text.startswith("📘 "):
        range_part = text.replace("📘 ", "", 1).replace("–", "-").strip()
        if "-" in range_part:
            parts = range_part.split("-", 1)
            if parts[0].isdigit() and parts[1].isdigit():
                start_num = int(parts[0])
                end_num = int(parts[1])
                if 1 <= start_num <= end_num <= total:
                    active_quizzes[user_id] = {
                        "questions": prepare_shuffled_slice(start_num - 1, end_num),
                        "index": 0,
                        "correct": 0,
                        "group_label": f"{start_num}–{end_num}",
                    }
                    await send_current_question(message, user_id)
                    return

    session = active_quizzes.get(user_id)
    if session:
        idx = session["index"]
        current_q = session["questions"][idx]
        correct_answer = current_q["options"][current_q["correct_index"]]

        if text not in current_q["options"]:
            await message.answer(
                "Iltimos, quyidagi variantlardan birini tanlang:",
                reply_markup=build_options_keyboard(current_q["options"]),
            )
            return

        if text == correct_answer:
            session["correct"] += 1
            await message.answer("✅ To'g'ri!")
        else:
            await message.answer(
                f"❌ Noto'g'ri.\nTo'g'ri javob: <b>{correct_answer}</b>",
                parse_mode="HTML",
            )

        session["index"] += 1
        await send_current_question(message, user_id)
        return

    await message.answer(
        "Testni boshlash uchun quyidagi guruhlardan birini tanlang:",
        reply_markup=build_groups_keyboard(total),
    )


# ================= RENDER WEB SERVER =================
async def health_handler(request: web.Request) -> web.Response:
    return web.Response(text="Bot is running!")


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_head("/", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info("🌐 Web server %d-portda ishga tushdi.", port)
    return runner


async def main() -> None:
    runner = await start_web_server()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
