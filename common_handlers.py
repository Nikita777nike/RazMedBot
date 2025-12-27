# handlers/common_handlers.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from utils.config import config
from database.database import db
from bot import bot, logger
from utils.agreement import AgreementHandler
from utils.keyboards import create_main_menu

router = Router()


# ========== ОБРАБОТКА СОГЛАШЕНИЯ ==========
@router.callback_query(F.data == "agreement_accept")
async def handle_agreement_accept(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь принимает соглашение"""
    try:
        user_id = callback.from_user.id

        # Записываем факт принятия соглашения
        db.record_agreement_acceptance(
            user_id=user_id,
            agreement_version="2.1",
            ip_info=f"telegram:{callback.from_user.id}"
        )

        # Обновляем заказ, если он есть
        cursor = db.conn.cursor()
        cursor.execute('''
            UPDATE orders 
            SET agreement_accepted = TRUE, agreement_version = '2.1'
            WHERE user_id = ? AND agreement_accepted = FALSE
        ''', (user_id,))
        db.conn.commit()

        await callback.message.edit_text(
            "✅ <b>Соглашение принято!</b>\n\n"
            "Теперь вы можете создать заказ.\n\n"
            "Нажмите кнопку <b>🩺 Создать заказ</b> в меню.",
            parse_mode="HTML"
        )

        await callback.answer("Соглашение принято")

    except Exception as e:
        logger.error(f"Ошибка принятия соглашения: {e}")
        await callback.answer("❌ Ошибка при принятии соглашения")


@router.callback_query(F.data == "agreement_full")
async def handle_agreement_full(callback: types.CallbackQuery):
    """Показать полное соглашение"""
    try:
        full_text = AgreementHandler.get_full_agreement()
        keyboard = AgreementHandler.create_agreement_keyboard(include_full=False)

        await callback.message.edit_text(full_text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка отображения полного соглашения: {e}")
        await callback.answer("❌ Ошибка")


@router.callback_query(F.data == "agreement_reject")
async def handle_agreement_reject(callback: types.CallbackQuery):
    """Пользователь отказывается от соглашения"""
    try:
        await callback.message.edit_text(
            "❌ <b>Вы отказались от пользовательского соглашения.</b>\n\n"
            "Для использования сервиса необходимо принять соглашение.\n\n"
            "Если у вас есть вопросы, свяжитесь с поддержкой:\n"
            f"{config.SUPPORT_CHANNEL}",
            parse_mode="HTML"
        )
        await callback.answer("Соглашение отклонено")

    except Exception as e:
        logger.error(f"Ошибка отказа от соглашения: {e}")
        await callback.answer("❌ Ошибка")


# ========== ИНФОРМАЦИЯ О СЕРВИСЕ ==========
@router.message(F.text == "👨‍⚕️ О сервисе")
async def handle_about_service(message: Message):
    """Информация о сервисе"""
    about_text = f"""<b>👨‍⚕️ О СЕРВИСЕ RAZMEDBOT</b>

<code>──────────────────────────────</code>
<b>🤖 КАК ЭТО РАБОТАЕТ</b>
<code>──────────────────────────────</code>
<code>1. 📤 ЗАГРУЗКА ДОКУМЕНТОВ</code>
Вы загружаете медицинские документы

<code>2. 🤖 AI-АНАЛИЗ</code>
Наш ИИ проводит первичный анализ данных

<code>3. 👨‍⚕️ ПРОВЕРКА СПЕЦИАЛИСТОМ</code>
Медицинский специалист проверяет и дополняет анализ

<code>4. 📝 ДЕТАЛЬНАЯ РАСШИФРОВКА</code>
Вы получаете понятное объяснение ваших документов

<code>──────────────────────────────</code>
<b>🎯 ЧТО МЫ ДЕЛАЕМ</b>
<code>──────────────────────────────</code>
✅ <b>Объясняем медицинские термины</b>
✅ <b>Расшифровываем анализы</b>
✅ <b>Интерпретируем результаты исследований</b>
✅ <b>Помогаем понять врачебные заключения</b>

<code>──────────────────────────────</code>
<b>🚫 ЧЕГО МЫ НЕ ДЕЛАЕМ</b>
<code>──────────────────────────────</code>
❌ <b>Не ставим диагнозы</b>
❌ <b>Не назначаем лечение</b>
❌ <b>Не заменяем врача</b>
❌ <b>Не консультируем по острым состояниям</b>

<code>──────────────────────────────</code>
<b>📊 С КАКИМИ ДОКУМЕНТАМИ РАБОТАЕМ</b>
<code>──────────────────────────────</code>
• 📈 Лабораторные анализы крови/мочи
• 🏥 Результаты УЗИ, МРТ, КТ, рентгена
• 💓 Кардиограммы (ЭКГ), Холтер
• 📄 Врачебные заключения и выписки
• 🔬 Протоколы исследований и операций

<code>──────────────────────────────</code>
<b>⏱️ СРОКИ И ГАРАНТИИ</b>
<code>──────────────────────────────</code>
• Максимальное время ответа: 24 часа
• Возможность уточняющих вопросов: 24 часа после ответа
• Конфиденциальность данных гарантирована
• Возврат средств при недоступности услуги

<code>──────────────────────────────</code>
<b>👤 ИСПОЛНИТЕЛЬ</b>
<code>──────────────────────────────</code>
<b>Исполнитель:</b> {config.SELF_EMPLOYED_NAME}
<b>Статус:</b> Медицинский специалист
<b>ИНН:</b> {config.SELF_EMPLOYED_INN}

<b>Поддержка:</b> {config.SUPPORT_CHANNEL}"""

    await message.answer(about_text, parse_mode="HTML")


# ========== МОИ ЗАКАЗЫ ==========
@router.message(F.text == "📋 Мои заказы")
async def handle_my_orders(message: Message):
    """Показать заказы пользователя"""
    try:
        orders = db.get_user_orders(message.from_user.id, limit=10)

        if not orders:
            await message.answer(
                "📭 У вас пока нет заказов.\n\n"
                "Создайте первый заказ с помощью кнопки <b>🩺 Создать заказ</b>",
                parse_mode="HTML"
            )
            return

        text_lines = []
        text_lines.append(f"<b>📋 ВАШИ ЗАКАЗЫ ({len(orders)})</b>\n")
        text_lines.append("<i>Сначала последние ↓</i>\n")

        for order in orders:
            order_id = order[0]
            service_type = order[8]
            status = order[9]
            created_at = order[10]
            price = order[14]

            # Эмодзи для статуса
            status_emoji = {
                'pending': '⏳',
                'processing': '🔄',
                'completed': '✅',
                'paid': '💰',
                'cancelled': '❌',
                'awaiting_clarification': '❓',
                'needs_new_docs': '📎'
            }.get(status, '📝')

            # Дата и время
            datetime_str = "н/д"
            if created_at:
                if isinstance(created_at, str):
                    datetime_str = created_at[:16]
                else:
                    try:
                        datetime_str = created_at.strftime('%d.%m %H:%M')
                    except:
                        datetime_str = "н/д"

            short_service = service_type[:30] + "..." if len(service_type) > 30 else service_type

            text_lines.append(f"<b>{status_emoji} #{order_id} • {datetime_str}</b>")
            text_lines.append(f"📋 {short_service}")
            text_lines.append(f"💰 {price}₽")
            text_lines.append(f"📊 Статус: <b>{status}</b>")

            # Добавляем действия в зависимости от статуса
            if status == OrderStatus.COMPLETED:
                text_lines.append("🔧 Можно задать уточняющий вопрос")
            elif status == OrderStatus.NEEDS_NEW_DOCS:
                text_lines.append("🔧 Нужно загрузить новые документы")

            text_lines.append("─" * 30 + "\n")

        text = "\n".join(text_lines)
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка отображения заказов пользователя: {e}")
        await message.answer(f"❌ Ошибка при получении заказов: {str(e)[:100]}")


# ========== СОГЛАШЕНИЕ ==========
@router.message(F.text == "📜 Соглашение")
async def handle_agreement(message: Message):
    """Показать соглашение"""
    text = AgreementHandler.get_short_agreement()
    keyboard = AgreementHandler.create_agreement_keyboard()

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ========== ОБРАБОТКА НЕИЗВЕСТНЫХ КОМАНД ==========
@router.message()
async def handle_unknown(message: Message):
    """Обработка неизвестных сообщений"""
    if message.text and message.text.startswith('/'):
        # Игнорируем неизвестные команды
        return

    # Для обычных сообщений показываем меню
    if message.from_user.id == config.ADMIN_ID:
        from admin.admin_handlers import create_admin_menu
        await message.answer("Выберите действие из меню:", reply_markup=create_admin_menu())
    else:
        await message.answer("Выберите действие из меню:", reply_markup=create_main_menu())