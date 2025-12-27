# utils/keyboards.py
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


# ========== ФУНКЦИИ ДЛЯ СОЗДАНИЯ КЛАВИАТУР ==========

def create_main_menu() -> ReplyKeyboardMarkup:
    """Создание главного меню"""
    buttons = [
        [KeyboardButton(text="🩺 Создать заказ")],
        [KeyboardButton(text="📋 Мои заказы"), KeyboardButton(text="👨‍⚕️ О сервисе")],
        [KeyboardButton(text="📜 Соглашение"), KeyboardButton(text="👨‍💻 Связаться")],
        [KeyboardButton(text="👥 Пригласить друга")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_service_prices():
    """Возвращает прайс-лист услуг с дополнительной информацией"""
    return {
        # Анализы крови и мочи (нужна демография)
        "Анализы крови/мочи": {"price": 290, "needs_demographics": True, "category": "Анализы"},
        "Биохимия крови": {"price": 290, "needs_demographics": True, "category": "Анализы"},
        "Гормоны": {"price": 290, "needs_demographics": True, "category": "Анализы"},
        "Общий анализ крови": {"price": 290, "needs_demographics": True, "category": "Анализы"},
        "Общий анализ мочи": {"price": 190, "needs_demographics": True, "category": "Анализы"},
        "Липидограмма": {"price": 290, "needs_demographics": True, "category": "Анализы"},
        "Печеночные пробы": {"price": 290, "needs_demographics": True, "category": "Анализы"},
        "Коагулограмма": {"price": 290, "needs_demographics": True, "category": "Анализы"},

        # Инструментальные исследования (не нужна демография)
        "УЗИ": {"price": 390, "needs_demographics": False, "category": "Исследования"},
        "Рентген": {"price": 290, "needs_demographics": False, "category": "Исследования"},
        "МРТ": {"price": 390, "needs_demographics": False, "category": "Исследования"},
        "КТ": {"price": 390, "needs_demographics": False, "category": "Исследования"},
        "ЭКГ": {"price": 390, "needs_demographics": False, "category": "Исследования"},
        "Холтер": {"price": 390, "needs_demographics": False, "category": "Исследования"},
        "Флюорография": {"price": 190, "needs_demographics": False, "category": "Исследования"},

        # Медицинская документация (не нужна демография)
        "Врачебное заключение": {"price": 190, "needs_demographics": False, "category": "Документы"},
        "Выписка из стационара": {"price": 190, "needs_demographics": False, "category": "Документы"},
        "Назначения лечения": {"price": 190, "needs_demographics": False, "category": "Документы"},
        "Протокол операции": {"price": 190, "needs_demographics": False, "category": "Документы"},
        "Результаты консультации": {"price": 190, "needs_demographics": False, "category": "Документы"},
    }


def create_service_keyboard():
    """Клавиатура для выбора услуги (только услуги, без кликабельных категорий)"""
    services = get_service_prices()
    buttons = []

    # Создаем кнопки для всех услуг сразу
    service_rows = []

    for service_name, info in services.items():
        price = info["price"]
        service_rows.append(f"{service_name} - {price}₽")

    # Группируем по 2 услуги в ряд
    for i in range(0, len(service_rows), 2):
        row = []
        if i < len(service_rows):
            row.append(KeyboardButton(text=service_rows[i]))
        if i + 1 < len(service_rows):
            row.append(KeyboardButton(text=service_rows[i + 1]))
        if row:
            buttons.append(row)

    # Добавляем категории как НЕкнопки (просто текст)
    category_info = """<b>📋 АНАЛИЗЫ (нужен возраст/пол)</b>
• Анализы крови/мочи, Биохимия, Гормоны
• 190-290₽

<b>🏥 ИССЛЕДОВАНИЯ</b>
• УЗИ, МРТ, КТ, ЭКГ, Холтер
• 190-390₽

<b>📄 ДОКУМЕНТАЦИЯ</b>
• Врачебные заключения, Выписки
• 190₽"""

    buttons.append([KeyboardButton(text="❌ Отменить заказ")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True), category_info


def create_promo_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для ввода промокода"""
    skip_button = KeyboardButton(text="⏭️ Пропустить")
    cancel_button = KeyboardButton(text="❌ Отменить заказ")

    return ReplyKeyboardMarkup(
        keyboard=[[skip_button], [cancel_button]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def create_demographics_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для ввода пола"""
    male_button = KeyboardButton(text="👨 Мужской")
    female_button = KeyboardButton(text="👩 Женский")
    skip_button = KeyboardButton(text="🤷 Не указывать")
    cancel_button = KeyboardButton(text="❌ Отменить заказ")

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [male_button, female_button],
            [skip_button],
            [cancel_button]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard


def create_docs_questions_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для загрузки документов и вопросов"""
    ready_button = KeyboardButton(text="✅ Отправить на обработку")
    cancel_button = KeyboardButton(text="❌ Отменить заказ")

    return ReplyKeyboardMarkup(
        keyboard=[[ready_button, cancel_button]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def create_new_docs_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для загрузки новых документов"""
    done_button = KeyboardButton(text="✅ Документы загружены")
    cancel_button = KeyboardButton(text="❌ Отменить")

    return ReplyKeyboardMarkup(
        keyboard=[[done_button], [cancel_button]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def create_clarification_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для уточняющих вопросов"""
    cancel_button = KeyboardButton(text="❌ Отменить уточнение")

    return ReplyKeyboardMarkup(
        keyboard=[[cancel_button]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def create_contact_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для связи с админом"""
    cancel_button = KeyboardButton(text="❌ Отменить отправку")

    return ReplyKeyboardMarkup(
        keyboard=[[cancel_button]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


# ========== ИНЛАЙН-КЛАВИАТУРЫ ==========

def create_rating_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Создать клавиатуру с оценкой 1-5 звёзд"""
    buttons = []
    row = []
    for i in range(1, 6):
        row.append(InlineKeyboardButton(
            text="⭐" * i,
            callback_data=f"rate_{order_id}_{i}"
        ))
        if i == 3:  # Переносим на вторую строку после 3-й звезды
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_clarification_actions_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Создать клавиатуру для действий после ответа"""
    buttons = [
        [
            InlineKeyboardButton(text="❓ Задать вопрос",
                                 callback_data=f"clarify_{order_id}"),
            InlineKeyboardButton(text="⭐ Оценить",
                                 callback_data=f"rate_menu_{order_id}")
        ],
        [
            InlineKeyboardButton(text="👨‍💻 Связаться",
                                 callback_data=f"support_{order_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_simple_rating_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Простая клавиатура только с оценкой"""
    buttons = [
        [InlineKeyboardButton(text="⭐ Оценить заказ",
                              callback_data=f"rate_menu_{order_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ========== КЛАВИАТУРЫ ДЛЯ АДМИНА ==========

def create_admin_menu() -> ReplyKeyboardMarkup:
    """Создание меню администратора"""
    buttons = [
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📋 Все заказы")],
        [KeyboardButton(text="⏳ Ожидающие"), KeyboardButton(text="💾 Бэкап")],
        [KeyboardButton(text="🎫 Промокоды"), KeyboardButton(text="👥 Рефералы")],
        [KeyboardButton(text="📝 Шаблоны"), KeyboardButton(text="🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def create_admin_order_actions_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с действиями админа для заказа"""
    buttons = [
        [
            InlineKeyboardButton(text="📤 Ответить", callback_data=f"admin_reply_{order_id}"),
            InlineKeyboardButton(text="✅ Завершить", callback_data=f"admin_complete_{order_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"admin_cancel_{order_id}"),
            InlineKeyboardButton(text="📎 Новые доки", callback_data=f"admin_redocs_{order_id}")
        ],
        [
            InlineKeyboardButton(text="💬 Уточнения", callback_data=f"admin_clarifications_{order_id}"),
            InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"admin_price_{order_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_admin_template_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора шаблона"""
    buttons = []

    # Примерные шаблоны (в реальном коде нужно получать из БД)
    templates = [
        ("✅ Стандартный ответ", "template_1"),
        ("🚀 Срочный ответ", "template_2"),
        ("📝 Нужны документы", "template_3"),
        ("✅ Завершено", "template_4")
    ]

    for name, callback in templates:
        buttons.append([InlineKeyboardButton(text=name, callback_data=callback)])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ========== КЛАВИАТУРЫ ДЛЯ СОГЛАШЕНИЯ ==========

def create_agreement_keyboard(include_full: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура для соглашения"""
    buttons = []
    buttons.append([InlineKeyboardButton(text="✅ Принимаю", callback_data="agreement_accept")])

    if include_full:
        buttons.append([InlineKeyboardButton(text="📖 Полное соглашение", callback_data="agreement_full")])

    buttons.append([InlineKeyboardButton(text="❌ Отказываюсь", callback_data="agreement_reject")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_full_agreement_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для полного соглашения"""
    buttons = [
        [InlineKeyboardButton(text="✅ Принимаю", callback_data="agreement_accept")],
        [InlineKeyboardButton(text="↩️ Назад", callback_data="agreement_back")],
        [InlineKeyboardButton(text="❌ Отказываюсь", callback_data="agreement_reject")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def get_progress_bar(step: int, total_steps: int = 5) -> str:
    """Создает визуальный прогресс-бар"""
    filled = '█' * step
    empty = '░' * (total_steps - step)
    return f"[{filled}{empty}] {step}/{total_steps}"


def format_price(price: int) -> str:
    """Форматирование цены"""
    return f"{price}₽"


def get_service_categories():
    """Получить список категорий услуг"""
    services = get_service_prices()
    categories = {}
    for service_name, info in services.items():
        category = info["category"]
        if category not in categories:
            categories[category] = []
        categories[category].append({
            "name": service_name,
            "price": info["price"],
            "needs_demographics": info["needs_demographics"]
        })
    return categories


def create_category_keyboard():
    """Клавиатура для выбора категории услуг (упрощенная)"""
    categories = get_service_categories()
    buttons = []

    for category_name, services in categories.items():
        # Создаем кнопку для категории
        button_text = f"{category_name} ({len(services)} услуг)"
        buttons.append([KeyboardButton(text=button_text)])

    buttons.append([KeyboardButton(text="❌ Отменить заказ")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)


# ========== КЛАВИАТУРЫ ДЛЯ РЕФЕРАЛЬНОЙ СИСТЕМЫ ==========

def create_referral_share_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для поделиться реферальной ссылкой"""
    buttons = [
        [
            InlineKeyboardButton(text="📤 Поделиться ссылкой",
                                 callback_data=f"share_ref_{user_id}")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика",
                                 callback_data=f"ref_stats_{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_share_options_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с вариантами поделиться"""
    buttons = [
        [
            InlineKeyboardButton(text="📱 Скопировать ссылку",
                                 callback_data=f"copy_ref_{user_id}")
        ],
        [
            InlineKeyboardButton(text="👥 Поделиться в Telegram",
                                 callback_data=f"share_tg_{user_id}")
        ],
        [
            InlineKeyboardButton(text="↩️ Назад",
                                 callback_data="ref_back")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ========== КЛАВИАТУРЫ ДЛЯ СТАТУСОВ ЗАКАЗОВ ==========

def create_order_status_keyboard(order_id: int, status: str) -> InlineKeyboardMarkup:
    """Клавиатура в зависимости от статуса заказа"""
    buttons = []

    if status == "pending":
        buttons.append([
            InlineKeyboardButton(text="❌ Отменить заказ",
                                 callback_data=f"cancel_order_{order_id}")
        ])
    elif status == "completed":
        buttons.append([
            InlineKeyboardButton(text="❓ Задать вопрос",
                                 callback_data=f"clarify_{order_id}"),
            InlineKeyboardButton(text="⭐ Оценить",
                                 callback_data=f"rate_{order_id}")
        ])
    elif status == "needs_new_docs":
        buttons.append([
            InlineKeyboardButton(text="📎 Загрузить документы",
                                 callback_data=f"upload_docs_{order_id}")
        ])

    buttons.append([
        InlineKeyboardButton(text="📞 Поддержка",
                             callback_data=f"support_{order_id}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ========== ПРОСТЫЕ КНОПКИ ==========

def create_cancel_only_keyboard() -> ReplyKeyboardMarkup:
    """Просто кнопка отмены"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отменить")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def create_yes_no_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура Да/Нет"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
            [KeyboardButton(text="❌ Отменить")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def create_skip_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой пропустить"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏭️ Пропустить")],
            [KeyboardButton(text="❌ Отменить")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


# ========== КЛАВИАТУРЫ ДЛЯ ФИЛЬТРОВ АДМИНА ==========

def create_admin_filter_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура фильтров для админа"""
    buttons = [
        [
            InlineKeyboardButton(text="⏳ Ожидающие", callback_data="filter_pending"),
            InlineKeyboardButton(text="✅ Завершенные", callback_data="filter_completed")
        ],
        [
            InlineKeyboardButton(text="💰 Оплаченные", callback_data="filter_paid"),
            InlineKeyboardButton(text="❌ Отмененные", callback_data="filter_cancelled")
        ],
        [
            InlineKeyboardButton(text="❓ Уточнения", callback_data="filter_clarification"),
            InlineKeyboardButton(text="📎 Новые доки", callback_data="filter_new_docs")
        ],
        [
            InlineKeyboardButton(text="🗓️ За сегодня", callback_data="filter_today"),
            InlineKeyboardButton(text="📊 Все", callback_data="filter_all")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ========== КЛАВИАТУРЫ ДЛЯ УПРАВЛЕНИЯ ПРОМОКОДАМИ ==========

def create_promo_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления промокодами"""
    buttons = [
        [
            InlineKeyboardButton(text="➕ Создать промокод", callback_data="promo_create"),
            InlineKeyboardButton(text="📋 Список промокодов", callback_data="promo_list")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="promo_stats"),
            InlineKeyboardButton(text="🚫 Деактивировать", callback_data="promo_deactivate")
        ],
        [
            InlineKeyboardButton(text="↩️ Назад", callback_data="promo_back")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ========== КЛАВИАТУРЫ ДЛЯ ШАБЛОНОВ ==========

def create_template_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления шаблонами"""
    buttons = [
        [
            InlineKeyboardButton(text="➕ Добавить шаблон", callback_data="template_add"),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data="template_edit")
        ],
        [
            InlineKeyboardButton(text="🗑️ Удалить шаблон", callback_data="template_delete"),
            InlineKeyboardButton(text="📋 Список шаблонов", callback_data="template_list")
        ],
        [
            InlineKeyboardButton(text="↩️ Назад", callback_data="template_back")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ========== УНИВЕРСАЛЬНЫЕ КЛАВИАТУРЫ ==========

def create_navigation_keyboard(back_callback: str = "back",
                               cancel_callback: str = "cancel") -> InlineKeyboardMarkup:
    """Универсальная клавиатура навигации"""
    buttons = [
        [
            InlineKeyboardButton(text="↩️ Назад", callback_data=back_callback),
            InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_callback)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_confirmation_keyboard(yes_callback: str, no_callback: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    buttons = [
        [
            InlineKeyboardButton(text="✅ Да", callback_data=yes_callback),
            InlineKeyboardButton(text="❌ Нет", callback_data=no_callback)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)