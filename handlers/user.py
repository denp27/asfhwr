import datetime
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from database import get_db_connection
from config import ADMIN_IDS
from services.payment_gateway import (
    create_platega_invoice, check_platega_payment,
    create_cryptobot_invoice, check_cryptobot_invoice
)

router = Router()

class TopUpState(StatesGroup):
    amount = State()

def calculate_age(created_timestamp):
    if not created_timestamp: return 0
    return max(0, int((time.time() - created_timestamp) / 86400))

def main_menu(user_id):
    keyboard = [
        [InlineKeyboardButton(text="💎 Купить аккаунты", callback_data="catalog")],
        [InlineKeyboardButton(text="⭐ Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="❓ FAQ", callback_data="faq")]
    ]
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton(text="🛠 Панель управления", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.message(F.text == "/start")
async def cmd_start(message: Message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, balance) VALUES (?, ?, 0.0)",
        (message.from_user.id, message.from_user.username or "NoUsername")
    )
    conn.commit()
    conn.close()
    await message.answer("✨ **Добро пожаловать в магазин аккаунтов!**", reply_markup=main_menu(message.from_user.id), parse_mode="Markdown")

@router.callback_query(F.data == "back_main")
async def cb_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("✨ **Главное меню:**", reply_markup=main_menu(callback.from_user.id), parse_mode="Markdown")

@router.callback_query(F.data == "faq")
async def cb_faq(callback: CallbackQuery):
    text = "❓ **FAQ**\n\n🔹 Выберите категорию в каталоге для покупки.\n🔹 Для пополнения баланса перейдите в профиль."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 На главную", callback_data="back_main")]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance, purchases_count, total_spent FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    balance, purchases, spent = (user[0], user[1], user[2]) if user else (0.0, 0, 0.0)
    text = f"⭐ **Ваш профиль:**\n\n🆔 ID: `{user_id}`\n💰 Баланс: `{balance} RUB`\n🛒 Покупок: `{purchases}`\n💸 Потрачено: `{spent} RUB`"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup_balance")],
        [InlineKeyboardButton(text="🔙 На главную", callback_data="back_main")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "topup_balance")
async def cb_topup(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("💵 Введите сумму пополнения в **рублях (RUB)** (например: `500`):", parse_mode="Markdown")
    await state.set_state(TopUpState.amount)

@router.message(TopUpState.amount)
async def process_topup_amount(message: Message, state: FSMContext):
    try:
        amount_rub = float(message.text.replace(",", "."))
        if amount_rub < 50:
            await message.answer("⚠️ Минимальная сумма: 50 RUB.")
            return
    except ValueError:
        await message.answer("⚠️ Введите корректное число:")
        return
    await state.clear()
    
    amount_usd = round(amount_rub / 95.0, 2)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Банковская карта / СБП (Platega)", callback_data=f"pay_platega_{amount_rub}")],
        [InlineKeyboardButton(text="💎 Криптовалюта (CryptoBot)", callback_data=f"pay_crypto_{amount_usd}_{amount_rub}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")]
    ])
    await message.answer(f"💳 Сумма: **{amount_rub} RUB** (~{amount_usd}$)\nВыберите способ оплаты:", reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("pay_platega_"))
async def cb_pay_platega(callback: CallbackQuery):
    amount_rub = float(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    wait_msg = await callback.message.answer("⏳ Создаем платеж через Platega...")
    pay_url, invoice_id = await create_platega_invoice(amount_rub, user_id)
    if not pay_url:
        await wait_msg.edit_text("❌ Ошибка создания платежа.")
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Оплатить", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_platega_{invoice_id}_{amount_rub}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")]
    ])
    await wait_msg.edit_text(f"🧾 Счет Platega на `{amount_rub} RUB` создан.", reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("check_platega_"))
async def cb_check_platega(callback: CallbackQuery):
    _, _, invoice_id, amount_rub_str = callback.data.split("_")
    amount_rub = float(amount_rub_str)
    if await check_platega_payment(invoice_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount_rub, callback.from_user.id))
        conn.commit()
        conn.close()
        await callback.message.edit_text(f"✅ Баланс пополнен на `+{amount_rub} RUB`!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⭐ В профиль", callback_data="profile")]]))
    else:
        await callback.answer("❌ Платёж еще не поступил.", show_alert=True)

@router.callback_query(F.data.startswith("pay_crypto_"))
async def cb_pay_crypto(callback: CallbackQuery):
    parts = callback.data.split("_")
    amount_usd = float(parts[2])
    amount_rub = float(parts[3])
    user_id = callback.from_user.id
    
    wait_msg = await callback.message.answer("⏳ Создаем инвойс в CryptoBot...")
    pay_url, invoice_id = await create_cryptobot_invoice(amount_usd, user_id)
    if not pay_url:
        await wait_msg.edit_text("❌ Ошибка создания счета CryptoBot.")
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Оплатить USDT", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_crypto_{invoice_id}_{amount_rub}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")]
    ])
    await wait_msg.edit_text(f"💎 Счет CryptoBot на `{amount_usd} USDT` (`{amount_rub} RUB`) создан.", reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("check_crypto_"))
async def cb_check_crypto(callback: CallbackQuery):
    _, _, invoice_id_str, amount_rub_str = callback.data.split("_")
    if await check_cryptobot_invoice(int(invoice_id_str)):
        amount_rub = float(amount_rub_str)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount_rub, callback.from_user.id))
        conn.commit()
        conn.close()
        await callback.message.edit_text(f"✅ Баланс пополнен на `+{amount_rub} RUB`!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⭐ В профиль", callback_data="profile")]]))
    else:
        await callback.answer("❌ Оплата не найдена.", show_alert=True)

# --- Каталог и фильтры при покупке ---

@router.callback_query(F.data == "catalog")
async def cb_catalog(callback: CallbackQuery):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT geo FROM products WHERE is_sold = 0")
    geos = cursor.fetchall()
    conn.close()

    if not geos:
        await callback.message.edit_text("⚠️ В данный момент товары отсутствуют.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]]))
        return
    
    keyboard = []
    for g in geos:
        geo_name = g[0]
        keyboard.append([InlineKeyboardButton(text=f"🌍 ГЕО: {geo_name}", callback_data=f"cat_geo_{geo_name}")])
    keyboard.append([InlineKeyboardButton(text="🌐 Все страны", callback_data="cat_geo_ALL")])
    keyboard.append([InlineKeyboardButton(text="🔙 На главную", callback_data="back_main")])
    
    await callback.message.edit_text("💎 **Выберите страну рега (ГЕО):**", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")

@router.callback_query(F.data.startswith("cat_geo_"))
async def cb_catalog_geo(callback: CallbackQuery):
    geo_filter = callback.data.split("_")[2]
    
    keyboard = [
        [InlineKeyboardButton(text="🔥 Прогретые", callback_data=f"filter_{geo_filter}_warm_1")],
        [InlineKeyboardButton(text="🌱 Свежереги (автореги)", callback_data=f"filter_{geo_filter}_warm_0")],
        [InlineKeyboardButton(text="📦 Все типы", callback_data=f"filter_{geo_filter}_warm_ALL")],
        [InlineKeyboardButton(text="🔙 Назад к странам", callback_data="catalog")]
    ]
    await callback.message.edit_text(f"⚙️ Выберите тип аккаунтов (ГЕО: `{geo_filter}`):", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")

@router.callback_query(F.data.startswith("filter_"))
async def cb_apply_filters(callback: CallbackQuery):
    parts = callback.data.split("_")
    geo_filter = parts[1]
    warm_filter = parts[3]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT id, name, price, is_warmed, created_at FROM products WHERE is_sold = 0"
    params = []
    
    if geo_filter != "ALL":
        query += " AND geo = ?"
        params.append(geo_filter)
    if warm_filter != "ALL":
        query += " AND is_warmed = ?"
        params.append(int(warm_filter))
        
    cursor.execute(query, params)
    prods = cursor.fetchall()
    conn.close()

    if not prods:
        await callback.message.edit_text("⚠️ По вашему фильтру аккаунты не найдены.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К выбору ГЕО", callback_data="catalog")]]))
        return
        
    keyboard = []
    for p in prods:
        prod_id, name, price, is_warmed, created_at = p[0], p[1], p[2], p[3], p[4]
        if is_warmed == 1:
            age = calculate_age(created_at)
            display_name = f"{name} | Отлега: {age} дн. | {price} RUB"
        else:
            display_name = f"{name} | Свежерег | {price} RUB"
            
        keyboard.append([InlineKeyboardButton(text=display_name, callback_data=f"buy_{prod_id}")])
        
    keyboard.append([InlineKeyboardButton(text="🔙 К выбору фильтров", callback_data=f"cat_geo_{geo_filter}")])
    await callback.message.edit_text("📦 **Доступные товары по фильтрам:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")

@router.callback_query(F.data.startswith("buy_"))
async def cb_buy_product(callback: CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT price, data, name FROM products WHERE id = ? AND is_sold = 0", (prod_id,))
    prod = cursor.fetchone()
    
    if not prod:
        conn.close()
        await callback.answer("❌ Товара больше нет в наличии.", show_alert=True)
        return
        
    price, p_data, name = prod[0], prod[1], prod[2]
    
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    balance = user[0] if user else 0.0
    
    if balance < price:
        conn.close()
        await callback.answer("❌ Недостаточно средств на балансе! Пополните профиль.", show_alert=True)
        return
        
    # Списание и выдача товара
    cursor.execute("UPDATE users SET balance = balance - ?, purchases_count = purchases_count + 1, total_spent = total_spent + ? WHERE user_id = ?", (price, price, user_id))
    cursor.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (prod_id,))
    cursor.execute("UPDATE stats SET sales_count = sales_count + 1, total_earned = total_earned + ?", (price,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"✅ **Покупка успешна!**\n\n📦 Товар: *{name}*\n🔑 Данные:\n`{p_data}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 На главную", callback_data="back_main")]]))
