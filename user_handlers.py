# handlers/user_handlers.py
import asyncio
import uuid
from datetime import datetime
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ContentType,
    LabeledPrice
)

from utils.config import config
from database.database import db
from bot import bot, logger
from utils.keyboards import (
    create_main_menu,
    create_service_keyboard,
    create_promo_keyboard,
    create_demographics_keyboard,
    create_docs_questions_keyboard,
    get_service_prices
)
from utils.agreement import AgreementHandler
from utils.validators import DocumentValidator
from models.enums import OrderStatus, DocumentType, DiscountType
from handlers.payment_handlers import send_invoice_to_user

router = Router()

from aiogram import Bot
from utils.config import config
import logging

logger = logging.getLogger(__name__)

# ========== СОСТОЯНИЯ ==========
class OrderState(StatesGroup):
    waiting_for_service = State()
    waiting_for_promo = State()
    waiting_for_payment = State()
    waiting_for_demographics = State()
    waiting_for_docs_and_questions = State()
    waiting_for_clarification = State()
    waiting_for_contact = State()


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def html_escape(text: str) -> str:
    """Экранирование HTML-символов"""
    if not text:
        return ""
    return (text.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def get_progress_bar(step: int, total_steps: int = 5) -> str:
    """Создает визуальный прогресс-бар"""
    filled = '█' * step
    empty = '░' * (total_steps - step)
    return f"[{filled}{empty}] {step}/{total_steps}"


def bold(text: str) -> str:
    """Жирный текст"""
    return f"<b>{html_escape(text)}</b>"


# ========== КЛАССЫ ДЛЯ КЛАВИАТУР ==========
class RatingHandler:
    """Класс для работы с оценками"""

    @staticmethod
    def create_rating_keyboard(order_id: int) -> InlineKeyboardMarkup:
        """Создать клавиатуру с оценкой 1-5 звёзд"""
        buttons = []
        row = []
        for i in range(1, 6):
            row.append(InlineKeyboardButton(
                text="⭐" * i,
                callback_data=f"rate_{order_id}_{i}"
            ))
            if i == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        return InlineKeyboardMarkup(inline_keyboard=buttons)


class ClarificationHandler:
    """Класс для работы с уточнениями"""

    @staticmethod
    def create_clarification_keyboard(order_id: int) -> InlineKeyboardMarkup:
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

    @staticmethod
    def create_simple_rating_keyboard(order_id: int) -> InlineKeyboardMarkup:
        """Простая клавиатура только с оценкой"""
        buttons = [
            [InlineKeyboardButton(text="⭐ Оценить заказ",
                                  callback_data=f"rate_menu_{order_id}")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)


# ========== КОМАНДА START ==========
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Начало работы с ботом"""
    await state.clear()

    # Проверяем реферальную ссылку
    args = message.text.split()
    referrer_id = None

    if len(args) > 1 and args[1].startswith('ref_'):
        try:
            referrer_id = int(args[1].replace('ref_', ''))
            if referrer_id != message.from_user.id:
                db.create_referral(referrer_id, message.from_user.id)
                logger.info(f"Реферальная ссылка использована: {referrer_id} → {message.from_user.id}")
        except (ValueError, IndexError):
            pass

    welcome_text = f"""👨‍⚕️ <b>Добро пожаловать в медицинский сервис расшифровки анализов RazMedBot</b>

🏥 <b>Профессиональная помощь в понимании ваших медицинских документов</b>

✨ <b>Наш подход к расшифровке:</b>

🤖 <b>Искусственный интеллект</b>
• Мгновенный анализ медицинских данных
• Сравнение с возрастными и половыми нормами
• Выявление ключевых показателей

👨‍⚕️ <b>Проверка медицинским специалистом</b>
• Экспертная оценка результатов
• Учет индивидуальных особенностей
• Рекомендации по дальнейшим действиям

<b>Выберите действие из меню ниже ⤵️</b>"""

    if message.from_user.id == config.ADMIN_ID:
        from admin.admin_handlers import create_admin_menu
        await message.answer(welcome_text, parse_mode="HTML", reply_markup=create_admin_menu())
    else:
        await message.answer(welcome_text, parse_mode="HTML", reply_markup=create_main_menu())

    logger.info(f"Пользователь {message.from_user.username} начал работу")


# ========== СОЗДАНИЕ ЗАКАЗА ==========
@router.message(F.text == "🩺 Создать заказ")
async def start_order_new_flow(message: Message, state: FSMContext):
    """Начало создания заказа"""
    # Проверяем, принимал ли пользователь уже соглашение
    if not db.check_agreement_accepted(message.from_user.id):
        # Показываем краткое соглашение
        text = AgreementHandler.get_short_agreement()
        keyboard = AgreementHandler.create_agreement_keyboard()

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        return

    # Если соглашение принято - начинаем новый поток
    await state.clear()
    await state.set_state(OrderState.waiting_for_service)

    instruction_text = f"""<b>🩺 ШАГ 1 из 5: ВЫБОР УСЛУГИ</b>

{get_progress_bar(1)}

<b>Выберите тип медицинских документов для расшифровки:</b>

<code>──────────────────────────────</code>
<b>📋 АНАЛИЗЫ (нужен возраст/пол)</b>
<code>──────────────────────────────</code>
• Анализы крови и мочи
• Биохимия, гормоны
• Коагулограммы
<code>💎 190-290₽</code>

<code>──────────────────────────────</code>
<b>🏥 ИССЛЕДОВАНИЯ</b>
<code>──────────────────────────────</code>
• УЗИ, МРТ, КТ, рентген
• ЭКГ, Холтер
<code>💎 190-390₽</code>

<code>──────────────────────────────</code>
<b>📄 ДОКУМЕНТАЦИЯ</b>
<code>──────────────────────────────</code>
• Врачебные заключения
• Выписки, назначения
• Протоколы операций
<code>💎 190₽</code>

<b>Выберите услугу из списка ниже:</b>"""

    keyboard, _ = create_service_keyboard()
    await message.answer(
        instruction_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# ========== ОТМЕНА ЗАКАЗА ==========
@router.message(F.text == "❌ Отменить заказ")
async def cancel_order(message: Message, state: FSMContext):
    """Отмена заказа пользователем"""
    await state.clear()
    await message.answer(
        "❌ Заказ отменен.",
        reply_markup=ReplyKeyboardRemove()
    )

    await asyncio.sleep(0.5)

    if message.from_user.id == config.ADMIN_ID:
        from admin.admin_handlers import create_admin_menu
        await message.answer(
            "Выберите действие:",
            reply_markup=create_admin_menu()
        )
    else:
        await message.answer(
            "Выберите действие:",
            reply_markup=create_main_menu()
        )


# ========== ПРИГЛАСИТЬ ДРУГА ==========
@router.message(F.text == "👥 Пригласить друга")
async def show_referral_info(message: Message):
    """Показать информацию о реферальной программе"""
    try:
        # Получаем статистику
        stats = db.get_referrer_stats(message.from_user.id)

        # Получаем username бота для ссылки
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            if not bot_username:
                referral_link = f"https://t.me/{bot_info.id}?start=ref_{message.from_user.id}"
            else:
                referral_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"
        except Exception as e:
            logger.error(f"Ошибка получения username бота: {e}")
            referral_link = f"t.me/ваш_бот?start=ref_{message.from_user.id}"

        referral_text = f"""<b>👥 ПРИГЛАСИТЬ ДРУГА</b>

💎 <b>Приглашайте друзей и получайте бонусы!</b>

<b>Как это работает:</b>
1. Вы приглашаете друга по своей ссылке
2. Друг получает <b>скидку {config.REFERRED_DISCOUNT_PERCENT}%</b> на первый заказ
3. Когда друг оплатит заказ, вы получаете <b>{config.REFERRER_BONUS_PERCENT}%</b> от суммы его заказа

<b>Ваша реферальная ссылка:</b>
<code>{referral_link}</code>

<b>Ваша статистика:</b>
• Приглашено друзей: {stats.get('total_referred', 0)}
• Из них сделали заказы: {stats.get('completed_referred', 0)}
• Всего заработано: {stats.get('total_bonus', 0):.2f}₽

<b>Просто отправьте другу эту ссылку!</b>"""

        await message.answer(referral_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка в show_referral_info: {e}")
        # Простой текст на случай ошибки
        await message.answer(
            f"👥 <b>Пригласить друга</b>\n\n"
            f"Ваша реферальная ссылка:\n"
            f"<code>t.me/ваш_бот?start=ref_{message.from_user.id}</code>\n\n"
            f"Приглашайте друзей и получайте {config.REFERRER_BONUS_PERCENT}% от их заказов!\n"
            f"Друзья получают скидку {config.REFERRED_DISCOUNT_PERCENT}% на первый заказ.",
            parse_mode="HTML"
        )


# ========== ОБРАБОТКА ВЫБОРА УСЛУГИ ==========
@router.message(OrderState.waiting_for_service)
async def handle_service_selection(message: Message, state: FSMContext):
    """Обработка выбора услуги"""
    if message.text == "❌ Отменить заказ":
        await cancel_order(message, state)
        return

    services = get_service_prices()
    selected_service = None
    service_info = None

    # Ищем выбранную услугу (убираем цену из текста)
    input_text = message.text
    for service_name in services.keys():
        # Проверяем, начинается ли текст с названия услуги
        if input_text.startswith(service_name):
            selected_service = service_name
            service_info = services[service_name]
            break

    if not selected_service:
        # Если не нашли услугу, показываем меню снова
        await message.answer(
            "❌ <b>Пожалуйста, выберите услугу с помощью кнопок ниже</b>\n\n"
            "Нажимайте только на кнопки с названиями услуг и ценами.",
            parse_mode="HTML"
        )

        # Показываем инструкцию и клавиатуру
        keyboard, category_info = create_service_keyboard()

        instruction_text = f"""<b>🩺 ШАГ 1 из 5: ВЫБОР УСЛУГИ</b>

[█░░░░] 1/5

<b>Выберите тип медицинских документов для расшифровки:</b>

{category_info}

<b>Выберите услугу из списка ниже:</b>"""

        await message.answer(instruction_text, parse_mode="HTML", reply_markup=keyboard)
        return

    original_price = service_info["price"]
    needs_demographics = service_info["needs_demographics"]

    # Проверяем реферальную скидку
    has_referral_discount, discount_percent = db.check_referral_discount(message.from_user.id)
    final_price = original_price

    if has_referral_discount:
        discount_amount = original_price * (discount_percent / 100)
        final_price = max(0, original_price - discount_amount)
        discount_text = f"\n🎁 <b>Реферальная скидка: {discount_percent}% ({int(discount_amount)}₽)</b>"
    else:
        discount_text = ""

    await state.update_data(
        service_type=selected_service,
        original_price=original_price,
        current_price=int(final_price),
        needs_demographics=needs_demographics,
        discount_applied=original_price - final_price if has_referral_discount else 0,
        discount_type="referral" if has_referral_discount else None
    )

    await state.set_state(OrderState.waiting_for_promo)

    instruction_text = f"""<b>💎 ШАГ 2 из 5: ПРОМОКОД</b>

[██░░░] 2/5

✅ <b>Услуга выбрана:</b> {selected_service}
💰 <b>Стоимость:</b> {original_price}₽
{discount_text}
💰 <b>Итоговая цена:</b> <code>{int(final_price)}₽</code>

──────────────────────────────
<b>Есть промокод?</b>

Если у вас есть промокод на скидку, введите его сейчас.
Или нажмите "⏭️ Пропустить" для продолжения.

<b>Введите промокод:</b>"""

    await message.answer(
        instruction_text,
        parse_mode="HTML",
        reply_markup=create_promo_keyboard()
    )


# ========== ОБРАБОТКА ПРОМОКОДА ==========
@router.message(OrderState.waiting_for_promo)
async def handle_promo_code(message: Message, state: FSMContext):
    """Обработка промокода"""
    if message.text == "❌ Отменить заказ":
        await cancel_order(message, state)
        return

    data = await state.get_data()
    original_price = data.get('original_price')
    current_price = data.get('current_price')
    selected_service = data.get('service_type')
    needs_demographics = data.get('needs_demographics', True)

    promo_code = None
    promo_discount = 0

    if message.text != "⏭️ Пропустить":
        # Пользователь ввел промокод
        promo_code = message.text.strip().upper()

        # Создаем временный order_id 0 для проверки промокода
        temp_order_id = 0

        # Проверяем и применяем промокод
        discount_amount, new_price, error_message = db.apply_promo_code(
            promo_code, message.from_user.id, temp_order_id, current_price
        )

        if error_message:
            await message.answer(f"❌ {error_message}\n\nВведите другой промокод или нажмите '⏭️ Пропустить':")
            return

        promo_discount = discount_amount
        current_price = new_price

    # Обновляем данные
    total_discount = data.get('discount_applied', 0) + promo_discount
    discount_type = "promo" if promo_code else data.get('discount_type')

    await state.update_data(
        current_price=current_price,
        discount_applied=total_discount,
        discount_type=discount_type,
        promo_code=promo_code
    )

    # Переходим к оплате
    await state.set_state(OrderState.waiting_for_payment)

    # Создаем временный заказ для оплаты
    temp_order_id = db.create_prepaid_order(
        user_id=message.from_user.id,
        username=message.from_user.username or "Пользователь",
        service_type=selected_service,
        price=current_price,
        original_price=original_price,
        discount_applied=total_discount,
        discount_type=discount_type,
        promo_code=promo_code,
        needs_demographics=needs_demographics
    )

    # Если есть реферальная скидка, применяем ее к заказу
    referrer_id = None
    if data.get('discount_type') == 'referral':
        discount_amount, final_price, referrer_id = db.apply_referral_discount(
            message.from_user.id, temp_order_id, original_price
        )

        if referrer_id:
            # Обновляем заказ с реферером
            cursor = db.conn.cursor()
            cursor.execute('''
                UPDATE orders 
                SET referrer_id = ?, price = ?
                WHERE id = ?
            ''', (referrer_id, final_price, temp_order_id))
            db.conn.commit()

            current_price = final_price
            await state.update_data(current_price=current_price)

    await state.update_data(
        order_id=temp_order_id,
        temp_order_id=temp_order_id,
        referrer_id=referrer_id
    )

    instruction_text = f"""<b>💰 ШАГ 3 из 5: ОПЛАТА</b>

{get_progress_bar(3)}

<code>──────────────────────────────</code>
<b>📋 ДЕТАЛИ ВАШЕГО ЗАПРОСА</b>
<code>──────────────────────────────</code>
<b>Услуга:</b> {html_escape(selected_service)}
<b>Исходная цена:</b> {original_price}₽
<b>Итоговая цена:</b> <code>{current_price}₽</code>

"""

    if total_discount > 0:
        instruction_text += f"<b>Скидка:</b> {total_discount:.2f}₽\n"

    if promo_code:
        instruction_text += f"<b>Промокод:</b> {promo_code}\n"

    instruction_text += f"""
<code>──────────────────────────────</code>
<b>🔬 ЧТО ВКЛЮЧЕНО В УСЛУГУ</b>
<code>──────────────────────────────</code>
<code>1. 🤖 AI-АНАЛИЗ ДОКУМЕНТОВ</code>
• Автоматическая обработка медицинских данных
• Сравнение показателей с референсными значениями

<code>2. 👨‍⚕️ ЭКСПЕРТНАЯ ПРОВЕРКА</code>
• Верификация результатов AI-анализа
• Профессиональная интерпретация данных

<code>3. 📝 ПОДРОБНАЯ РАСШИФРОВКА</code>
• Структурированный отчет по вашим документам
• Ответы на поставленные вопросы

<code>4. ⏱️ ГАРАНТИИ СЕРВИСА</code>
• Срок выполнения: до 24 часов
• Возможность уточняющих вопросов
• Конфиденциальность данных

<b>💳 ДЛЯ ПРОДОЛЖЕНИЯ НЕОБХОДИМА ОПЛАТА</b>

После успешной оплаты вы перейдете к заполнению 
дополнительной информации для более точной расшифровки.

<b>Готовы продолжить?</b>"""

    await message.answer(
        instruction_text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

    # Отправляем счет на оплату
    await asyncio.sleep(2)

    await message.answer("💳 <b>Отправляю счет на оплату...</b>", parse_mode="HTML")

    success, processed_order_id = await send_invoice_to_user(
        user_id=message.from_user.id,
        order_id=temp_order_id,
        price=current_price,
        service_type=selected_service
    )

    if not success:
        await message.answer(
            "⚠️ <b>Не удалось отправить счет на оплату.</b>\nПожалуйста, напишите в поддержку: " + html_escape(
                config.SUPPORT_CHANNEL),
            parse_mode="HTML"
        )
        await state.clear()
        if message.from_user.id == config.ADMIN_ID:
            from admin.admin_handlers import create_admin_menu
            await message.answer("Выберите действие:", reply_markup=create_admin_menu())
        else:
            await message.answer("Выберите действие:", reply_markup=create_main_menu())
        return

    # Сохраняем order_id в состоянии
    await state.update_data(order_id=processed_order_id)

    # Если это тестовый режим, переходим к следующему шагу
    if config.PAYMENT_TEST_MODE:
        await asyncio.sleep(1)  # Небольшая пауза для UX

        await message.answer(
            f"""✅ <b>ТЕСТОВЫЙ ПЛАТЕЖ ОБРАБОТАН!</b>

Теперь продолжим оформление заказа.""",
            parse_mode="HTML"
        )

        await asyncio.sleep(1)

        # Проверяем, нужна ли демография
        if needs_demographics:
            # Переходим к демографии
            await state.set_state(OrderState.waiting_for_demographics)

            await message.answer(
                f"""<b>👤 ШАГ 4 из 5: ОСНОВНАЯ ИНФОРМАЦИЯ</b>

{get_progress_bar(4)}

<b>Пожалуйста, укажите возраст пациента:</b>

Эта информация необходима для корректной интерпретации 
анализов, так как многие медицинские нормы различаются 
в зависимости от возраста.

<i>Введите возраст цифрами:</i>
<code>Пример: 35</code>""",
                parse_mode="HTML",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            # Пропускаем демографию, переходим к документам
            await state.set_state(OrderState.waiting_for_docs_and_questions)
            await state.update_data(age=None, sex="Не указан")

            await message.answer(
                f"""<b>📎 ШАГ 4 из 5: ДОКУМЕНТЫ И ВОПРОСЫ</b>

{get_progress_bar(4)}

<b>📤 ЗАГРУЗКА ДОКУМЕНТОВ</b>

Для проведения качественной расшифровки необходимо 
загрузить медицинские документы.

<b>Принимаемые форматы:</b>
• 📸 Фотографии/скан-копии документов
• 📄 PDF файлы с результатами
• 📝 Документы Word (DOC/DOCX)

<b>Технические ограничения:</b>
• Максимальное количество: {config.MAX_DOCUMENTS} документов
• Максимальный размер: {config.MAX_FILE_SIZE // (1024 * 1024)} МБ каждый

<b>После загрузка документов, опишите ваш вопрос ниже.</b>
<i>Чем подробнее описание, тем точнее будет расшифровка</i>

<code>──────────────────────────────</code>
<b>Загрузите документы и опишите вопрос, затем нажмите «✅ Отправить на обработку»</b>""",
                parse_mode="HTML",
                reply_markup=create_docs_questions_keyboard()
            )
    else:
        # В реальном режиме ждем платеж
        await message.answer(
            "✅ Счет отправлен. Пожалуйста, оплатите его в течение 15 минут.\n"
            "После успешной оплаты мы продолжим оформление заказа.",
            parse_mode="HTML"
        )


# ========== ОБРАБОТКА ДЕМОГРАФИИ ==========
@router.message(OrderState.waiting_for_demographics)
async def handle_demographics(message: Message, state: FSMContext):
    """Обработка возраста и пола"""
    data = await state.get_data()

    if 'age' not in data:
        # Ожидаем возраст
        if not message.text.isdigit():
            await message.answer("❌ Пожалуйста, укажите возраст цифрами (например: 35)")
            return

        age = int(message.text)

        if age < 0 or age > 120:
            await message.answer("❌ Пожалуйста, укажите реальный возраст (от 0 до 120 лет).")
            return

        await state.update_data(age=age)

        # Запрашиваем пол
        await message.answer(
            f"""<b>👤 ШАГ 4 из 5: ОСНОВНАЯ ИНФОРМАЦИЯ</b>

{get_progress_bar(4)}

✅ <b>Возраст сохранен:</b> {age} лет

<b>Теперь укажите ваш пол:</b>

Эта информация необходима для корректной интерпретации 
анализов, так как многие медицинские нормы различаются 
в зависимости от пола пациента.

<i>Выберите соответствующий вариант:</i>""",
            parse_mode="HTML",
            reply_markup=create_demographics_keyboard()
        )
        return

    # Ожидаем пол
    if message.text not in ["👨 Мужской", "👩 Женский", "🤷 Не указывать"]:
        await message.answer("❌ Пожалуйста, выберите пол с помощью кнопок")
        await message.answer("Выберите пол:", reply_markup=create_demographics_keyboard())
        return

    sex = message.text.replace("👨 ", "").replace("👩 ", "").replace("🤷 ", "")

    # Сохраняем пол и переходим к документам
    age = data['age']
    await state.update_data(sex=sex)
    await state.set_state(OrderState.waiting_for_docs_and_questions)

    await state.update_data(documents=[], document_types=[])

    await message.answer(
        f"""<b>📎 ШАГ 5 из 5: ДОКУМЕНТЫ И ВОПРОСЫ</b>

{get_progress_bar(5)}

✅ <b>Основная информация сохранена:</b>
• Возраст: {age} лет
• Пол: {sex}

<b>📤 ЗАГРУЗКА ДОКУМЕНТОВ</b>

Для проведения качественной расшифровки необходимо 
загрузить медицинские документы.

<b>Принимаемые форматы:</b>
• 📸 Фотографии/скан-копии документов
• 📄 PDF файлы с результатами
• 📝 Документы Word (DOC/DOCX)

<b>Технические ограничения:</b>
• Максимальное количество: {config.MAX_DOCUMENTS} документов
• Максимальный размер: {config.MAX_FILE_SIZE // (1024 * 1024)} МБ каждый

<b>После загрузки документов, опишите ваш вопрос ниже.</b>
<i>Чем подробнее описание, тем точнее будет расшифровка</i>

<code>──────────────────────────────</code>
<b>Загрузите документы и опишите вопрос, затем нажмите «✅ Отправить на обработку»</b>""",
        parse_mode="HTML",
        reply_markup=create_docs_questions_keyboard()
    )


# ========== ОБРАБОТКА ДОКУМЕНТОВ И ВОПРОСОВ ==========

# Обработка фото документов
@router.message(OrderState.waiting_for_docs_and_questions, F.photo)
async def handle_document_photo(message: Message, state: FSMContext):
    """Обработка фото документов"""
    # Валидация
    is_valid, error_msg = await DocumentValidator.validate_photo(message)
    if not is_valid:
        await message.answer(f"⚠️ {error_msg}")
        return

    # Получаем текущие данные
    data = await state.get_data()
    documents = data.get('documents', [])
    document_types = data.get('document_types', [])

    # Проверяем лимит документов
    if len(documents) >= config.MAX_DOCUMENTS:
        await message.answer(
            f"⚠️ Максимальное количество документов: {config.MAX_DOCUMENTS}. "
            "Пожалуйста, нажмите «✅ Отправить на обработку»."
        )
        return

    # Сохраняем file_id
    file_id = message.photo[-1].file_id
    documents.append(file_id)
    document_types.append(DocumentType.PHOTO.value)

    await state.update_data(documents=documents, document_types=document_types)

    await message.answer(
        f"✅ Фото получено! Загружено документов: {len(documents)}/{config.MAX_DOCUMENTS}\n\n"
        f"Теперь опишите ваш вопрос или загрузите еще документы."
    )


# Обработка файлов-документов
@router.message(OrderState.waiting_for_docs_and_questions, F.document)
async def handle_document_file(message: Message, state: FSMContext):
    """Обработка файлов-документов"""
    # Валидация
    is_valid, error_msg = await DocumentValidator.validate_document(message)
    if not is_valid:
        await message.answer(f"⚠️ {error_msg}")
        return

    # Получаем текущие данные
    data = await state.get_data()
    documents = data.get('documents', [])
    document_types = data.get('document_types', [])

    # Проверяем лимит документов
    if len(documents) >= config.MAX_DOCUMENTS:
        await message.answer(
            f"⚠️ Максимальное количество документов: {config.MAX_DOCUMENTS}. "
            "Пожалуйста, нажмите «✅ Отправить на обработку»."
        )
        return

    # Сохраняем file_id
    file_id = message.document.file_id
    documents.append(file_id)

    # Определяем тип документа
    mime_type = message.document.mime_type
    doc_type = DocumentValidator.ALLOWED_MIME_TYPES.get(mime_type, DocumentType.OTHER)
    document_types.append(doc_type.value)

    await state.update_data(documents=documents, document_types=document_types)

    file_name = message.document.file_name or "документ"
    await message.answer(
        f"✅ Файл '{file_name}' получен! Загружено документов: {len(documents)}/{config.MAX_DOCUMENTS}\n\n"
        f"Теперь опишите ваш вопрос или загрузите еще документы."
    )


# Завершение заказа
@router.message(OrderState.waiting_for_docs_and_questions, F.text == "✅ Отправить на обработку")
async def finish_order(message: Message, state: FSMContext):
    """Завершение заказа"""
    data = await state.get_data()
    documents = data.get('documents', [])

    if not documents:
        await message.answer(
            "❌ Вы не отправили ни одного документа.\n\n"
            "Пожалуйста, отправьте фото или файлы документов сначала.",
            reply_markup=create_docs_questions_keyboard()
        )
        return

    # Получаем вопросы из истории сообщений
    # Вместо этого просто переходим к вводу вопросов
    await message.answer(
        "📝 <b>Опишите ваш вопрос или ситуацию:</b>\n\n"
        "Пожалуйста, напишите, что вы хотите узнать по вашим документам.\n"
        "Чем подробнее описание, тем точнее будет расшифровка.\n\n"
        "<i>Пример: \"Помогите расшифровать анализ крови, особенно интересуют показатели печени.\"</i>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

    # Сохраняем документы и ждем вопросы
    await state.set_state(OrderState.waiting_for_docs_and_questions)
    await state.update_data(waiting_for_questions=True)


# Обработка ввода вопросов
@router.message(OrderState.waiting_for_docs_and_questions, F.text)
async def handle_questions_input(message: Message, state: FSMContext):
    """Обработка ввода вопросов"""
    # Проверяем, ожидаем ли мы вопрос
    data = await state.get_data()
    if not data.get('waiting_for_questions'):
        return  # Это не вопрос, а что-то другое

    # Это текстовый вопрос пользователя
    user_questions = message.text.strip()

    if len(user_questions) < 10:
        await message.answer(
            "❌ Пожалуйста, опишите ваш вопрос более подробно (минимум 10 символов).\n"
            "Пример: 'Помогите расшифровать анализ крови.'"
        )
        return

    # Сохраняем вопросы и завершаем заказ
    order_id = data.get('order_id')
    if not order_id:
        await message.answer(
            "❌ <b>Ошибка: заказ не найден.</b>\n\n"
            "Пожалуйста, начните заказ заново с /start",
            parse_mode="HTML"
        )
        await state.clear()
        return

    # Обновляем детали заказа в БД
    age = data.get('age')
    sex = data.get('sex', 'Не указан')

    db.update_order_details(
        order_id=order_id,
        age=age,
        sex=sex,
        questions=user_questions,
        documents=data.get('documents', []),
        document_types=data.get('document_types', [])
    )

    # Обновляем статус на "processing"
    db.update_order_status(order_id, OrderStatus.PROCESSING)

    # Получаем полную информацию о заказе
    order = db.get_order_by_id(order_id)
    if order:
        service_type = order[8] if len(order) > 8 else "Не указано"
        price = order[14] if len(order) > 14 else 490
        original_price = order[15] if len(order) > 15 else price
    else:
        service_type = data.get('service_type', 'Не указано')
        price = data.get('current_price', 490)
        original_price = data.get('original_price', price)

    # Рассчитываем скидку
    discount = original_price - price if original_price > price else 0

    summary = f"""<b>🎉 ЗАКАЗ #{order_id} ОФОРМЛЕН!</b>

<code>──────────────────────────────</code>
<b>📋 ИНФОРМАЦИЯ О ЗАКАЗЕ</b>
<code>──────────────────────────────</code>
<b>Услуга:</b> {html_escape(service_type)}
"""

    if discount > 0:
        summary += f"<b>Исходная цена:</b> {original_price}₽\n"
        summary += f"<b>Скидка:</b> {discount}₽\n"

    summary += f"""<b>Итоговая цена:</b> <code>{price}₽</code> (✅ Оплачено)
"""

    if age is not None:
        summary += f"<b>Возраст пациента:</b> {age} лет\n"
    summary += f"""<b>Пол пациента:</b> {html_escape(sex)}
<b>Количество документов:</b> {len(data.get('documents', []))}
<b>Дата создания:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}

<code>──────────────────────────────</code>
<b>🔬 ПРОЦЕСС ОБРАБОТКИ</b>
<code>──────────────────────────────</code>
<code>1. 📤 ЗАГРУЗКА В СИСТЕМУ</code>
   Ваши документы переданы на обработку

<code>2. 🤖 AI-АНАЛИЗ</code>
   Искусственный интеллект проводит первичный анализ данных

<code>3. 👨‍⚕️ ЭКСПЕРТНАЯ ПРОВЕРКА</code>
   Медицинский специалист проверяет результаты и готовит расшифровку

<code>4. ✅ ВЫДАЧА РЕЗУЛЬТАТА</code>
   Вы получаете структурированный ответ с объяснениями

<code>──────────────────────────────</code>
<b>⏱️ СРОКИ И ГАРАНТИИ</b>
<code>──────────────────────────────</code>
<b>Максимальное время обработки:</b> 24 часа
<b>Формат ответа:</b> Текстовое сообщение в этот чат
<b>Дополнительные возможности:</b>
• Уточняющие вопросы в течение 24 часов после ответа
• Возможность оценки качества услуги

<code>──────────────────────────────</code>
<b>📞 КОНТАКТНАЯ ИНФОРМАЦИЯ</b>
<code>──────────────────────────────</code>
<b>Исполнитель:</b> {config.SELF_EMPLOYED_NAME}
<b>Статус:</b> Медицинский специалист

<b>✅ Ваш запрос принят в работу. 
Оповещение о готовности придет в этот чат.</b>

<code>💡 <i>Рекомендация:</i> Сохраните номер заказа #{order_id} 
для быстрого доступа к информации о нем.</code>"""

    await message.answer(summary, parse_mode="HTML")

    # Уведомление админу
    try:
        admin_text = f"""<b>🆕 НОВЫЙ ЗАКАЗ #{order_id}</b>

<b>👤 КЛИЕНТ:</b>
• ID: {message.from_user.id}
• Username: @{message.from_user.username or 'не указан'}

<b>📋 ПАРАМЕТРЫ ЗАКАЗА:</b>
• Услуга: {service_type}
• Стоимость: {price}₽ (скидка: {discount}₽)"""

        if age is not None:
            admin_text += f"\n• Возраст пациента: {age}"
        admin_text += f"""
• Пол пациента: {sex}
• Документов: {len(data.get('documents', []))}

<b>❓ ВОПРОС КЛИЕНТА:</b>
{user_questions[:500]}{'...' if len(user_questions) > 500 else ''}

<b>⏱️ ДАТА СОЗДАНИЯ:</b>
{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

<b>🚀 ДЕЙСТВИЯ:</b>
• Ответить клиенту: /send_{order_id} [текст ответа]
• Быстрый ответ: /template1_{order_id} (и другие шаблоны)
• Запросить новые доки: /redocs_{order_id} [причина]
• Изменить статус: /complete_{order_id} или /cancel_{order_id}"""

        await bot.send_message(
            chat_id=config.ADMIN_ID,
            text=admin_text,
            parse_mode="HTML"
        )

        # Отправляем документы админу
        for i, file_id in enumerate(data.get('documents', []), 1):
            try:
                await bot.send_document(
                    chat_id=config.ADMIN_ID,
                    document=file_id,
                    caption=f"Документ {i} от @{message.from_user.username or 'пользователя'} (Заказ #{order_id})"
                )
            except:
                await bot.send_photo(
                    chat_id=config.ADMIN_ID,
                    photo=file_id,
                    caption=f"Документ {i} от @{message.from_user.username or 'пользователя'} (Заказ #{order_id})"
                )

        logger.info(f"✅ Заказ #{order_id} полностью оформлен от @{message.from_user.username}")

    except Exception as e:
        logger.error(f"Ошибка отправки уведомления админу: {e}")

    await state.clear()
    if message.from_user.id == config.ADMIN_ID:
        from admin.admin_handlers import create_admin_menu
        await message.answer(
            "📝 Вы можете создать новый заказ или посмотреть текущие в главном меню.",
            reply_markup=create_admin_menu()
        )
    else:
        await message.answer(
            "📝 Вы можете создать новый заказ или посмотреть текущие в главном меню.",
            reply_markup=create_main_menu()
        )


# ========== ОБРАБОТКА УТОЧНЯЮЩИХ ВОПРОСОВ ==========

# Запрос на уточняющий вопрос
@router.callback_query(F.data.startswith("clarify_"))
async def handle_clarification_request(callback: types.CallbackQuery, state: FSMContext):
    """Обработка запроса на уточняющий вопрос"""
    try:
        order_id = int(callback.data.split('_')[1])

        # Проверяем возможность задать вопрос
        can_clarify, message_text = db.can_user_clarify(order_id, callback.from_user.id)

        if not can_clarify:
            await callback.answer(f"❌ {message_text}", show_alert=True)
            return

        # Устанавливаем состояние для уточнения
        await state.set_state(OrderState.waiting_for_clarification)
        await state.update_data(clarification_order_id=order_id)

        await callback.message.answer(
            f"""<b>📝 УТОЧНЯЮЩИЙ ВОПРОС ПО ЗАКАЗУ #{order_id}</b>

Вы можете задать уточняющий вопрос по вашему заказу.

<b>Доступные форматы:</b>
• Текстовое сообщение
• Фотография документа
• Файл (PDF, DOC, DOCX)

<b>Ограничения:</b>
• Время для уточнений: {config.CLARIFICATION_TIME_LIMIT_HOURS} часов после получения ответа
• Ответ придет в этот чат

<b>Напишите ваш вопрос или отправьте документ:</b>""",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="❌ Отменить уточнение")]],
                resize_keyboard=True
            )
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка обработки запроса на уточнение: {e}")
        await callback.answer("❌ Ошибка при обработке запроса")


# Отмена уточняющего вопроса
@router.message(OrderState.waiting_for_clarification, F.text == "❌ Отменить уточнение")
async def cancel_clarification(message: Message, state: FSMContext):
    """Отмена уточняющего вопроса"""
    await state.clear()
    await message.answer(
        "❌ Уточняющий вопрос отменен.",
        reply_markup=ReplyKeyboardRemove()
    )

    if message.from_user.id == config.ADMIN_ID:
        from admin.admin_handlers import create_admin_menu
        await message.answer("Выберите действие:", reply_markup=create_admin_menu())
    else:
        await message.answer("Выберите действие:", reply_markup=create_main_menu())


# Обработка текстового уточняющего вопроса
@router.message(OrderState.waiting_for_clarification, F.text)
async def handle_clarification_text(message: Message, state: FSMContext):
    """Обработка текстового уточняющего вопроса"""
    data = await state.get_data()
    order_id = data.get('clarification_order_id')

    if not order_id:
        await message.answer("❌ Ошибка: заказ не найден")
        await state.clear()
        return

    # Добавляем уточнение в БД
    clarification_id = db.add_clarification(
        order_id=order_id,
        user_id=message.from_user.id,
        message_text=message.text,
        is_from_user=True
    )

    # Уведомляем админа
    order = db.get_order_by_id(order_id)
    if order:
        username = order[2] or "без username"

        admin_text = f"""❓ УТОЧНЯЮЩИЙ ВОПРОС #{clarification_id}

Заказ: #{order_id}
От: @{username} (ID: {message.from_user.id})
Вопрос: {message.text[:500]}

🔧 Ответить: /clarify_answer_{clarification_id} [текст]
📝 Быстрый ответ: /template1_{order_id} (и другие)"""

        await bot.send_message(
            config.ADMIN_ID,
            admin_text
        )

    await message.answer(
        f"✅ Ваш уточняющий вопрос отправлен специалисту (ID вопроса: #{clarification_id})\n\n"
        f"Ответ придет в этот чат.",
        reply_markup=ReplyKeyboardRemove()
    )

    await state.clear()

    if message.from_user.id == config.ADMIN_ID:
        from admin.admin_handlers import create_admin_menu
        await message.answer("Выберите действие:", reply_markup=create_admin_menu())
    else:
        await message.answer("Выберите действие:", reply_markup=create_main_menu())


# Обработка уточняющего вопроса с фото
@router.message(OrderState.waiting_for_clarification, F.photo)
async def handle_clarification_photo(message: Message, state: FSMContext):
    """Обработка уточняющего вопроса с фото"""
    data = await state.get_data()
    order_id = data.get('clarification_order_id')

    if not order_id:
        await message.answer("❌ Ошибка: заказ не найден")
        await state.clear()
        return

    # Для фото берем подпись или создаем стандартную
    caption = message.caption or "Дополнительное фото к уточняющему вопросу"

    # Добавляем уточнение в БД
    clarification_id = db.add_clarification(
        order_id=order_id,
        user_id=message.from_user.id,
        message_text=caption,
        message_type="photo",
        file_id=message.photo[-1].file_id,
        is_from_user=True
    )

    # Отправляем админу
    order = db.get_order_by_id(order_id)
    if order:
        username = order[2] or "без username"

        await bot.send_photo(
            config.ADMIN_ID,
            photo=message.photo[-1].file_id,
            caption=f"""❓ УТОЧНЯЮЩИЙ ВОПРОС С ФОТО #{clarification_id}

Заказ: #{order_id}
От: @{username} (ID: {message.from_user.id})
Описание: {caption[:200]}

🔧 Ответить: /clarify_answer_{clarification_id} [текст]
📝 Быстрый ответ: /template1_{order_id} (и другие)"""
        )

    await message.answer(
        f"✅ Ваше фото с вопросом отправлено специалисту (ID вопроса: #{clarification_id})",
        reply_markup=ReplyKeyboardRemove()
    )

    await state.clear()

    if message.from_user.id == config.ADMIN_ID:
        from admin.admin_handlers import create_admin_menu
        await message.answer("Выберите действие:", reply_markup=create_admin_menu())
    else:
        await message.answer("Выберите действие:", reply_markup=create_main_menu())


# Обработка уточняющего вопроса с документом
@router.message(OrderState.waiting_for_clarification, F.document)
async def handle_clarification_document(message: Message, state: FSMContext):
    """Обработка уточняющего вопроса с документом"""
    data = await state.get_data()
    order_id = data.get('clarification_order_id')

    if not order_id:
        await message.answer("❌ Ошибка: заказ не найден")
        await state.clear()
        return

    # Для документа берем подпись или имя файла
    caption = message.caption or f"Дополнительный документ: {message.document.file_name or 'файл'}"

    # Добавляем уточнение в БД
    clarification_id = db.add_clarification(
        order_id=order_id,
        user_id=message.from_user.id,
        message_text=caption,
        message_type="document",
        file_id=message.document.file_id,
        is_from_user=True
    )

    # Отправляем админу
    order = db.get_order_by_id(order_id)
    if order:
        username = order[2] or "без username"

        await bot.send_document(
            config.ADMIN_ID,
            document=message.document.file_id,
            caption=f"""❓ УТОЧНЯЮЩИЙ ВОПРОС С ДОКУМЕНТОМ #{clarification_id}

Заказ: #{order_id}
От: @{username} (ID: {message.from_user.id})
Описание: {caption[:200]}

🔧 Ответить: /clarify_answer_{clarification_id} [текст]
📝 Быстрый ответ: /template1_{order_id} (и другие)"""
        )

    await message.answer(
        f"✅ Ваш документ с вопросом отправлен специалисту (ID вопроса: #{clarification_id})",
        reply_markup=ReplyKeyboardRemove()
    )

    await state.clear()

    if message.from_user.id == config.ADMIN_ID:
        from admin.admin_handlers import create_admin_menu
        await message.answer("Выберите действие:", reply_markup=create_admin_menu())
    else:
        await message.answer("Выберите действие:", reply_markup=create_main_menu())


# ========== ОБРАБОТКА СВЯЗИ С ПОДДЕРЖКОЙ ==========

# Запрос на связь с админом
@router.message(F.text == "👨‍💻 Связаться")
async def handle_contact_request(message: Message, state: FSMContext):
    """Обработка запроса на связь с админом"""

    await state.set_state(OrderState.waiting_for_contact)

    contact_text = f"""<b>👨‍💻 СВЯЗЬ С АДМИНИСТРАТОРОМ</b>

Вы можете написать сообщение администратору бота.

<b>Что можно обсудить:</b>
• Вопросы по работе сервиса
• Технические проблемы
• Предложения по улучшению
• Вопросы по оплате
• Другие вопросы

<b>Как это работает:</b>
1. Вы пишете сообщение ниже
2. Я перешлю его администратору
3. Администратор ответит вам в этот чат

<b>Напишите ваше сообщение:</b>
<i>Постарайтесь описать вопрос максимально подробно</i>"""

    await message.answer(
        contact_text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отменить отправку")]],
            resize_keyboard=True
        )
    )


# Отмена отправки сообщения админу
@router.message(OrderState.waiting_for_contact, F.text == "❌ Отменить отправку")
async def cancel_contact(message: Message, state: FSMContext):
    """Отмена отправки сообщения админу"""
    await state.clear()
    await message.answer(
        "❌ Отправка сообщения отменена.",
        reply_markup=ReplyKeyboardRemove()
    )

    if message.from_user.id == config.ADMIN_ID:
        from admin.admin_handlers import create_admin_menu
        await message.answer("Выберите действие:", reply_markup=create_admin_menu())
    else:
        await message.answer("Выберите действие:", reply_markup=create_main_menu())


# Обработка сообщения админу
@router.message(OrderState.waiting_for_contact, F.text)
async def handle_contact_message(message: Message, state: FSMContext):
    """Обработка сообщения админу"""
    user_message = message.text.strip()

    if len(user_message) < 5:
        await message.answer("❌ Сообщение слишком короткое. Напишите хотя бы 5 символов.")
        return

    # Отправляем сообщение админу
    admin_message = f"""<b>📩 НОВОЕ СООБЩЕНИЕ ОТ ПОЛЬЗОВАТЕЛЯ</b>

<b>👤 От:</b> @{message.from_user.username or 'без username'} (ID: {message.from_user.id})
<b>📝 Сообщение:</b>
{html_escape(user_message)}

<b>💬 Ответить:</b> Напишите сообщение пользователю @{message.from_user.username or message.from_user.id}"""

    try:
        await bot.send_message(
            config.ADMIN_ID,
            admin_message,
            parse_mode="HTML"
        )

        await message.answer(
            "✅ <b>Ваше сообщение отправлено администратору!</b>\n\n"
            "Ответ придет вам в этот чат. Обычно время ответа - в течение 24 часов.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )

        logger.info(f"Сообщение от пользователя {message.from_user.id} отправлено админу")

    except Exception as e:
        await message.answer(
            "❌ <b>Не удалось отправить сообщение администратору</b>\n\n"
            "Попробуйте позже или напишите напрямую: " + html_escape(config.SUPPORT_CHANNEL),
            parse_mode="HTML"
        )
        logger.error(f"Ошибка отправки сообщения админу: {e}")

    await state.clear()

    if message.from_user.id == config.ADMIN_ID:
        from admin.admin_handlers import create_admin_menu
        await message.answer("Выберите действие:", reply_markup=create_admin_menu())
    else:
        await message.answer("Выберите действие:", reply_markup=create_main_menu())


# Запрос на связь с поддержкой из кнопки
@router.callback_query(F.data.startswith("support_"))
async def handle_support_request(callback: types.CallbackQuery):
    """Обработка запроса на связь с поддержкой из кнопки"""
    try:
        order_id = int(callback.data.split('_')[1])

        support_text = f"""<b>📞 КОНТАКТНАЯ ИНФОРМАЦИЯ</b>

<b>По заказу #{order_id} вы можете:</b>

<code>1. 📱 НАПИСАТЬ АДМИНИСТРАТОРУ</code>
Нажмите кнопку "👨‍💻 Связаться" в меню

<code>2. 📢 КАНАЛ ПОДДЕРЖКИ</code>
{config.SUPPORT_CHANNEL}

<code>3. 💬 ЗАДАТЬ УТОЧНЯЮЩИЙ ВОПРОС</code>
Используйте кнопку "Задать вопрос"

<b>⏱️ Время ответа:</b>
• Обычные вопросы: в течение 24 часов
• Срочные вопросы: укажите в сообщении "СРОЧНО"

<b>📋 Что указать при обращении:</b>
• Номер заказа: #{order_id}
• Ваш вопрос или проблему"""

        await callback.message.answer(support_text, parse_mode="HTML")
        await callback.answer("✅ Информация о поддержке отправлена")

    except Exception as e:
        logger.error(f"Ошибка обработки запроса в поддержку: {e}")
        await callback.answer("❌ Ошибка при обработке запроса")


# ========== ОБРАБОТКА МЕНЮ ОЦЕНОК ==========
@router.callback_query(F.data.startswith("rate_menu_"))
async def handle_rate_menu(callback: types.CallbackQuery):
    """Обработка запроса на оценку (меню)"""
    try:
        order_id = int(callback.data.split('_')[2])

        keyboard = RatingHandler.create_rating_keyboard(order_id)

        await callback.message.answer(
            f"""<b>⭐ ОЦЕНКА КАЧЕСТВА УСЛУГИ</b>

<b>Заказ #{order_id}</b>

Пожалуйста, оцените качество полученной расшифровки.

<b>Критерии оценки:</b>
• ⭐ Точность и полнота анализа
• ⭐⭐ Понятность объяснений
• ⭐⭐⭐ Полезность рекомендаций
• ⭐⭐⭐⭐ Скорость ответа
• ⭐⭐⭐⭐⭐ Общее впечатление

<b>Выберите количество звезд:</b>""",
            parse_mode="HTML",
            reply_markup=keyboard
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка отображения меню оценки: {e}")
        await callback.answer("❌ Ошибка при отображении меню оценки")


# ========== ОБРАБОТКА ОЦЕНОК ==========
@router.callback_query(F.data.startswith("rate_"))
async def handle_rating_callback(callback: types.CallbackQuery):
    """Обработка оценки от пользователя"""
    try:
        # Извлекаем данные из callback_data: rate_123_5
        parts = callback.data.split('_')
        if len(parts) != 3:
            await callback.answer("❌ Ошибка оценки")
            return

        order_id = int(parts[1])
        rating = int(parts[2])

        if rating < 1 or rating > 5:
            await callback.answer("❌ Некорректная оценка")
            return

        # Сохраняем оценку в БД
        success = db.save_rating(order_id, rating)

        if success:
            # Получаем информацию о заказе
            order = db.get_order_by_id(order_id)
            if order:
                user_id, username = order[1], order[2]

                # Уведомляем админа
                admin_message = f"""<b>⭐ НОВАЯ ОЦЕНКА ЗАКАЗА #{order_id}</b>

<b>👤 Клиент:</b> @{username or 'без имени'} (ID: {user_id})
<b>⭐ Оценка:</b> {'⭐' * rating} ({rating}/5)
<b>📅 Дата:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}

<b>Спасибо за обратную связь!</b>
Ваше мнение помогает нам улучшать качество сервиса."""

                await bot.send_message(
                    config.ADMIN_ID,
                    admin_message,
                    parse_mode="HTML"
                )

            await callback.message.edit_text(
                f"""<b>✅ ОЦЕНКА ПРИНЯТА!</b>

<b>Вы поставили оценку:</b> {'⭐' * rating} ({rating}/5)

<b>Спасибо за ваше мнение!</b>
Ваша обратная связь помогает нам становиться лучше.

<b>💡 Если у вас остались вопросы</b>
• Задайте уточняющий вопрос
• Обратитесь в поддержку
• Создайте новый заказ для консультации""",
                parse_mode="HTML"
            )

            await callback.answer(f"Оценка {rating} ⭐ сохранена!")
        else:
            await callback.answer("❌ Ошибка при сохранении оценки")

    except Exception as e:
        logger.error(f"Ошибка обработки оценки: {e}")
        await callback.answer("❌ Ошибка при обработке оценки")


# ========== ОБРАБОТКА НОВЫХ ДОКУМЕНТОВ ДЛЯ ЗАКАЗОВ, ГДЕ НУЖНЫ НОВЫЕ ДОКУМЕНТЫ ==========

# Пользователь сообщил, что загрузил новые документы
@router.message(lambda message: message.text == "✅ Документы загружены")
async def handle_new_docs_uploaded(message: Message, state: FSMContext):
    """Пользователь сообщил, что загрузил новые документы"""
    try:
        # Ищем активный заказ пользователя со статусом needs_new_docs
        cursor = db.conn.cursor()
        cursor.execute('''
            SELECT id FROM orders 
            WHERE user_id = ? AND status = 'needs_new_docs'
            ORDER BY updated_at DESC 
            LIMIT 1
        ''', (message.from_user.id,))

        order = cursor.fetchone()

        if not order:
            # Проверяем, есть ли заказ в состоянии
            data = await state.get_data()
            order_id = data.get('order_id')

            if order_id:
                # Получаем заказ по ID
                cursor.execute('SELECT * FROM orders WHERE id = ? AND user_id = ?',
                               (order_id, message.from_user.id))
                order = cursor.fetchone()

            if not order:
                await message.answer(
                    "❌ У вас нет активного запроса на новые документы.\n\n"
                    "Если вы отправили документы ранее, подождите ответа специалиста.",
                    reply_markup=ReplyKeyboardRemove()
                )
                return

        order_id = order[0]

        # Проверяем, были ли загружены новые документы
        # Получаем последние уточнения пользователя
        cursor.execute('''
            SELECT COUNT(*) FROM clarifications 
            WHERE order_id = ? AND user_id = ? AND is_from_user = TRUE
            AND message_type IN ('photo', 'document')
            AND sent_at > (
                SELECT MAX(sent_at) FROM clarifications 
                WHERE order_id = ? AND is_admin_request = TRUE
            )
        ''', (order_id, message.from_user.id, order_id))

        new_docs_count = cursor.fetchone()[0]

        if new_docs_count == 0:
            await message.answer(
                "⚠️ <b>Вы не отправили новые документы.</b>\n\n"
                "Пожалуйста, отправьте фото или файлы документов перед нажатием этой кнопки.",
                parse_mode="HTML",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="❌ Отменить")]],
                    resize_keyboard=True
                )
            )
            return

        # Обновляем статус заказа на ожидание обработки
        cursor.execute('''
            UPDATE orders 
            SET status = 'pending', updated_at = CURRENT_TIMESTAMP,
                clarification_count = clarification_count + 1
            WHERE id = ?
        ''', (order_id,))

        # Добавляем запись о загрузке новых документов
        cursor.execute('''
            INSERT INTO clarifications (order_id, user_id, message_text, is_from_user)
            VALUES (?, ?, ?, TRUE)
        ''', (order_id, message.from_user.id, f"Пользователь загрузил {new_docs_count} новых документов",))

        db.conn.commit()

        # Уведомляем пользователя
        await message.answer(
            f"""✅ <b>НОВЫЕ ДОКУМЕНТЫ ПРИНЯТЫ!</b>

Спасибо за загрузку новых документов к заказу #{order_id}.

<b>📋 Что дальше:</b>
• Ваши документы переданы специалисту на повторный анализ
• Время обработка: до 24 часов
• Ответ придет в этот чат

<b>🔄 Статус заказа:</b> В обработке
<b>📅 Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}

<code>Если у вас есть дополнительные вопросы, напишите их в чат.</code>""",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )

        # Уведомляем админа
        try:
            username = message.from_user.username or "без username"

            await bot.send_message(
                config.ADMIN_ID,
                f"""🔄 <b>НОВЫЕ ДОКУМЕНТЫ ПОЛУЧЕНЫ</b>

<b>Заказ:</b> #{order_id}
<b>От:</b> @{username} (ID: {message.from_user.id})
<b>Новых документов:</b> {new_docs_count}
<b>Статус:</b> Передан на повторную обработку

<b>🔧 Действия:</b>
• Ответить: /send_{order_id} [текст]
• Быстрый ответ: /template1_{order_id}
• Просмотреть заказ: /order_{order_id}""",
                parse_mode="HTML"
            )

            logger.info(f"Пользователь {message.from_user.id} загрузил новые документы для заказа #{order_id}")

        except Exception as e:
            logger.error(f"Ошибка уведомления админа о новых документах: {e}")

        # Возвращаем пользователя в главное меню
        await asyncio.sleep(1)

        if message.from_user.id == config.ADMIN_ID:
            from admin.admin_handlers import create_admin_menu
            await message.answer("Выберите действие:", reply_markup=create_admin_menu())
        else:
            await message.answer("Выберите действие:", reply_markup=create_main_menu())

        await state.clear()

    except Exception as e:
        await message.answer(
            f"❌ Ошибка обработки документов: {str(e)[:200]}",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.error(f"Ошибка обработки новых документов: {e}")


# Обработка документов для заказов, где требуются новые документы
@router.message(F.photo | F.document | (F.text & ~F.text.in_([
    "🩺 Создать заказ", "📋 Мои заказы", "👨‍⚕️ О сервисе",
    "👨‍💻 Связаться", "👥 Пригласить друга", "🏠 Главное меню",
    "❌ Отменить", "✅ Документы загружены",
    # Команды админа
    "📊 Статистика", "📋 Все заказы", "⏳ Ожидающие", "💾 Бэкап",
    "🎫 Промокоды", "👥 Рефералы", "📝 Шаблоны"
])))
async def handle_docs_for_order_needs_new_docs(message: Message, state: FSMContext):
    """Обработка документов для заказов, где требуются новые документы"""
    try:
        # Сначала проверяем команды, которые обрабатываются другими хендлерами
        if message.text in [
            "🩺 Создать заказ", "📋 Мои заказы", "👨‍⚕️ О сервисе",
            "👨‍💻 Связаться", "👥 Пригласить друга", "🏠 Главное меню",
            "❌ Отменить", "✅ Документы загружены",
            "📊 Статистика", "📋 Все заказы", "⏳ Ожидающие", "💾 Бэкап",
            "🎫 Промокоды", "👥 Рефералы", "📝 Шаблоны"
        ]:
            return  # Пропускаем, эти команды обрабатываются другими хендлерами

        # Проверяем, есть ли у пользователя заказ со статусом needs_new_docs
        cursor = db.conn.cursor()
        cursor.execute('''
            SELECT id FROM orders 
            WHERE user_id = ? AND status = 'needs_new_docs'
            LIMIT 1
        ''', (message.from_user.id,))

        result = cursor.fetchone()

        if not result:
            # У пользователя нет заказа, требующего новые документы
            return

        order_id = result[0]

        # Обрабатываем фото
        if message.photo:
            is_valid, error_msg = await DocumentValidator.validate_photo(message)
            if not is_valid:
                await message.answer(f"⚠️ {error_msg}")
                return

            # Сохраняем документ как уточнение
            file_id = message.photo[-1].file_id
            caption = message.caption or "Новое фото документа"

            db.add_clarification(
                order_id=order_id,
                user_id=message.from_user.id,
                message_text=caption,
                message_type="photo",
                file_id=file_id,
                is_from_user=True
            )

            await message.answer(
                f"✅ Фото сохранено для заказа #{order_id}\n\n"
                f"<i>После загрузки всех документов нажмите кнопку «✅ Документы загружены»</i>",
                parse_mode="HTML"
            )
            return

        # Обрабатываем документы
        elif message.document:
            is_valid, error_msg = await DocumentValidator.validate_document(message)
            if not is_valid:
                await message.answer(f"⚠️ {error_msg}")
                return

            # Сохраняем документ как уточнение
            file_id = message.document.file_id
            caption = message.caption or f"Новый документ: {message.document.file_name or 'файл'}"

            # Определяем тип документа
            mime_type = message.document.mime_type
            doc_type = DocumentValidator.ALLOWED_MIME_TYPES.get(mime_type, DocumentType.OTHER)

            db.add_clarification(
                order_id=order_id,
                user_id=message.from_user.id,
                message_text=caption,
                message_type=doc_type.value,
                file_id=file_id,
                is_from_user=True
            )

            await message.answer(
                f"✅ Документ сохранен для заказа #{order_id}\n\n"
                f"<i>После загрузки всех документов нажмите кнопку «✅ Документы загружены»</i>",
                parse_mode="HTML"
            )
            return

        # Обрабатываем текстовые сообщения (вопросы по новым документам)
        elif message.text and message.text != "❌ Отменить":
            # Проверяем, не является ли это командой
            if message.text.startswith('/'):
                return  # Пропускаем команды

            # Сохраняем текстовое уточнение
            db.add_clarification(
                order_id=order_id,
                user_id=message.from_user.id,
                message_text=message.text,
                is_from_user=True
            )

            await message.answer(
                f"✅ Вопрос сохранен для заказа #{order_id}\n\n"
                f"<i>Специалист получит ваш вопрос вместе с новыми документами.</i>",
                parse_mode="HTML"
            )
            return

    except Exception as e:
        logger.error(f"Ошибка обработки документов для needs_new_docs: {e}")


# Отмена загрузки новых документов
@router.message(lambda message: message.text == "❌ Отменить")
async def handle_cancel_new_docs_upload(message: Message, state: FSMContext):
    """Отмена загрузки новых документов"""
    await state.clear()

    # Находим заказ пользователя со статусом needs_new_docs
    cursor = db.conn.cursor()
    cursor.execute('''
        SELECT id FROM orders 
        WHERE user_id = ? AND status = 'needs_new_docs'
        LIMIT 1
    ''', (message.from_user.id,))

    result = cursor.fetchone()

    if result:
        order_id = result[0]

        # Возвращаем заказ в предыдущий статус (скорее всего pending)
        cursor.execute('''
            UPDATE orders 
            SET status = 'pending', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (order_id,))

        # Добавляем запись об отмене
        cursor.execute('''
            INSERT INTO clarifications (order_id, user_id, message_text, is_from_user)
            VALUES (?, ?, ?, TRUE)
        ''', (order_id, message.from_user.id, "Пользователь отменил загрузку новых документов"))

        db.conn.commit()

        logger.info(f"Пользователь {message.from_user.id} отменил загрузку новых документов для заказа #{order_id}")

    await message.answer(
        "❌ Загрузка новых документов отменена.",
        reply_markup=ReplyKeyboardRemove()
    )

    await asyncio.sleep(0.5)

    if message.from_user.id == config.ADMIN_ID:
        from admin.admin_handlers import create_admin_menu
        await message.answer("Выберите действие:", reply_markup=create_admin_menu())
    else:
        await message.answer("Выберите действие:", reply_markup=create_main_menu())