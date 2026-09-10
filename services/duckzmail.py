import aiohttp
import re
import asyncio
import random
import string

BASE_URL = "https://duckzmail.com/api"

async def create_duckzmail_account():
    """Получает реальные верифицированные домены с duckzmail.com и генерирует почту."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/verified-domains") as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            domains = data.get("domains", [])
            if not domains:
                return None
            domain = random.choice(domains)
            
        username = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        email = f"{username}@{domain}"
        return {"email": email, "password": "no_password_needed"}

async def fetch_duckzmail_code(email: str):
    """Реально опрашивает API duckzmail.com и ищет 6-значный код в письмах."""
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}/emails?recipient={email}&limit=10"
        for _ in range(12):  # Ждем до 60 секунд (опрос каждые 5 сек)
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        emails = data.get("emails", [])
                        if emails:
                            latest = emails[0]
                            email_id = latest.get("id") or latest.get("идентификатор")
                            if email_id:
                                body_url = f"{BASE_URL}/emails/{email_id}/body"
                                async with session.get(body_url) as body_resp:
                                    if body_resp.status == 200:
                                        body_data = await body_resp.json()
                                        full_content = (body_data.get("text", "") or "") + " " + (body_data.get("html", "") or "")
                                        code_match = re.search(r'\b\d{6}\b', full_content)
                                        if code_match:
                                            return code_match.group(0), full_content
            except Exception:
                pass
            await asyncio.sleep(5)
    return None, "Письмо с кодом не найдено"
