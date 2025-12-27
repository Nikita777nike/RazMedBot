# utils/config.py
import os
from typing import Optional
from pydantic import BaseModel, validator
from dotenv import load_dotenv

load_dotenv()

class BotConfig(BaseModel):
    """Конфигурация бота через Pydantic"""
    BOT_TOKEN: str
    ADMIN_ID: int
    MAX_DOCUMENTS: int = 10
    MAX_FILE_SIZE: int = 20 * 1024 * 1024  # 20 MB
    PROVIDER_TOKEN: Optional[str] = None
    PAYMENT_TEST_MODE: bool = True
    TEST_PAYMENT_PRICE: int = 1
    DATABASE_URL: str = "sqlite:///orders.db"
    BACKUP_DIR: str = "../backups"

    # Данные самозанятого
    SELF_EMPLOYED_NAME: str = "Семёнычев Никита Сергеевич"
    SELF_EMPLOYED_INN: str = "164514339030"
    SUPPORT_CHANNEL: str = "https://t.me/ponyatmed"

    # Настройки уточнений
    CLARIFICATION_TIME_LIMIT_HOURS: int = 24

    # Реферальная система
    REFERRER_BONUS_PERCENT: int = 10  # 10% приглашающему
    REFERRED_DISCOUNT_PERCENT: int = 5  # 5% приглашенному

    @validator('BOT_TOKEN')
    def validate_token(cls, v):
        if not v:
            raise ValueError("BOT_TOKEN не может быть пустым")
        return v

# Загрузка конфигурации
config = BotConfig(
    BOT_TOKEN=os.getenv("BOT_TOKEN", ""),
    ADMIN_ID=int(os.getenv("ADMIN_ID", 0)),
    PROVIDER_TOKEN=os.getenv("PROVIDER_TOKEN")
)