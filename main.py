import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
import random
import datetime

dp = Dispatcher()

class DB():
    def __init__(self, path, logging=False):
        self.path = path
        self.logging = logging
    async def setup(self):
        self.db = await aiosqlite.connect(self.path)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                name TEXT,
                date TEXT
            )
        """)
        await self.db.commit()

        if self.logging: print("DB: setuped")

    async def push(self, msg):
        await self.db.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)", (
            msg.chat.id,
            msg.from_user.id,
            msg.from_user.username or msg.from_user.full_name,
            msg.from_user.full_name,
            msg.date
        ))
        await self.db.commit()

        if self.logging: print("DB: commited")

    async def get_all(self, msg):
        cursor = await self.db.execute("SELECT * FROM messages WHERE chat_id = ?", (msg.chat.id, ))
        rows = await cursor.fetchall()
        await cursor.close()

        if self.logging: print("DB: get all")

        return rows

    async def get_makan_list(self, msg, start_time_str):
        cursor = await self.db.execute(
            """
            SELECT user_id, username, name, COUNT(*) as cnt
            FROM messages
            WHERE chat_id = ? AND date >= ?
            GROUP BY user_id, username, name
            """,
            (msg.chat.id, start_time_str)
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if self.logging: print("DB: get makan")

        return rows

    async def get_makan(self, msg, target):
        cursor = await self.db.execute(
            """
                SELECT name, date
                FROM messages
                WHERE chat_id = ? AND user_id = ? OR username = ?
            """,
            (msg.chat.id, target.id, target.username) if type(target) != str else (msg.chat.id, None, target)
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if self.logging: print("DB: get makan")

        return rows

# init db
database = DB("stats.db", True)

# assist functions
def parse_period(period: str):
    if not period:
        raise ValueError("Empty period")

    unit = period[-1]
    number_part = period[:-1]

    if not number_part.isdigit():
        raise ValueError("Invalid number in period")

    number = int(number_part)

    if unit == "d":
        return datetime.timedelta(days=number)
    elif unit == "w":
        return datetime.timedelta(weeks=number)
    else:
        raise ValueError("Use format like 7d, 2w")
def resolve_target_user(message: types.Message, command: CommandObject = None):
    if message.reply_to_message:
        return message.reply_to_message.from_user

    # аргументы
    if command and command.args:
        tagged = command.args.split()[0]
        if tagged.startswith('@'):
            return tagged[1:]  # username

    return message.from_user
async def process_makan(message: types.Message, target):
    now = message.date

    hours_ago = now - datetime.timedelta(hours=1)
    day_ago = now - datetime.timedelta(days=1)
    week_ago = now - datetime.timedelta(weeks=1)
    month_ago = now - datetime.timedelta(days=30)

    makan = await database.get_makan(message, target)

    if not makan:
        return await message.reply("❌ Пользователь не найден в базе")

    hour = day = week = month = total = 0

    for _, date_str in makan:
        msg_time = datetime.datetime.fromisoformat(date_str)

        total += 1
        if msg_time >= hours_ago: hour += 1
        if msg_time >= day_ago: day += 1
        if msg_time >= week_ago: week += 1
        if msg_time >= month_ago: month += 1

    full_name = makan[-1][0]

    s = f"""
📊 <i>Статистика {full_name}</i>

📅 За час: {hour}
📅 За день: {day}
📅 За неделю: {week}
📅 За месяц: {month}
📅 Всего: {total}
"""
    await message.reply(s, parse_mode="HTML")
# command handlers
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("""
Привет👋, MacanyeWest -  бот🤖, который подсчитывает кол-во сообщений💬 каждого пользователя в группе.
Разделяет сообщения по День/Неделя/Месяц/Всего📆.

ℹ️ Напиши /help чтобы узнать, что может бот.
""") # 👋 🤖 💬 📆

@dp.message(Command("help"))
async def help_handler(message: types.Message):
    await message.reply("""
💻 Команды для управления:

🔝 /makan_top - показывает список топ 10 пользователей по сообщениям.

📋 /kto_makan <кол-во сообщений> <период> <упомянуть> <процент пощады> - выводит список тех, кто не набрал норму макана.

ℹ️ /makan <@пользователь> - показывает статистику личную/выбранного пользователя.
или "макан"

🙋🏿 я макан - выдаёт тебе строчку из текста макана.

🙅🏿 макан не я - выбирает случайного пользователя из чата и выдаёт ему строчку из текста макана.
""") # 💻 🔝 📋 ℹ️ 🙋🏿 🙅🏿

@dp.message(Command("makan_top"))
async def makan_top(message: types.Message):
    l = await database.get_all(message)

    users = {}
    for _, user_id, username, full_name, date in l:
        if user_id not in users:
            users[user_id] = {
                "username": username,
                "full_name": full_name,
                "messages": []
            }
        users[user_id]["messages"].append(date)

    top = [(v["username"], v["full_name"], len(v["messages"])) for v in users.values()]
    top.sort(key=lambda x: x[2], reverse=True)

    s = ""
    for i, (username, full_name, count) in enumerate(top[:10], 1):
        s += f"{i}. {full_name} — {count}\n"

    await message.reply("🔝Топ-лист:\n" + s)

@dp.message(Command("kto_makan"))
async def kto_makan(message: types.Message, command: CommandObject):
    if not command.args:
        return await message.reply("""
Используй: /kto_makan <норма> <период> "<упомянуть>" "<процент пощады>")
Например: /kto_makan 80 7d да 90
Примечание: параметры в кавычках необязательны, по умолчанию - "нет", "90"
""")

    parts = command.args.split()

    try:
        qt = int(parts[0])
        period = parts[1]
    except (IndexError, ValueError):
        return await message.reply("❌ Неверный формат команды.")
    useTag = parts[2] if len(parts) > 2 else "нет"
    mercyPrc = int(parts[3]) if len(parts) > 3 else 90

    now = message.date
    delta = parse_period(period)
    start_time = now - delta

    makan = await database.get_makan_list(message, start_time.isoformat())
    makan.sort(key=lambda x: x[3], reverse=False)

    not_reached = []

    mercyBorder = qt * mercyPrc / 100
    useTag = True if useTag == "да" else False

    for _, username, full_name, count in makan:
        if count < qt:
            not_reached.append((username, full_name, count))

    s = "📉Меньше нормы:\n"
    for i, (username, full_name, count) in enumerate(not_reached, 1):
        s += f"<u>{i}</u>" if count >= mercyBorder else f"{i}" # is mercy - underlined index
        s += f". {full_name}"
        s += f" (@{username})" if useTag else ""
        s += f" — {count}\n"

    await message.reply(s, parse_mode="HTML")

@dp.message(Command("makan"))
async def makan_handler(message: types.Message, command: CommandObject):
    user = resolve_target_user(message, command)
    await process_makan(message, user)

@dp.message(lambda message: message.text and message.text.lower() == "макан")
async def ty_makan_handler(message: types.Message):
    user = resolve_target_user(message)
    await process_makan(message, user)

makan_texts = open("macan_texts.txt", "r", encoding="UTF-8").readlines()
@dp.message(lambda message: message.text and message.text.lower() == "я макан")
async def ty_makan_handler(message: types.Message):
    stroke = makan_texts[random.randint(0, len(makan_texts) - 1)]
    await message.reply(f"{stroke}<i>© Макан</i>", parse_mode="HTML")

# message logger
@dp.message()
async def logger(message: types.Message):
    await database.push(message)

# main
async def main():
    # bot settings
    TOKEN = open("token.txt", "r", encoding="utf-8").read().strip()
    PROXY = open("proxy.txt", "r", encoding="utf-8").read().strip()

    session = AiohttpSession(proxy=PROXY)
    bot = Bot(token=TOKEN, session=session)

    # setup database
    await database.setup()

    # setup bot
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())