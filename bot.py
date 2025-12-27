# bot.py
import asyncio
import logging
import os
from pathlib import Path
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from utils.config import config

# Создаем директорию для логов
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Инициализация базы данных
from database.database import Database

db = Database()

# Инициализация бота
storage = MemoryStorage()
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=storage)

# Экспортируемые переменные
__all__ = ['bot', 'logger', 'dp', 'db']


# Глобальный обработчик ошибок
@dp.error()
async def global_error_handler(event):
    logger.error(f"Global error: {event.exception}", exc_info=True)
    return True


async def main():
    """Главная функция запуска бота"""
    logger.info("Бот запускается...")

    # Импортируем все хендлеры
    from handlers import user_handlers, payment_handlers, common_handlers
    from admin import admin_handlers

    # Регистрация всех хендлеров
    dp.include_router(common_handlers.router)
    dp.include_router(user_handlers.router)
    dp.include_router(payment_handlers.router)
    dp.include_router(admin_handlers.router)

    logger.info("Бот запущен и готов к работе!")

    # Запуск бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())