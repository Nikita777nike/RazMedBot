# handlers/payment_handlers.py - исправленная версия
import asyncio
import uuid
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    PreCheckoutQuery,
    SuccessfulPayment,
    ContentType,
    LabeledPrice,
    ReplyKeyboardRemove
)
from aiogram.enums import ContentType

from utils.config import config
from utils.keyboards import create_docs_questions_keyboard
from database.database import db
from models.enums import OrderStatus
from handlers.user_handlers import OrderState

import logging

logger = logging.getLogger(__name__)

router = Router()


def html_escape(text: str) -> str:
    """Экранирование HTML-символов (дублируем из user_handlers)"""
    if not text:
        return ""
    return (text.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


async def send_invoice_to_user(user_id: int, order_id: int, price: int = 490, service_type: str = "", bot: Bot = None):
    """Отправка счета на оплату с поддержкой тестового режима"""

    # Тестовый режим платежей
    if config.PAYMENT_TEST_MODE:
        logger.info(f"📱 ТЕСТОВЫЙ РЕЖИМ: Заказ #{order_id}, услуга: {service_type}, цена: {price}₽")

        # Создаем invoice_payload для теста
        invoice_payload = f"test_order_{order_id}"

        # Сохраняем invoice_payload в БД
        db.set_invoice_payload(order_id, invoice_payload)

        # Имитируем успешный платеж
        await asyncio.sleep(1)

        success, processed_order_id = db.process_payment(
            invoice_payload=invoice_payload,
            provider_payment_id=f"test_payment_{order_id}",
            amount=config.TEST_PAYMENT_PRICE * 100
        )

        if success:
            return True, order_id
        return False, None

    # Реальный режим
    if not config.PROVIDER_TOKEN:
        logger.error("PROVIDER_TOKEN не настроен. Платежи недоступны.")
        return False, None

    try:
        invoice_payload = f"order_{order_id}_{uuid.uuid4().hex[:8]}"

        # Сохраняем invoice_payload в БД
        db.set_invoice_payload(order_id, invoice_payload)

        prices = [LabeledPrice(label=f"Расшифровка: {service_type}", amount=price * 100)]

        await bot.send_invoice(
            chat_id=user_id,
            title=f"Оплата заказа #{order_id}",
            description=f"Расшифровка медицинских документов: {service_type}",
            payload=invoice_payload,
            provider_token=config.PROVIDER_TOKEN,
            currency="RUB",
            prices=prices,
            start_parameter="razmed_order",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False,
            disable_notification=False,
            protect_content=False
        )

        logger.info(f"Счет отправлен для заказа #{order_id} (услуга: {service_type}, цена: {price}₽)")
        return True, order_id

    except Exception as e:
        logger.error(f"Ошибка отправки счета для заказа #{order_id}: {e}")
        return False, None


# ========== ОБРАБОТКА ПРЕДВАРИТЕЛЬНОГО ЗАПРОСА НА ОПЛАТУ ==========
@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """Обработка предварительного запроса на оплату"""
    await bot.answer_pre_checkout_query(
        pre_checkout_query_id=pre_checkout_query.id,
        ok=True
    )


# ========== ОБРАБОТКА УСПЕШНОЙ ОПЛАТЫ ==========
@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: Message, state: FSMContext, bot: Bot):
    """Обработка успешного платежа"""
    # В тестовом режиме этот обработчик не должен срабатывать
    if config.PAYMENT_TEST_MODE:
        return

    payment = message.successful_payment

    success, order_id = db.process_payment(
        invoice_payload=payment.invoice_payload,
        provider_payment_id=payment.provider_payment_charge_id,
        amount=payment.total_amount
    )

    if success and order_id:
        # Получаем данные о заказе
        order = db.get_order_by_id(order_id)
        if not order:
            await message.answer("❌ Ошибка: заказ не найден после оплаты")
            return

        service_type = order[8] if len(order) > 8 else "Не указано"
        price = payment.total_amount / 100
        needs_demographics = order[27] if len(order) > 27 else True  # needs_demographics

        # Сохраняем order_id в состоянии
        await state.update_data(order_id=order_id)

        # Проверяем, нужна ли демография
        if needs_demographics:
            await state.set_state(OrderState.waiting_for_demographics)

            # Уведомляем пользователя
            await message.answer(
                f"""✅ <b>Оплата прошла успешно!</b>

💎 Услуга: {service_type}
💰 Сумма: {price}₽
📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}

Теперь продолжим оформление заказа.""",
                parse_mode="HTML"
            )

            await asyncio.sleep(1)

            # Переходим к демографии
            await message.answer(
                f"""<b>👤 ШАГ 4 из 5: ОСНОВНАЯ ИНФОРМАЦИЯ</b>

[███░░] 4/5

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
                f"""✅ <b>Оплата прошла успешно!</b>

💎 Услуга: {service_type}
💰 Сумма: {price}₽

<b>📎 ШАГ 4 из 5: ДОКУМЕНТЫ И ВОПРОСЫ</b>

[███░░] 4/5

<b>📤 ЗАГРУЗКА ДОКУМЕНТОВ</b>

Для проведения качественной расшифровки необходимо 
загрузить медицинские документы.

<b>Принимаемые форматы:</b>
• 📸 Фотографии/скан-копии документов
• 📄 PDF файлы с результатами
• 📝 Документы Word (DOC/DOCX)

<b>После загрузки документов, опишите ваш вопрос ниже.</b>
<i>Чем подробнее описание, тем точнее будет расшифровка</i>

<code>──────────────────────────────</code>
<b>Загрузите документы и опишите вопрос, затем нажмите «✅ Отправить на обработку»</b>""",
                parse_mode="HTML",
                reply_markup=create_docs_questions_keyboard()
            )

        # Уведомляем админа
        await bot.send_message(
            config.ADMIN_ID,
            f"💰 ПЛАТЕЖ ПРИНЯТ! Заказ #{order_id} от @{message.from_user.username}\n"
            f"Услуга: {service_type}\nСумма: {price}₽\nСтатус: ожидает деталей",
        )

        logger.info(f"Платеж успешно обработан для заказа #{order_id}")
    else:
        await message.answer(
            "⚠️ <b>Ошибка обработки платежа</b>\nПожалуйста, свяжитесь с поддержкой: " + html_escape(
                config.SUPPORT_CHANNEL),
            parse_mode="HTML"
        )