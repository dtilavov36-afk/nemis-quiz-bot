import asyncio
import json
import logging
import os
import random
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# @BotFather dan olgan tokeningizni shu yerga yozing:
TOKEN = os.getenv("9028333002:AAFW8k7hS1hfsnKKtJ5uSKaJTh204ZFiwDI", "9028333002:AAFW8k7hS1hfsnKKtJ5uSKaJTh204ZFiwDI")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Savollar bazasini yuklash
with open("questions.json", "r", encoding="utf-8") as f:
    QUESTIONS = json.load(f)

# 4 ta guruh chegaralari (indekslar 0 dan boshlanadi)
GROUPS = {
    "1️⃣ 1-guruh (1–50)": (0, 50),
    "2️⃣ 2-guruh (51–100)": (50, 100),
    "3️⃣ 3-guruh (101–150)": (100, 150),
    "4️⃣ 4-guruh (151–201)": (150, len(QUESTIONS)),
    "🔥 Barchasi (1–201)": (0, len(QUESTIONS))
}

# Foydalanuvchilar holati
user_state = {}

# Guruh tanlash menyusi
groups_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="1️⃣ 1-guruh (1–50)"), KeyboardButton(text="2️⃣ 2-guruh (51–100)")],
        [KeyboardButton(text="3️⃣ 3-guruh (101–150)"), KeyboardButton(text="4️⃣ 4-guruh (151–201)")],
        [KeyboardButton(text="🔥 Barchasi (1–201)")]
    ],
    resize_keyboard=True
)

# Test jarayonidagi tugmalar
quiz_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Joriy natija"), KeyboardButton(text="⏹ Testni yakunlash")],
        [KeyboardButton(text="🔙 Guruh tanlash")]
    ],
    resize_keyboard=True
)


@dp.message(Command("start"))
@dp.message(lambda msg: msg.text == "🔙 Guruh tanlash")
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_state:
        del user_state[user_id]

    await message.answer(
        f"🇩🇪 <b>Nemis tili A1 — Quiz Botga xush kelibsiz!</b>\n\n"
        f"Jami savollar <b>4 ta guruhga</b> bo‘lingan.\n"
        f"Testni boshlash uchun quyidagi guruhlardan birini tanlang:",
        parse_mode="HTML",
        reply_markup=groups_keyboard
    )


@dp.message(lambda msg: msg.text in GROUPS)
async def start_group_quiz(message: types.Message):
    user_id = message.from_user.id
    group_name = message.text
    start_idx, end_idx = GROUPS[group_name]

    # Tanlangan guruh savollarini ajratib olish
    selected_questions = QUESTIONS[start_idx:end_idx]

    user_state[user_id] = {
        "group_name": group_name,
        "questions": selected_questions,
        "start_num": start_idx + 1,
        "index": 0,
        "score": 0,
        "current_correct_id": None
    }

    await message.answer(
        f"✅ Tanlandi: <b>{group_name}</b>\n"
        f"Savollar soni: <b>{len(selected_questions)} ta</b>.\n"
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
    state = user_state.get(user_id)
    if not state:
        await message.answer("Hozirda faol test yo‘q. Guruhni tanlang:", reply_markup=groups_keyboard)
        return

    answered = state["index"]
    total = len(state["questions"])
    score = state["score"]
    group_name = state["group_name"]
    percent = round((score / answered) * 100, 1) if answered > 0 else 0
    del user_state[user_id]

    await message.answer(
        f"⏹ <b>Test muddatidan oldin yakunlandi!</b>\n\n"
        f"Bo‘lim: <b>{group_name}</b>\n"
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
        del user_state[user_id]

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
    options = q_item["options"].copy()
    random.shuffle(options)

    correct_id = options.index(q_item["correct"])
    state["current_correct_id"] = correct_id

    # Savolning umumiy bazadagi tartib raqami va guruh ichidagi o'rni
    real_num = state["start_num"] + idx
    question_text = f"[{idx + 1}/{len(q_list)} | №{real_num}] {q_item['question']}"[:300]
    options = [opt[:100] for opt in options]

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
    if user_id not in user_state:
        return

    state = user_state[user_id]
    chosen_options = poll_answer.option_ids

    if chosen_options and chosen_options[0] == state["current_correct_id"]:
        state["score"] += 1

    state["index"] += 1
    await asyncio.sleep(0.8)
    await send_question(user_id, user_id)


# Render uyqu rejimiga o'tmasligi uchun kichik HTTP server
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