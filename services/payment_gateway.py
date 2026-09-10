import httpx
from aiocryptopay import AioCryptoPay, Networks
from config import PLATEGA_MERCHANT_ID, PLATEGA_SECRET_KEY, CRYPTO_BOT_TOKEN

crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

# --- Platega.io (Карты / СБП) ---
async def create_platega_invoice(amount_rub: float, user_id: int):
    url = "https://api.platega.io/v1/invoice/create"
    headers = {
        "Merchant": PLATEGA_MERCHANT_ID,
        "Secret": PLATEGA_SECRET_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "amount": amount_rub,
        "currency": "RUB",
        "metadata": {"user_id": user_id}
    }
    async with httpx.AsyncClient() as session:
        try:
            resp = await session.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("pay_url"), data.get("id")
        except Exception as e:
            print(f"Platega error: {e}")
    return None, None

async def check_platega_payment(invoice_id: str) -> bool:
    url = f"https://api.platega.io/v1/invoice/{invoice_id}"
    headers = {"Merchant": PLATEGA_MERCHANT_ID, "Secret": PLATEGA_SECRET_KEY}
    async with httpx.AsyncClient() as session:
        try:
            resp = await session.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status", "").lower() in ["confirmed", "paid", "success", "succeeded"]:
                    return True
        except Exception:
            pass
    return False

# --- CryptoBot (USDT) ---
async def create_cryptobot_invoice(amount_usd: float, user_id: int):
    try:
        invoice = await crypto.create_invoice(
            asset='USDT',
            amount=amount_usd,
            description=f"Пополнение баланса ID: {user_id}",
            payload=str(user_id)
        )
        return invoice.pay_url, invoice.invoice_id
    except Exception as e:
        print(f"CryptoBot error: {e}")
        return None, None

async def check_cryptobot_invoice(invoice_id: int) -> bool:
    try:
        invoices = await crypto.get_invoices(invoice_ids=[invoice_id])
        if invoices and invoices[0].status == 'paid':
            return True
    except Exception:
        pass
    return False
