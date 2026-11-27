import asyncio
import json
import logging
import os
import random
from pathlib import Path
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

RAW_TOKEN = os.getenv("BOT_TOKEN", "9260798734:AAFuHjxrirFFqxx8zje_QX4K-fHgPrmYZN0").strip()

if not RAW_TOKEN or "BU_YERGA" in RAW_TOKEN or ":" not in RAW_TOKEN:
    raise ValueError(
        "❌ XATO: BOT_TOKEN kiritilmagan yoki noto'g'ri! "
        "@BotFather dan to'g'ri token olib, BOT_TOKEN ga joylang."
    )

bot = Bot(token=RAW_TOKEN)
dp = Dispatcher()

BASE_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = BASE_DIR / "questions.json"

if not QUESTIONS_PATH.exists():
    raise FileNotFoundError(f"❌ XATO: questions.json topilmadi! Yo'l: {QUESTIONS_PATH}")

with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
    QUESTIONS = json.load(f)

if not isinstance(QUESTIONS, list) or len(QUESTIONS) == 0:
    raise ValueError("❌ XATO: questions.json bo'sh yoki noto'g'ri formatda!")

logging.info(f"✅ {len(QUESTIONS)} ta savol muvaffaqiyatli yuklandi.")

# Savollarni 50 tadan guruhlarga bo'lish
total_q = len(QUESTIONS)
STEP = 50
GROUPS = {}
keyboard_rows = []
row = []

for idx, start in enumerate(range(0, total_q, STEP), start=1):
    end = min(start + STEP, total_q)
    btn_text = f"{idx}️⃣ {idx}-guruh ({start + 1}–{end})"
    GROUPS[btn_text] = (start, end)
    row.append(KeyboardButton(text=btn_text))
    if len(row) == 2:
        keyboard_rows.append(row)
        row = []

if row:
    keyboard_rows.append(row)

all_btn = f"🔥 Barchasi (1–{total_q})"
GROUPS[all_btn] = (0, total_q)
keyboard_rows.append([KeyboardButton(text=all_btn)])

groups_keyboard = ReplyKeyboardMarkup(
    keyboard=keyboard_rows,
    resize_keyboard=True
)

quiz_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Joriy natija"), KeyboardButton(text="⏹ Testni yakunlash")],
        [KeyboardButton(text="🔙 Guruh tanlash")]
    ],
    resize_keyboard=True
)

user_state = {}


@dp.message(Command("start"))
@dp.message(lambda msg: msg.text == "🔙 Guruh tanlash")
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_state.pop(user_id, None)

    await message.answer(
        f"📚 <b>Hayot faoliyati xavfsizligi — Quiz Bot</b>\n\n"
        f"Jami <b>{total_q} ta</b> savol <b>50 tadan</b> guruhlarga bo‘lingan.\n"
        f"Har safar savollar ham, javob variantlari ham aralashtirib beriladi.\n\n"
        f"Boshlash uchun guruhni tanlang:",
        parse_mode="HTML",
        reply_markup=groups_keyboard
    )


@dp.message(lambda msg: msg.text in GROUPS)
async def start_group_quiz(message: types.Message):
    user_id = message.from_user.id
    group_name = message.text
    start_idx, end_idx = GROUPS[group_name]

    selected_questions = [q.copy() for q in QUESTIONS[start_idx:end_idx]]
    random.shuffle(selected_questions)

    user_state[user_id] = {
        "group_name": group_name,
        "questions": selected_questions,
        "index": 0,
        "score": 0,
        "current_correct_id": None
    }

    await message.answer(
        f"✅ Tanlandi: <b>{group_name}</b>\n"
        f"Savollar soni: <b>{len(selected_questions)} ta</b> (aralashtirilgan).\n"
        f"1-savol yuborilmoqda...",
        parse_mode="HTML",
        reply_markup=quiz_keyboard
    )
    await send_question(message.chat.id, user_id)


@dp.message(lambda msg: msg.text == "📊 Joriy natija")
async def show_current_score(message: types.Message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    if not state:
        await message.answer("Hozirda faol test yo‘q. Guruhni tanlang:", reply_markup=groups_keyboard)
        return

    answered = state["index"]
    total = len(state["questions"])
    score = state["score"]
    percent = round((score / answered) * 100, 1) if answered > 0 else 0

    await message.answer(
        f"📊 <b>Joriy natijangiz ({state['group_name']}):</b>\n"
        f"Ishlangan savollar: <b>{answered} / {total}</b>\n"
        f"To‘g‘ri javoblar: <b>{score} ta</b> ({percent}%)",
        parse_mode="HTML"
    )


@dp.message(lambda msg: msg.text == "⏹ Testni yakunlash")
async def stop_quiz(message: types.Message):
    user_id = message.from_user.id
    state = user_state.pop(user_id, None)
    if not state:
        await message.answer("Hozirda faol test yo‘q. Guruhni tanlang:", reply_markup=groups_keyboard)
        return

    answered = state["index"]
    total = len(state["questions"])
    score = state["score"]
    percent = round((score / answered) * 100, 1) if answered > 0 else 0

    await message.answer(
        f"⏹ <b>Test muddatidan oldin yakunlandi!</b>\n\n"
        f"Bo‘lim: <b>{state['group_name']}</b>\n"
        f"Ishlangan savollar: <b>{answered} / {total}</b>\n"
        f"✅ To‘g‘ri javoblar: <b>{score} ta</b> ({percent}%)",
        parse_mode="HTML",
        reply_markup=groups_keyboard
    )


async def send_question(chat_id: int, user_id: int):
    state = user_state.get(user_id)
    if not state:
        return

    idx = state["index"]
    q_list = state["questions"]

    if idx >= len(q_list):
        score = state["score"]
        total = len(q_list)
        group_name = state["group_name"]
        percent = round((score / total) * 100, 1)
        user_state.pop(user_id, None)

        await bot.send_message(
            chat_id,
            f"🎉 <b>{group_name} yakunlandi!</b>\n\n"
            f"✅ Umumiy natija: <b>{score} / {total}</b> ({percent}%)\n\n"
            f"Keyingi guruhni tanlashingiz mumkin:",
            parse_mode="HTML",
            reply_markup=groups_keyboard
        )
        return

    q_item = q_list[idx]
    correct_answer = str(q_item["correct"]).strip()

    raw_options = [str(opt).strip() for opt in q_item["options"]]
    options = list(dict.fromkeys(raw_options))
    if correct_answer not in options:
        options.append(correct_answer)

    options = [opt[:100] for opt in options]
    correct_trimmed = correct_answer[:100]

    options = list(dict.fromkeys(options))
    if correct_trimmed not in options:
        options[0] = correct_trimmed

    random.shuffle(options)

    correct_id = options.index(correct_trimmed)
    state["current_correct_id"] = correct_id

    question_text = f"[{idx + 1}/{len(q_list)}] {q_item['question']}"[:300]

    await bot.send_poll(
        chat_id=chat_id,
        question=question_text,
        options=options,
        type="quiz",
        correct_option_id=correct_id,
        is_anonymous=False
    )


@dp.poll_answer()
async def handle_poll_answer(poll_answer: types.PollAnswer):
    user_id = poll_answer.user.id
    state = user_state.get(user_id)
    if not state:
        return

    chosen_options = poll_answer.option_ids
    if chosen_options and chosen_options[0] == state["current_correct_id"]:
        state["score"] += 1

    state["index"] += 1
    await asyncio.sleep(0.6)
    await send_question(user_id, user_id)


async def health_check(request):
    return web.Response(text="Bot ishlamoqda!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def main():
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
