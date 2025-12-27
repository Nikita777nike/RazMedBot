# utils/logger.py
import logging
import os
from pathlib import Path
from datetime import datetime


def setup_logger():
    """Настройка логгера для всего проекта"""

    # Создаем директорию для логов рядом с проектом
    project_root = Path(__file__).parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    # Имя файла с датой
    log_file = log_dir / f"bot_{datetime.now().strftime('%Y%m%d')}.log"

    # Настройка основного логгера
    logger = logging.getLogger("medical_bot")
    logger.setLevel(logging.INFO)

    # Форматтер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Добавляем обработчики
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# Глобальный логгер
logger = setup_logger()