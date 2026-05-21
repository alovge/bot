import asyncio
import re
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker
)

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    select
)

# =========================
# CONFIG
# =========================

BOT_TOKEN = "8647073525:AAH5H9-7-iVpxqVtvssR0bmW7Gj1Tq0ZGyg"

GROUP_CITY = {
    -1001111111111: "Москва",
    -1002222222222: "Рига"
}

ADMIN_IDS = [123456789]

# =========================
# INIT
# =========================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

if not os.path.exists("databases"):
    os.makedirs("databases")

# =========================
# DATABASE
# =========================

engines = {}
sessions = {}

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    fio = Column(String)

    city = Column(String)

    active = Column(Boolean, default=True)

    bike_received = Column(String)
    bike_returned = Column(String)
    tech_service = Column(String)

    checked = Column(Boolean, default=False)
    checked_date = Column(String)

def get_db(city: str):

    if city not in engines:

        engine = create_async_engine(
            f"sqlite+aiosqlite:///databases/{city}.db"
        )

        session = async_sessionmaker(
            engine,
            expire_on_commit=False
        )

        engines[city] = engine
        sessions[city] = session

    return engines[city], sessions[city]

async def create_tables(city):

    engine, _ = get_db(city)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# =========================
# STATES
# =========================

class AddCityState(StatesGroup):
    waiting_for_city = State()

# =========================
# PARSER
# =========================

def parse_message(text):

    patterns = {
        "received": r"(.+) получил велосипед",
        "returned": r"(.+) сдал велосипед",
        "delete": r"Удалить (.+)",
        "service": r"(.+) прошел ТО"
    }

    for action, pattern in patterns.items():

        match = re.search(pattern, text)

        if match:

            fio = match.group(1).strip()

            return {
                "action": action,
                "fio": fio,
                "date": datetime.now().strftime("%d.%m.%Y")
            }

    return None

# =========================
# CITIES
# =========================

cities = ["Москва", "Рига"]

# =========================
# KEYBOARDS
# =========================

def cities_keyboard():

    buttons = []

    for city in cities:

        buttons.append([
            InlineKeyboardButton(
                text=city,
                callback_data=f"city_{city}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="➕ Добавить город",
            callback_data="add_city"
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

def city_menu(city):

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="Активные пользователи",
                    callback_data=f"active_{city}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="Пользователи за всё время",
                    callback_data=f"all_{city}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="⬅ Назад",
                    callback_data="back"
                )
            ]
        ]
    )

def back_button(city):

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅ Назад",
                    callback_data=f"city_{city}"
                )
            ]
        ]
    )

def user_button(user_id, checked):

    icon = "✅" if checked else "☑"

    return InlineKeyboardButton(
        text=icon,
        callback_data=f"check_{user_id}"
    )

# =========================
# START
# =========================

@dp.message(CommandStart())
async def start(message: Message):

    await message.answer(
        "Выберите город:",
        reply_markup=cities_keyboard()
    )

# =========================
# BACK
# =========================

@dp.callback_query(F.data == "back")
async def back(callback: CallbackQuery):

    await callback.message.edit_text(
        "Выберите город:",
        reply_markup=cities_keyboard()
    )

# =========================
# ADD CITY
# =========================

@dp.callback_query(F.data == "add_city")
async def add_city(callback: CallbackQuery, state: FSMContext):

    if callback.from_user.id not in ADMIN_IDS:
        return

    await state.set_state(AddCityState.waiting_for_city)

    await callback.message.answer(
        "Введите название города:"
    )

@dp.message(AddCityState.waiting_for_city)
async def save_city(message: Message, state: FSMContext):

    city = message.text.strip()

    if city not in cities:
        cities.append(city)

    await create_tables(city)

    await message.answer(
        f"Город {city} добавлен",
        reply_markup=cities_keyboard()
    )

    await state.clear()

# =========================
# CITY MENU
# =========================

@dp.callback_query(F.data.startswith("city_"))
async def city_selected(callback: CallbackQuery):

    city = callback.data.replace("city_", "")

    await callback.message.edit_text(
        f"Город: {city}",
        reply_markup=city_menu(city)
    )

# =========================
# ACTIVE USERS
# =========================

@dp.callback_query(F.data.startswith("active_"))
async def active_users(callback: CallbackQuery):

    city = callback.data.replace("active_", "")

    _, session = get_db(city)

    async with session() as db:

        result = await db.execute(
            select(User).where(User.active == True)
        )

        users = result.scalars().all()

    text = f"Активные пользователи ({city})\n\n"

    keyboard = []

    for user in users:

        status = "✅" if user.checked else "☑"

        text += (
            f"{status} {user.fio}\n"
        )

        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {user.fio}",
                callback_data=f"check_{city}_{user.id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅ Назад",
            callback_data=f"city_{city}"
        )
    ])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard
        )
    )

# =========================
# ALL USERS
# =========================

@dp.callback_query(F.data.startswith("all_"))
async def all_users(callback: CallbackQuery):

    city = callback.data.replace("all_", "")

    _, session = get_db(city)

    async with session() as db:

        result = await db.execute(
            select(User)
        )

        users = result.scalars().all()

    text = f"Все пользователи ({city})\n\n"

    for user in users:

        text += (
            f"ФИО: {user.fio}\n"
            f"Получил: {user.bike_received}\n"
            f"Сдал: {user.bike_returned}\n"
            f"ТО: {user.tech_service}\n"
            f"Галочка: {'Да' if user.checked else 'Нет'}\n"
            f"Дата галочки: {user.checked_date}\n\n"
        )

    await callback.message.edit_text(
        text,
        reply_markup=back_button(city)
    )

# =========================
# CHECK USER
# =========================

@dp.callback_query(F.data.startswith("check_"))
async def check_user(callback: CallbackQuery):

    data = callback.data.split("_")

    city = data[1]
    user_id = int(data[2])

    _, session = get_db(city)

    async with session() as db:

        result = await db.execute(
            select(User).where(User.id == user_id)
        )

        user = result.scalar()

        if user:

            user.checked = not user.checked

            user.checked_date = datetime.now().strftime("%d.%m.%Y %H:%M")

            await db.commit()

    await callback.answer("Статус обновлен")

# =========================
# GROUP MESSAGE PARSER
# =========================

@dp.message(F.chat.type.in_(["group", "supergroup"]))
async def group_parser(message: Message):

    if message.chat.id not in GROUP_CITY:
        return

    city = GROUP_CITY[message.chat.id]

    parsed = parse_message(message.text)

    if not parsed:
        return

    _, session = get_db(city)

    async with session() as db:

        result = await db.execute(
            select(User).where(User.fio == parsed["fio"])
        )

        user = result.scalar()

        # =====================
        # ПОЛУЧИЛ ВЕЛОСИПЕД
        # =====================

        if parsed["action"] == "received":

            if not user:

                user = User(
                    fio=parsed["fio"],
                    city=city,
                    active=True,
                    bike_received=parsed["date"]
                )

                db.add(user)

            else:

                user.active = True
                user.bike_received = parsed["date"]

            await db.commit()

        # =====================
        # СДАЛ ВЕЛОСИПЕД
        # =====================

        elif parsed["action"] == "returned":

            if user:

                user.active = False
                user.bike_returned = parsed["date"]

                await db.commit()

        # =====================
        # УДАЛЕНИЕ
        # =====================

        elif parsed["action"] == "delete":

            if user:

                await db.delete(user)
                await db.commit()

        # =====================
        # ТО
        # =====================

        elif parsed["action"] == "service":

            if user:

                user.tech_service = parsed["date"]

                await db.commit()

# =========================
# STARTUP
# =========================

async def startup():

    for city in cities:
        await create_tables(city)

# =========================
# MAIN
# =========================

async def main():

    await startup()

    print("BOT STARTED")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
