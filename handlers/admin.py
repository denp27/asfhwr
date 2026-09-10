import datetime
import random
import string
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_db_connection
from config import ADMIN_IDS
from services.duckzmail import create_duckzmail_account
from services.real_automation import execute_real_tiktok_warmup

router = Router()

class AutoregStage(StatesGroup):
    geo = State()
    warm = State()
    price = State()

class WarmupState(StatesGroup):
    keywords = State()

def calculate_age(date_str):
    if not date_str: return 0
    try:
        return max(0, (datetime.datetime.now() - datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")).days)
    except:
        return 0

@router.callback_query(F.data == "admin")
async def cb_admin(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sales_count, total_earned FROM stats")
    stats = cursor.fetchone()
    conn.close()

    text = f"🛠 **Админ-панель**\n\n📊 Продаж: {stats[0]}\n💵 Заработано: {stats[1]}$"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Управление аккаунтами (отлега)", callback_data="admin_accs")],
        [InlineKeyboardButton(text="🤖 Авторег с DuckzMail", callback_data="start_autoreg")],
        [InlineKeyboardButton(text="🔥 Реальный прогрев Playwright", callback_data="start_warmup")],
        [InlineKeyboardButton(text="🔙 На главную", callback_data="back_main")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "admin_accs")
async def cb_admin_accs(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, geo, is_sold, price, date_added FROM products")
    prods = cursor.fetchall()
    conn.close()

    if not prods:
        await callback.message.edit_text("⚠️ Товаров нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]]))
        return
        
    text = "📦 **Список аккаунтов и отлега:**\n\n"
    for p in prods:
        age = calculate_age(p[5])
        status = "🟢 Доступен" if p[3] == 0 else "🔴 Продан"
        text += f"ID: `{p[0]}` | **{p[1]}**\n└ Добавлен: `{p[5]}` | Отлега: **{age} дн.** | 💰 {p[4]}$ | {status}\n\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]]), parse_mode="Markdown")

@router.callback_query(F.data == "start_autoreg")
async def cb_start_autoreg(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    login = "user_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    password = "".join(random.choices(string.ascii_letters + string.digits + "!@#$", k=12))
    await state.update_data(login=login, password=password)
    await callback.message.answer("🌍 Введите ГЕО аккаунта (например: `USA`):", parse_mode="Markdown")
    await state.set_state(AutoregStage.geo)

@router.message(AutoregStage.geo)
async def process_geo(message: Message, state: FSMContext):
    await state.update_data(geo=message.text.upper())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Да", callback_data="w_yes"), InlineKeyboardButton(text="🌱 Нет", callback_data="w_no")]
    ])
    await message.answer("🔥 Аккаунт прогретый?", reply_markup=keyboard)
    await state.set_state(AutoregStage.warm)

@router.callback_query(AutoregStage.warm, F.data.in_({"w_yes", "w_no"}))
async def process_warm(callback: CallbackQuery, state: FSMContext):
    await state.update_data(warm=1 if callback.data == "w_yes" else 0)
    await callback.message.answer("💵 Введите цену в **RUB** (например: `300`):")
    await state.set_state(AutoregStage.price)

@router.message(AutoregStage.price)
async def process_price(message: Message, state: FSMContext):
    try:
        price_rub = float(message.text.replace(",", "."))
    except:
        await message.answer("Введите число:")
        return
        
    data = await state.get_data()
    status = await message.answer("⏳ Создание почты на DuckzMail...")
    
    mail = await create_duckzmail_account()
    if not mail:
        await status.edit_text("❌ Ошибка получения почты с duckzmail.com")
        await state.clear()
        return
        
    acc_str = f"{data['login']}:{data['password']}:{mail['email']}:{mail['password']}"
    price_usd = round(price_rub / 95.0, 2)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    name = f"TikTok {data['geo']} | Отлега: 0 дн. | {'Прогретый' if data['warm'] else 'Свежерег'}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO products (category, name, price, geo, is_warmed, data, date_added) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   ("tiktok", name, price_usd, data['geo'], data['warm'], acc_str, date_str))
    conn.commit()
    conn.close()
    
    await state.clear()
    from handlers.user import main_menu
    await message.answer(f"✅ Аккаунт с почтой `{mail['email']}` добавлен на витрину!", reply_markup=main_menu(message.from_user.id), parse_mode="Markdown")

@router.callback_query(F.data == "start_warmup")
async def cb_start_warmup(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await callback.message.answer("🔥 Введите ключевые слова для прогрева через запятую:")
    await state.set_state(WarmupState.keywords)

@router.message(WarmupState.keywords)
async def process_kw(message: Message, state: FSMContext):
    kw = message.text
    await state.clear()
    status = await message.answer("⏳ Запуск браузерного робота Playwright...")
    success, logs = await execute_real_tiktok_warmup(kw)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В админку", callback_data="admin")]])
    await status.edit_text(f"✅ **Прогрев завершен!**\n\n📜 **Лог:**\n{logs}", reply_markup=keyboard, parse_mode="Markdown")
