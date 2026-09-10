import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database import db_init
from handlers import user, admin

async def main():
    logging.basicConfig(level=logging.INFO)
    db_init()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(user.router)
    dp.include_router(admin.router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот успешно запущен и работает в реальном режиме!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
