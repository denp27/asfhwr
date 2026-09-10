import datetime
import time
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

class AdminUserSearch(StatesGroup):
    user_id = State()

class AdminChangeBalance(StatesGroup):
    amount = State()

def calculate_age(created_timestamp):
    if not created_timestamp: return 0
    return max(0, int((time.time() - created_timestamp) / 86400))

@router.callback_query(F.data == "admin")
async def cb_admin(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await state.clear()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sales_count, total_earned FROM stats")
    stats = cursor.fetchone()
    conn.close()

    text = f"🛠 **Админ-панель**\n\n📊 Продаж: {stats[0]}\n💵 Заработано: {stats[1]} RUB"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Управление аккаунтами", callback_data="admin_accs")],
        [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_users")],
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
    cursor.execute("SELECT id, name, geo, is_sold, price, is_warmed, created_at FROM products")
    prods = cursor.fetchall()
    conn.close()

    if not prods:
        await callback.message.edit_text("⚠️ Товаров нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]]))
        return
        
    text = "📦 **Список аккаунтов:**\n\n"
    for p in prods:
        age = calculate_age(p[6]) if p[5] == 1 else 0
        status = "🟢 Доступен" if p[3] == 0 else "🔴 Продан"
        warm_status = "🔥 Прогретый" if p[5] == 1 else "🌱 Свежерег"
        text += f"ID: `{p[0]}` | ГЕО: **{p[2]}** | {warm_status}\n└ Отлега: `{age} дн.` | 💰 {p[4]} RUB | {status}\n\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]]), parse_mode="Markdown")

# --- Управление пользователями и балансом (в RUB) ---

@router.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await callback.message.answer("🔍 Введите **Telegram ID** пользователя для просмотра и управления балансом:", parse_mode="Markdown")
    await state.set_state(AdminUserSearch.user_id)

@router.message(AdminUserSearch.user_id)
async def process_admin_search_user(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Введите корректный числовой Telegram ID:")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, balance, purchases_count, total_spent FROM users WHERE user_id = ?", (target_id,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        await message.answer(f"❌ Пользователь с ID `{target_id}` не найден в базе данных.", parse_mode="Markdown")
        await state.clear()
        return

    await state.update_data(target_user_id=target_id)
    text = (
        f"👤 **Информация о пользователе:**\n\n"
        f"🆔 ID: `{user[0]}`\n"
        f"👤 Username: @{user[1]}\n"
        f"💰 Баланс: `{user[2]} RUB`\n"
        f"🛒 Всего покупок: `{user[3]}`\n"
        f"💸 Всего потрачено: `{user[4]} RUB`"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Изменить баланс (+/- RUB)", callback_data="admin_edit_balance")],
        [InlineKeyboardButton(text="🔙 В админ-панель", callback_data="admin")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(None)

@router.callback_query(F.data == "admin_edit_balance")
async def cb_admin_edit_balance(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await callback.message.answer(
        "💵 Введите сумму для изменения баланса в **RUB** (рублях):\n"
        "• Для пополнения введите положительное число (например: `500`)\n"
        "• Для списания введите отрицательное число (например: `-200`)",
        parse_mode="Markdown"
    )
    await state.set_state(AdminChangeBalance.amount)

@router.message(AdminChangeBalance.amount)
async def process_admin_change_balance(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        delta = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("⚠️ Введите корректное число:")
        return

    data = await state.get_data()
    target_id = data.get("target_user_id")
    if not target_id:
        await message.answer("❌ Ошибка сессии. Повторите поиск пользователя через админ-панель.")
        await state.clear()
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, target_id))
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (target_id,))
    new_balance = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛠 В админ-панель", callback_data="admin")]
    ])
    await message.answer(f"✅ Баланс пользователя `{target_id}` успешно обновлен!\n💰 Новый баланс: `{new_balance} RUB`", reply_markup=keyboard, parse_mode="Markdown")

# --- Авторег с DuckzMail (с указанием страны и автоматическим определением отлеги) ---

@router.callback_query(F.data == "start_autoreg")
async def cb_start_autoreg(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    login = "user_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    password = "".join(random.choices(string.ascii_letters + string.digits + "!@#$", k=12))
    await state.update_data(login=login, password=password)
    await callback.message.answer("🌍 Введите страну рега (ГЕО) аккаунта (например: `USA`, `RU`, `KAZ`):", parse_mode="Markdown")
    await state.set_state(AutoregStage.geo)

@router.message(AutoregStage.geo)
async def process_geo(message: Message, state: FSMContext):
    await state.update_data(geo=message.text.strip().upper())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Прогретый (с отлегой)", callback_data="w_yes")],
        [InlineKeyboardButton(text="🌱 Свежерег (без отлеги)", callback_data="w_no")]
    ])
    await message.answer("🔥 Какой тип аккаунта создаем?", reply_markup=keyboard)
    await state.set_state(AutoregStage.warm)

@router.callback_query(AutoregStage.warm, F.data.in_({"w_yes", "w_no"}))
async def process_warm(callback: CallbackQuery, state: FSMContext):
    await state.update_data(warm=1 if callback.data == "w_yes" else 0)
    await callback.message.answer("💵 Введите цену в **RUB** (например: `350`):")
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
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created_timestamp = time.time()
    
    warm_type = "Прогретый" if data['warm'] == 1 else "Свежерег"
    name = f"TikTok {data['geo']} | {warm_type}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO products (category, name, price, geo, is_warmed, data, date_added, created_at) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ("tiktok", name, price_rub, data['geo'], data['warm'], acc_str, date_str, created_timestamp))
    conn.commit()
    conn.close()
    
    await state.clear()
    from handlers.user import main_menu
    await message.answer(f"✅ Аккаунт ({data['geo']}, {warm_type}) с почтой `{mail['email']}` добавлен на витрину!", reply_markup=main_menu(message.from_user.id), parse_mode="Markdown")

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
