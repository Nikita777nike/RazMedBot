# admin/admin_handlers.py
import asyncio
import json
import csv
import tempfile
import os
from datetime import datetime
from io import StringIO
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile
)
from aiogram.fsm.context import FSMContext

from utils.config import config
from database.database import db
from bot import bot, logger
from models.enums import OrderStatus, DiscountType

router = Router()


def create_admin_menu() -> ReplyKeyboardMarkup:
    """Создание меню администратора"""
    buttons = [
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📋 Все заказы")],
        [KeyboardButton(text="⏳ Ожидающие"), KeyboardButton(text="💾 Бэкап")],
        [KeyboardButton(text="🎫 Промокоды"), KeyboardButton(text="👥 Рефералы")],
        [KeyboardButton(text="📝 Шаблоны"), KeyboardButton(text="🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def html_escape(text: str) -> str:
    """Экранирование HTML-символов"""
    if not text:
        return ""
    return (text.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


# ========== СТАТИСТИКА ==========
@router.message(F.text == "📊 Статистика")
async def handle_statistics(message: Message):
    """Показать статистику"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        stats = db.get_statistics()

        # Формируем сообщение со статистикой
        stats_text = f"""<b>📊 СТАТИСТИКА СЕРВИСА</b>

<b>📈 ОБЩАЯ СТАТИСТИКА:</b>
• Всего заказов: {stats['total_orders']}
• Сегодня: {stats['today_orders']}
• Уникальных пользователей: {stats['unique_users']}
• Приняли соглашение: {stats['agreements_accepted']}

<b>📋 СТАТУСЫ ЗАКАЗОВ:</b>
• Ожидают ответа: {stats['pending_orders']}
• В обработке: {stats['completed_orders']}
• Уточняются: {stats['clarification_orders']}
• Нужны документы: {stats['new_docs_orders']}
• Оплачено: {stats['paid_orders']}

<b>💰 ФИНАНСЫ:</b>
• Общая выручка: {stats['total_revenue']}₽
• Средний чек: {stats['avg_price']}₽
• Сумма скидок: {stats['total_discounts']}₽
• Промокоды: {stats['promo_discounts']:.2f}₽
• Неотчитано в налоговой: {stats['unreported_amount']}₽ ({stats['unreported_payments']} платежей)

<b>⭐ ОЦЕНКИ:</b>
• Всего оценок: {stats['total_ratings']}
• Средняя оценка: {stats['avg_rating']:.1f}/5"""

        # Распределение оценок
        if stats['rating_distribution']:
            stats_text += "\n<b>📊 РАСПРЕДЕЛЕНИЕ ОЦЕНОК:</b>"
            for rating, count in stats['rating_distribution']:
                stars = "⭐" * rating
                stats_text += f"\n{stars}: {count}"

        # Статистика по уточнениям
        stats_text += f"""
<b>❓ УТОЧНЕНИЯ:</b>
• Всего уточняющих вопросов: {stats['total_clarifications']}

<b>🎫 ПРОМОКОДЫ:</b>
• Всего промокодов: {stats['total_promo_codes']}
• Использований: {stats['promo_uses']}
• Скидка по промокодам: {stats['promo_discounts']:.2f}₽

<b>📋 ПО ТИПАМ УСЛУГ:</b>"""

        # Статистика по типам услуг
        if stats['service_stats']:
            for service_type, count, avg_price, total_revenue in stats['service_stats']:
                stats_text += f"\n• {service_type}: {count} зак., {avg_price:.0f}₽ средн., {total_revenue}₽ всего"

        # Статистика по дням
        if stats['daily_stats']:
            stats_text += "\n\n<b>📅 ЗАКАЗЫ ПО ДНЯМ (7 дней):</b>"
            for date_str, count, revenue in stats['daily_stats']:
                stats_text += f"\n• {date_str}: {count} зак., {revenue or 0}₽"

        # Реферальная статистика
        try:
            referral_stats = db.get_all_referrals_stats()
            stats_text += f"""

<b>👥 РЕФЕРАЛЬНАЯ СИСТЕМА:</b>
• Всего рефералов: {referral_stats['total_referrals']}
• Завершенных заказов: {referral_stats['completed_referrals']}
• Выплачено бонусов: {referral_stats['total_bonuses']:.2f}₽
• Предоставлено скидок: {referral_stats['total_discounts']:.2f}₽"""
        except Exception as e:
            logger.error(f"Ошибка получения реферальной статистики: {e}")

        # Команды для админа
        stats_text += """

<b>🔧 КОМАНДЫ:</b>
<code>/export_stats</code> - экспорт в CSV
<code>/mark_tax_reported [order_id]</code> - отметить как отчитанный
<code>/backup_db</code> - создать резервную копию БД
<code>/cleanup_old</code> - очистить старые данные"""

        await message.answer(stats_text, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка получения статистики: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка получения статистики: {e}")


# ========== ВСЕ ЗАКАЗЫ ==========
@router.message(F.text == "📋 Все заказы")
async def handle_all_orders(message: Message):
    """Показать все заказы (последние сверху)"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Получаем заказы с сортировкой по убыванию (новые сверху)
        cursor = db.conn.cursor()
        cursor.execute('''
            SELECT id, user_id, username, service_type, status, 
                   created_at, price, original_price 
            FROM orders 
            ORDER BY created_at DESC 
            LIMIT 20
        ''')
        orders = cursor.fetchall()

        if not orders:
            await message.answer("📭 Нет заказов", reply_markup=create_admin_menu())
            return

        text_lines = []
        text_lines.append(f"<b>📋 ПОСЛЕДНИЕ ЗАКАЗЫ ({len(orders)})</b>\n")
        text_lines.append("<i>Новые заказы вверху ↓</i>\n")

        for order in orders:
            order_id, user_id, username, service_type, status, created_at, price, original_price = order

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
                    try:
                        dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                        datetime_str = dt.strftime('%d.%m %H:%M')
                    except:
                        datetime_str = created_at[:16]
                else:
                    try:
                        datetime_str = created_at.strftime('%d.%m %H:%M')
                    except:
                        datetime_str = "н/д"

            # Сокращаем текст
            short_service = service_type[:25] + "..." if len(service_type) > 25 else service_type
            short_username = username[:15] if username else "без username"

            # Скидка
            discount = original_price - price if original_price and price else 0

            text_lines.append(f"<b>{status_emoji} #{order_id} • {datetime_str}</b>")
            text_lines.append(f"👤 @{short_username} (ID: {user_id})")
            text_lines.append(f"📋 {short_service}")
            text_lines.append(f"💰 {price}₽ (скидка: {discount}₽)")
            text_lines.append(f"📊 Статус: <b>{status}</b>")
            text_lines.append(f"🔧 /send_{order_id} /complete_{order_id} /cancel_{order_id}")
            text_lines.append("─" * 40)
            text_lines.append("")

        text = "\n".join(text_lines)
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка отображения всех заказов: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())


# ========== ОЖИДАЮЩИЕ ЗАКАЗЫ ==========
@router.message(F.text == "⏳ Ожидающие")
async def handle_pending_orders(message: Message):
    """Показать ожидающие заказы (последние сверху)"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Получаем ожидающие заказы с сортировкой по убыванию
        cursor = db.conn.cursor()
        cursor.execute('''
            SELECT id, user_id, username, service_type, status, 
                   created_at, price, age, sex, questions
            FROM orders 
            WHERE status IN ('pending', 'processing', 'awaiting_clarification', 'needs_new_docs')
            ORDER BY created_at DESC 
            LIMIT 20
        ''')
        orders = cursor.fetchall()

        if not orders:
            await message.answer("✅ Нет ожидающих заказов", reply_markup=create_admin_menu())
            return

        text_lines = []
        text_lines.append(f"<b>⏳ ОЖИДАЮЩИЕ ОБРАБОТКИ ({len(orders)})</b>\n")
        text_lines.append("<i>Новые заказы вверху ↓</i>\n")

        for order in orders:
            order_id, user_id, username, service_type, status, created_at, price, age, sex, questions = order

            # Эмодзи для статуса
            status_emoji = {
                'pending': '⏳',
                'processing': '🔄',
                'awaiting_clarification': '❓',
                'needs_new_docs': '📎'
            }.get(status, '📝')

            # Дата и время
            datetime_str = "н/д"
            if created_at:
                if isinstance(created_at, str):
                    try:
                        dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                        datetime_str = dt.strftime('%d.%m %H:%M')
                    except:
                        datetime_str = created_at[:16]
                else:
                    try:
                        datetime_str = created_at.strftime('%d.%m %H:%M')
                    except:
                        datetime_str = "н/д"

            # Демография
            demographics = ""
            if age:
                demographics = f"{age} лет"
            if sex and sex != "Не указан":
                if demographics:
                    demographics += f", {sex}"
                else:
                    demographics = sex
            if not demographics:
                demographics = "не указано"

            # Вопрос
            short_question = questions[:50] + "..." if questions and len(questions) > 50 else (
                        questions or "нет вопроса")

            # Сокращаем
            short_service = service_type[:30] + "..." if len(service_type) > 30 else service_type
            short_username = username[:15] if username else "без username"

            text_lines.append(f"<b>{status_emoji} #{order_id} • {datetime_str} • {status}</b>")
            text_lines.append(f"👤 @{short_username} (ID: {user_id})")
            text_lines.append(f"📋 {short_service}")
            text_lines.append(f"💰 {price}₽")
            text_lines.append(f"👤 {demographics}")
            text_lines.append(f"❓ {short_question}")
            text_lines.append(f"🔧 /send_{order_id} /complete_{order_id} /cancel_{order_id} /redocs_{order_id}")
            text_lines.append("─" * 40)
            text_lines.append("")

        text = "\n".join(text_lines)
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка отображения ожидающих заказов: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())


# ========== СОЗДАНИЕ БЭКАПА ==========
@router.message(F.text == "💾 Бэкап")
async def handle_backup(message: Message):
    """Создать резервную копию БД"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        await message.answer("🔄 Создание резервной копии БД...", reply_markup=create_admin_menu())

        success = db.backup()

        if success:
            # Получаем список последних бэкапов
            backups = sorted([f for f in os.listdir(config.BACKUP_DIR)
                              if f.startswith('backup_') and f.endswith('.db')])

            if backups:
                latest = backups[-1]
                file_size = os.path.getsize(os.path.join(config.BACKUP_DIR, latest))
                file_size_mb = file_size / (1024 * 1024)

                await message.answer(
                    f"✅ Бэкап создан успешно!\n"
                    f"Файл: {latest}\n"
                    f"Размер: {file_size_mb:.2f} МБ\n"
                    f"Всего бэкапов: {len(backups)}",
                    reply_markup=create_admin_menu()
                )
            else:
                await message.answer("✅ Бэкап создан успешно!", reply_markup=create_admin_menu())
        else:
            await message.answer("❌ Ошибка создания бэкапа", reply_markup=create_admin_menu())

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка создания бэкапа: {e}")


# ========== ПРОМОКОДЫ ==========
@router.message(F.text == "🎫 Промокоды")
async def handle_promo_codes_menu(message: Message):
    """Меню управления промокодами"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        promo_codes = db.get_all_promo_codes()

        if not promo_codes:
            text = """<b>🎫 УПРАВЛЕНИЕ ПРОМОКОДАМИ</b>

📭 Нет созданных промокодов.

<code>Для создания промокода используйте команду:</code>
<code>/create_promo [код] [percent/fixed] [значение] [использований] [описание]</code>

<b>Примеры:</b>
• <code>/create_promo SUMMER25 percent 25 100</code>
  → 25% скидка, 100 использований
• <code>/create_promo WELCOME500 fixed 500 -1</code>
  → 500₽ скидка, безлимит
• <code>/create_promo TEST10 percent 10 1 'Тестовый'</code>
  → 10% скидка, 1 использование, с описанием"""

            await message.answer(text, parse_mode="HTML")
            return

        text = "<b>🎫 СПИСОК ПРОМОКОДОВ</b>\n\n"

        for promo in promo_codes:
            promo_id, code, discount_type, discount_value, uses_left, valid_until, created_at, is_active, description = promo

            text += f"<b>🔸 {code}</b> {'✅' if is_active else '❌'}\n"

            if discount_type == 'percent':
                text += f"Скидка: <b>{discount_value}%</b>\n"
            else:
                text += f"Скидка: <b>{discount_value}₽</b>\n"

            if uses_left == -1:
                text += f"Использований: <b>∞</b>\n"
            elif uses_left > 0:
                text += f"Использований: <b>{uses_left}</b>\n"
            else:
                text += f"Использований: <b>0 (закончился)</b>\n"

            if description:
                text += f"Описание: {description}\n"

            text += f"ID: {promo_id}\n\n"

        text += """<b>📌 КОМАНДЫ:</b>
<code>/create_promo [код] [percent/fixed] [значение] [использований] [описание]</code>
<code>/deactivate_promo [код]</code> - деактивировать промокод
<code>/promo_stats</code> - статистика по промокодам"""

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка отображения промокодов: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())


# ========== РЕФЕРАЛЬНАЯ СИСТЕМА ==========
@router.message(F.text == "👥 Рефералы")
async def handle_referrals_menu(message: Message):
    """Меню управления реферальной системой"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        stats = db.get_all_referrals_stats()

        text = f"""<b>👥 СТАТИСТИКА РЕФЕРАЛЬНОЙ СИСТЕМЫ</b>

<b>Общая статистика:</b>
• Всего рефералов: {stats['total_referrals']}
• Завершенных заказов: {stats['completed_referrals']}
• Выплачено бонусов: {stats['total_bonuses']:.2f}₽
• Предоставлено скидок: {stats['total_discounts']:.2f}₽

<b>Топ-10 рефереров:</b>"""

        if stats['top_referrers']:
            for i, (referrer_id, count, total_bonus) in enumerate(stats['top_referrers'], 1):
                # Получаем username реферера
                cursor = db.conn.cursor()
                cursor.execute('SELECT username FROM orders WHERE user_id = ? LIMIT 1', (referrer_id,))
                result = cursor.fetchone()
                username = result[0] if result else f"ID: {referrer_id}"

                text += f"\n{i}. @{username}: {count} приглаш., бонус: {total_bonus or 0:.2f}₽"
        else:
            text += "\nНет данных о реферерах."

        text += f"""

<b>Настройки системы:</b>
• Бонус рефереру: {config.REFERRER_BONUS_PERCENT}% от заказа
• Скидка приглашенному: {config.REFERRED_DISCOUNT_PERCENT}%

<b>Команды:</b>
<code>/referral_stats [user_id]</code> - статистика по конкретному пользователю"""

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка отображения статистики рефералов: {e}")


# ========== ШАБЛОНЫ ==========
@router.message(F.text == "📝 Шаблоны")
async def handle_templates_menu(message: Message):
    """Меню управления шаблонами"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    templates = db.get_quick_templates()

    if not templates:
        text = """<b>📝 УПРАВЛЕНИЕ ШАБЛОНАМИ</b>

Нет сохраненных шаблонов.

<code>📌 КОМАНДЫ:</b>
<code>/template_add [название] [текст]</code> - добавить шаблон
<code>/template_edit [id] [новый текст]</code> - изменить текст шаблона
<code>/template_edit_name [id] [новое название]</code> - изменить название
<code>/template_del [id]</code> - удалить шаблон"""
    else:
        text = "<b>📝 СПИСОК ШАБЛОНОВ</b>\n\n"

        for template_id, name, template_text, created_at, updated_at in templates:
            text += f"<b>#{template_id} - {name}</b>\n"
            text += f"Текст: {template_text[:100]}...\n"
            text += f"Создан: {created_at}\n"
            text += f"Использовать: /use_template_{template_id}_[order_id]\n\n"

        text += """<b>📌 КОМАНДЫ:</b>
<code>/template_add [название] [текст]</code> - добавить шаблон
<code>/template_edit [id] [новый текст]</code> - изменить текст шаблона
<code>/template_edit_name [id] [новое название]</code> - изменить название
<code>/template_del [id]</code> - удалить шаблон"""

    await message.answer(text, parse_mode="HTML")


# ========== КОМАНДА АДМИН-МЕНЮ ==========
@router.message(F.text == "🏠 Главное меню")
async def show_main_menu_admin(message: Message, state: FSMContext):
    """Показать главное меню админа"""
    await state.clear()
    await message.answer("❌ Текущее действие отменено.", reply_markup=ReplyKeyboardRemove())

    await asyncio.sleep(0.5)
    await message.answer("🏠 Главное меню", reply_markup=create_admin_menu())


# ========== ОБРАБОТКА КОМАНД АДМИНА ==========

@router.message(lambda message: message.text and message.text.startswith('/send_'))
async def cmd_send_to_order(message: Message):
    """Ответить на заказ"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Извлекаем ID заказа из текста
        parts = message.text.split(' ', 1)
        if len(parts) < 2:
            await message.answer("❌ Формат: /send_[id] [ответ]\nПример: /send_123 Привет, вот ваш ответ...",
                                 reply_markup=create_admin_menu())
            return

        # Получаем ID заказа
        command_part = parts[0]  # /send_123
        answer_text = parts[1]  # весь остальной текст

        # Извлекаем ID из команды
        if not command_part.startswith('/send_'):
            await message.answer("❌ Формат: /send_[id] [ответ]", reply_markup=create_admin_menu())
            return

        try:
            order_id = int(command_part[6:])  # /send_123 -> 123
        except ValueError:
            await message.answer("❌ Неверный ID заказа", reply_markup=create_admin_menu())
            return

        # Получаем заказ
        order = db.get_order_by_id(order_id)
        if not order:
            await message.answer(f"❌ Заказ #{order_id} не найден", reply_markup=create_admin_menu())
            return

        user_id = order[1]  # user_id находится во втором столбце
        username = order[2] or "пользователь"

        # Проверяем, что ответ не пустой
        if not answer_text.strip():
            await message.answer("❌ Ответ не может быть пустым", reply_markup=create_admin_menu())
            return

        # Отправляем ответ пользователю с клавиатурой действий
        response_text = f"""<b>👨‍⚕️ ОТВЕТ НА ВАШ ЗАКАЗ #{order_id}</b>

<b>🤖 Наш AI-помощник проанализировал ваши документы, и медицинский специалист проверил ответ:</b>

{html_escape(answer_text)}

<b>🔬 Этот ответ включает:</b>
• 🤖 AI-анализ ваших документов
• 👨‍⚕️ Проверку и дополнения медицинского специалиста
• 📊 Сравнение с возрастными и половыми нормами

<b>📝 После получения ответа вы можете:</b>"""

        # Импортируем клавиатуру из пользовательских хендлеров
        from handlers.user_handlers import ClarificationHandler
        keyboard = ClarificationHandler.create_clarification_keyboard(order_id)

        await bot.send_message(user_id, response_text, parse_mode="HTML", reply_markup=keyboard)

        # Обновляем статус заказа
        db.update_order_status(order_id, OrderStatus.COMPLETED, admin_id=message.from_user.id)

        # Сохраняем ответ как уточнение (но от админа)
        db.add_clarification(
            order_id=order_id,
            user_id=message.from_user.id,
            message_text=answer_text,
            is_from_user=False
        )

        await message.answer(f"✅ Ответ отправлен пользователю @{username} (заказ #{order_id})",
                             reply_markup=create_admin_menu())
        logger.info(f"Админ отправил ответ на заказ #{order_id}")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка отправки ответа: {e}")


@router.message(lambda message: message.text and message.text.startswith('/complete_'))
async def cmd_complete_order(message: Message):
    """Завершить заказ"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Извлекаем ID заказа
        command_part = message.text.strip()

        if not command_part.startswith('/complete_'):
            await message.answer("❌ Формат: /complete_[id]", reply_markup=create_admin_menu())
            return

        try:
            order_id = int(command_part[10:])
        except ValueError:
            await message.answer("❌ Неверный ID заказа", reply_markup=create_admin_menu())
            return

        # Получаем заказ
        order = db.get_order_by_id(order_id)
        if not order:
            await message.answer(f"❌ Заказ #{order_id} не найден", reply_markup=create_admin_menu())
            return

        user_id = order[1]
        username = order[2] or "пользователь"
        status = order[9]

        # Проверяем, можно ли завершить заказ
        if status in [OrderStatus.COMPLETED, OrderStatus.CANCELLED]:
            await message.answer(f"❌ Заказ #{order_id} уже {status}", reply_markup=create_admin_menu())
            return

        # Обновляем статус
        success = db.update_order_status(order_id, OrderStatus.COMPLETED, admin_id=message.from_user.id)

        if not success:
            await message.answer(f"❌ Ошибка при завершении заказа #{order_id}", reply_markup=create_admin_menu())
            return

        # Отправляем уведомление пользователю
        user_message = f"""<b>✅ ВАШ ЗАКАЗ #{order_id} ЗАВЕРШЕН</b>

Благодарим вас за использование нашего сервиса!

<b>📝 После получения ответа вы можете:</b>
• Задать уточняющий вопрос (в течение 24 часов)
• Оценить качество услуги
• Обратиться в поддержку
• Создать новый заказ"""

        from handlers.user_handlers import ClarificationHandler
        keyboard = ClarificationHandler.create_simple_rating_keyboard(order_id)
        await bot.send_message(user_id, user_message, parse_mode="HTML", reply_markup=keyboard)

        await message.answer(
            f"✅ Заказ #{order_id} от @{username} завершен",
            reply_markup=create_admin_menu()
        )
        logger.info(f"Админ завершил заказ #{order_id}")

    except Exception as e:
        logger.error(f"Ошибка завершения заказа: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())


@router.message(lambda message: message.text and message.text.startswith('/cancel_'))
async def cmd_cancel_order(message: Message):
    """Отменить заказ"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Извлекаем ID заказа
        command_part = message.text.strip()

        if not command_part.startswith('/cancel_'):
            await message.answer("❌ Формат: /cancel_[id]", reply_markup=create_admin_menu())
            return

        try:
            order_id = int(command_part[8:])
        except ValueError:
            await message.answer("❌ Неверный ID заказа", reply_markup=create_admin_menu())
            return

        # Получаем заказ
        order = db.get_order_by_id(order_id)
        if not order:
            await message.answer(f"❌ Заказ #{order_id} не найден", reply_markup=create_admin_menu())
            return

        user_id = order[1]
        username = order[2] or "пользователь"
        status = order[9]

        # Проверяем, можно ли отменить заказ
        if status in [OrderStatus.CANCELLED, OrderStatus.COMPLETED]:
            await message.answer(f"❌ Заказ #{order_id} уже {status}", reply_markup=create_admin_menu())
            return

        # Обновляем статус
        success = db.update_order_status(order_id, OrderStatus.CANCELLED, admin_id=message.from_user.id)

        if not success:
            await message.answer(f"❌ Ошибка при отмене заказа #{order_id}", reply_markup=create_admin_menu())
            return

        # Отправляем уведомление пользователю
        user_message = f"""<b>❌ ВАШ ЗАКАЗ #{order_id} ОТМЕНЕН</b>

Заказ был отменен администратором.

Если у вас есть вопросы по этому решению, пожалуйста, свяжитесь с поддержкой:
{config.SUPPORT_CHANNEL}

<b>Вы можете:</b>
• Связаться с поддержкой для выяснения причин
• Создать новый заказ"""

        await bot.send_message(user_id, user_message, parse_mode="HTML")

        await message.answer(
            f"✅ Заказ #{order_id} от @{username} отменен",
            reply_markup=create_admin_menu()
        )
        logger.info(f"Админ отменил заказ #{order_id}")

    except Exception as e:
        logger.error(f"Ошибка отмены заказа: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())


@router.message(lambda message: message.text and message.text.startswith('/redocs_'))
async def cmd_request_new_docs(message: Message):
    """Запросить новые документы"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Извлекаем ID заказа и причину
        parts = message.text.split(' ', 1)
        if len(parts) < 2:
            await message.answer("❌ Формат: /redocs_[id] [причина]\nПример: /redocs_123 Плохо читается",
                                 reply_markup=create_admin_menu())
            return

        command_part = parts[0]  # /redocs_123
        reason = parts[1]  # причина

        if not command_part.startswith('/redocs_'):
            await message.answer("❌ Формат: /redocs_[id] [причина]", reply_markup=create_admin_menu())
            return

        try:
            order_id = int(command_part[8:])  # /redocs_123 -> 123
        except ValueError:
            await message.answer("❌ Неверный ID заказа", reply_markup=create_admin_menu())
            return

        # Получаем заказ
        order = db.get_order_by_id(order_id)
        if not order:
            await message.answer(f"❌ Заказ #{order_id} не найден", reply_markup=create_admin_menu())
            return

        user_id = order[1]
        username = order[2] or "пользователь"

        # Помечаем заказ как нуждающийся в новых документах
        success = db.mark_order_needs_new_docs(order_id, reason, message.from_user.id)

        if not success:
            await message.answer(f"❌ Ошибка при запросе новых документов для заказа #{order_id}",
                                 reply_markup=create_admin_menu())
            return

        # Отправляем уведомление пользователю
        user_message = f"""<b>📎 НУЖНЫ НОВЫЕ ДОКУМЕНТЫ</b>

<b>По вашему заказу #{order_id} требуется загрузить новые документы.</b>

<b>Причина:</b>
{html_escape(reason)}

<b>Что делать:</b>
1. Загрузите новые, более качественные документы (фото/сканы)
2. После загрузки нажмите кнопку «✅ Документы загружены»
3. Мы обработаем ваш заказ заново

<b>⚠️ Важно:</b>
• Документы должны быть четкими и читаемыми
• Можно загружать фото, PDF, Word документы
• После загрузки обязательно нажмите кнопку подтверждения"""

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Документы загружены")],
                [KeyboardButton(text="❌ Отменить")]
            ],
            resize_keyboard=True
        )

        await bot.send_message(user_id, user_message, parse_mode="HTML", reply_markup=keyboard)

        await message.answer(
            f"✅ Запрос на новые документы отправлен пользователю @{username} (заказ #{order_id})",
            reply_markup=create_admin_menu()
        )
        logger.info(f"Админ запросил новые документы для заказа #{order_id}")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка запроса новых документов: {e}")


@router.message(lambda message: message.text and message.text.startswith('/clarify_answer_'))
async def cmd_answer_clarification(message: Message):
    """Ответить на уточняющий вопрос"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Извлекаем ID уточнения и текст ответа
        parts = message.text.split(' ', 1)
        if len(parts) < 2:
            await message.answer("❌ Формат: /clarify_answer_[id] [ответ]",
                                 reply_markup=create_admin_menu())
            return

        command_part = parts[0]  # /clarify_answer_123
        answer_text = parts[1]  # ответ

        if not command_part.startswith('/clarify_answer_'):
            await message.answer("❌ Формат: /clarify_answer_[id] [ответ]", reply_markup=create_admin_menu())
            return

        try:
            clarification_id = int(command_part[16:])  # /clarify_answer_123 -> 123
        except ValueError:
            await message.answer("❌ Неверный ID уточнения", reply_markup=create_admin_menu())
            return

        # Получаем уточнение из БД
        cursor = db.conn.cursor()
        cursor.execute('SELECT * FROM clarifications WHERE id = ?', (clarification_id,))
        clarification = cursor.fetchone()

        if not clarification:
            await message.answer(f"❌ Уточнение #{clarification_id} не найдено", reply_markup=create_admin_menu())
            return

        order_id = clarification[1]
        user_id = clarification[2]
        user_message = clarification[3]

        # Получаем заказ
        order = db.get_order_by_id(order_id)
        if not order:
            await message.answer(f"❌ Заказ #{order_id} не найден", reply_markup=create_admin_menu())
            return

        username = order[2] or "пользователь"

        # Отправляем ответ пользователю
        response_text = f"""<b>👨‍⚕️ ОТВЕТ НА ВАШ ВОПРОС</b>

<b>Ваш вопрос:</b>
{html_escape(user_message[:500])}{'...' if len(user_message) > 500 else ''}

<b>Ответ специалиста:</b>
{html_escape(answer_text)}

<b>Этот ответ относится к заказу #{order_id}</b>"""

        await bot.send_message(user_id, response_text, parse_mode="HTML")

        # Сохраняем ответ как уточнение
        db.add_clarification(
            order_id=order_id,
            user_id=message.from_user.id,
            message_text=answer_text,
            is_from_user=False,
            replied_to=clarification_id
        )

        # Обновляем статус заказа
        db.update_order_status(order_id, OrderStatus.COMPLETED, admin_id=message.from_user.id)

        await message.answer(
            f"✅ Ответ на уточнение #{clarification_id} отправлен пользователю @{username}",
            reply_markup=create_admin_menu()
        )
        logger.info(f"Админ ответил на уточнение #{clarification_id}")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка ответа на уточнение: {e}")


@router.message(lambda message: message.text and message.text.startswith('/price_'))
async def cmd_change_price(message: Message):
    """Изменить цену заказа"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Извлекаем ID заказа и новую цену
        parts = message.text.split(' ', 1)
        if len(parts) < 2:
            await message.answer("❌ Формат: /price_[id] [новая_цена]",
                                 reply_markup=create_admin_menu())
            return

        command_part = parts[0]  # /price_123
        price_text = parts[1]  # цена

        if not command_part.startswith('/price_'):
            await message.answer("❌ Формат: /price_[id] [цена]", reply_markup=create_admin_menu())
            return

        try:
            order_id = int(command_part[7:])  # /price_123 -> 123
            new_price = int(price_text)
        except ValueError:
            await message.answer("❌ Неверный формат. Используйте: /price_123 500", reply_markup=create_admin_menu())
            return

        if new_price <= 0 or new_price > 10000:
            await message.answer("❌ Цена должна быть от 1 до 10000 рублей", reply_markup=create_admin_menu())
            return

        # Получаем заказ
        order = db.get_order_by_id(order_id)
        if not order:
            await message.answer(f"❌ Заказ #{order_id} не найден", reply_markup=create_admin_menu())
            return

        old_price = order[14] if len(order) > 14 else 490

        # Изменяем цену
        success = db.change_order_price(order_id, new_price)

        if not success:
            await message.answer(f"❌ Ошибка при изменении цены заказа #{order_id}", reply_markup=create_admin_menu())
            return

        await message.answer(
            f"✅ Цена заказа #{order_id} изменена: {old_price}₽ → {new_price}₽",
            reply_markup=create_admin_menu()
        )
        logger.info(f"Админ изменил цену заказа #{order_id} с {old_price}₽ на {new_price}₽")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка изменения цены: {e}")


@router.message(lambda message: message.text and message.text.startswith('/clarifications_'))
async def cmd_view_clarifications(message: Message):
    """Просмотреть историю уточнений по заказу"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Извлекаем ID заказа
        command_part = message.text  # /clarifications_123

        if not command_part.startswith('/clarifications_'):
            await message.answer("❌ Формат: /clarifications_[id]", reply_markup=create_admin_menu())
            return

        try:
            order_id = int(command_part[15:])  # /clarifications_123 -> 123
        except ValueError:
            await message.answer("❌ Неверный ID заказа", reply_markup=create_admin_menu())
            return

        # Получаем историю уточнений
        clarifications = db.get_clarifications(order_id, limit=20)

        if not clarifications:
            await message.answer(f"📭 Нет уточнений по заказу #{order_id}", reply_markup=create_admin_menu())
            return

        text = f"<b>📝 ИСТОРИЯ УТОЧНЕНИЙ ЗАКАЗА #{order_id}</b>\n\n"

        for clarification in clarifications:
            clar_id, clar_order_id, user_id, message_text, message_type, file_id, \
                sent_at, is_from_user, replied_to, is_admin_request = clarification[:10]

            # Определяем отправителя
            if is_from_user:
                sender = "👤 Пользователь"
            else:
                sender = "👨‍⚕️ Специалист"

            # Форматируем время
            if isinstance(sent_at, str):
                time_str = sent_at
            else:
                time_str = sent_at.strftime('%d.%m.%Y %H:%M') if sent_at else 'н/д'

            text += f"<b>{sender} • {time_str}</b>\n"

            if message_type != 'text':
                text += f"📎 Тип: {message_type}\n"

            if message_text:
                # Обрезаем длинный текст
                display_text = message_text[:300] + ('...' if len(message_text) > 300 else '')
                text += f"{display_text}\n"

            if file_id and message_type in ['photo', 'document', 'pdf']:
                text += f"📁 Файл ID: {file_id[:20]}...\n"

            if is_admin_request:
                text += f"<i>📋 Запрос от администратора</i>\n"

            text += "─" * 20 + "\n\n"

        text += f"<b>📊 Всего уточнений:</b> {len(clarifications)}"

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка просмотра уточнений: {e}")


@router.message(lambda message: message.text and message.text.startswith('/create_promo'))
async def cmd_create_promo_code(message: Message):
    """Создать промокод"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        parts = message.text.split(' ')
        if len(parts) < 4:
            await message.answer(
                "❌ Формат: /create_promo [код] [percent/fixed] [значение] [использований (-1 для бесконечных)]\n"
                "Примеры:\n"
                "/create_promo SUMMER2024 percent 10 -1\n"
                "/create_promo SALE500 fixed 500 50\n"
                "/create_promo TEST percent 20 100 'Пробный промокод'",
                reply_markup=create_admin_menu()
            )
            return

        code = parts[1].upper()
        discount_type = parts[2].lower()
        discount_value = float(parts[3])

        if len(parts) > 4:
            uses_left = int(parts[4])
        else:
            uses_left = -1

        description = ""
        if len(parts) > 5:
            description = ' '.join(parts[5:])

        if discount_type not in ['percent', 'fixed']:
            await message.answer("❌ Тип скидки должен быть 'percent' или 'fixed'", reply_markup=create_admin_menu())
            return

        if discount_type == 'percent' and (discount_value <= 0 or discount_value > 100):
            await message.answer("❌ Процент должен быть от 1 до 100", reply_markup=create_admin_menu())
            return

        if discount_type == 'fixed' and discount_value <= 0:
            await message.answer("❌ Фиксированная скидка должна быть больше 0", reply_markup=create_admin_menu())
            return

        success = db.create_promo_code(
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            uses_left=uses_left,
            description=description
        )

        if success:
            await message.answer(f"✅ Промокод {code} создан успешно!", reply_markup=create_admin_menu())
        else:
            await message.answer(f"❌ Ошибка создания промокода {code}", reply_markup=create_admin_menu())

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка создания промокода: {e}")


@router.message(lambda message: message.text and message.text.startswith('/deactivate_promo'))
async def cmd_deactivate_promo_code(message: Message):
    """Деактивировать промокод"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        parts = message.text.split(' ', 1)
        if len(parts) < 2:
            await message.answer("❌ Формат: /deactivate_promo [код]", reply_markup=create_admin_menu())
            return

        code = parts[1].upper()
        success = db.deactivate_promo_code(code)

        if success:
            await message.answer(f"✅ Промокод {code} деактивирован", reply_markup=create_admin_menu())
        else:
            await message.answer(f"❌ Ошибка деактивации промокода {code}", reply_markup=create_admin_menu())

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка деактивации промокода: {e}")


@router.message(lambda message: message.text and message.text == '/promo_stats')
async def cmd_promo_stats(message: Message):
    """Статистика по промокодам"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Получаем статистику
        stats = db.get_statistics()

        promo_stats_text = f"""<b>📊 СТАТИСТИКА ПРОМОКОДОВ</b>

<b>Общая информация:</b>
• Всего промокодов: {stats['total_promo_codes']}
• Использований: {stats['promo_uses']}
• Общая сумма скидок: {stats['promo_discounts']:.2f}₽

<b>Использованные промокоды:</b>"""

        # Получаем список использованных промокодов
        cursor = db.conn.cursor()
        cursor.execute('''
            SELECT up.promo_code, COUNT(*) as uses, SUM(up.discount_amount) as total_discount,
                   GROUP_CONCAT(DISTINCT u.username) as users
            FROM used_promo_codes up
            LEFT JOIN orders o ON up.order_id = o.id
            LEFT JOIN (
                SELECT user_id, MAX(username) as username 
                FROM orders 
                GROUP BY user_id
            ) u ON up.user_id = u.user_id
            GROUP BY up.promo_code
            ORDER BY total_discount DESC
        ''')

        used_promos = cursor.fetchall()

        if used_promos:
            for promo_code, uses, total_discount, users in used_promos:
                promo_stats_text += f"\n🔸 <b>{promo_code}</b>:"
                promo_stats_text += f"\n   Использован: {uses} раз"
                promo_stats_text += f"\n   Скидка: {total_discount:.2f}₽"
                if users:
                    user_list = users.split(',')[:5]
                    promo_stats_text += f"\n   Пользователи: {', '.join(user_list)}"
                    if len(users.split(',')) > 5:
                        promo_stats_text += f" и ещё {len(users.split(',')) - 5}"
        else:
            promo_stats_text += "\nНет данных об использовании промокодов."

        await message.answer(promo_stats_text, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка получения статистики промокодов: {e}")


@router.message(lambda message: message.text and message.text.startswith('/referral_stats'))
async def cmd_referral_stats(message: Message):
    """Статистика по конкретному пользователю"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        parts = message.text.split(' ')
        if len(parts) < 2:
            await message.answer("❌ Формат: /referral_stats [user_id]", reply_markup=create_admin_menu())
            return

        try:
            user_id = int(parts[1])
        except ValueError:
            await message.answer("❌ Неверный ID пользователя", reply_markup=create_admin_menu())
            return

        # Получаем статистику пользователя
        stats = db.get_referrer_stats(user_id)

        # Получаем username
        cursor = db.conn.cursor()
        cursor.execute('SELECT username FROM orders WHERE user_id = ? LIMIT 1', (user_id,))
        result = cursor.fetchone()
        username = result[0] if result else "неизвестно"

        # Получаем реферальную ссылку
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            if not bot_username:
                referral_link = f"https://t.me/{bot_info.id}?start=ref_{user_id}"
            else:
                referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        except Exception:
            referral_link = f"t.me/ваш_бот?start=ref_{user_id}"

        text = f"""<b>📊 РЕФЕРАЛЬНАЯ СТАТИСТИКА</b>

<b>Пользователь:</b>
• ID: {user_id}
• Username: @{username}

<b>Статистика:</b>
• Приглашено друзей: {stats.get('total_referred', 0)}
• Из них сделали заказы: {stats.get('completed_referred', 0)}
• Заработано бонусов: {stats.get('total_bonus', 0):.2f}₽

<b>Реферальная ссылка:</b>
<code>{referral_link}</code>

<b>Действия:</b>
• Отправить ссылку пользователю: /send_ref_{user_id}"""

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка получения реферальной статистики: {e}")


@router.message(lambda message: message.text and message.text.startswith('/send_ref_'))
async def cmd_send_referral_link(message: Message):
    """Отправить реферальную ссылку пользователю"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        parts = message.text.split(' ')
        if len(parts) < 2:
            await message.answer("❌ Формат: /send_ref_[user_id] [сообщение]", reply_markup=create_admin_menu())
            return

        command_part = parts[0]
        try:
            user_id = int(command_part[9:])  # /send_ref_123 -> 123
        except ValueError:
            await message.answer("❌ Неверный ID пользователя", reply_markup=create_admin_menu())
            return

        # Получаем статистику пользователя
        stats = db.get_referrer_stats(user_id)

        # Получаем username
        cursor = db.conn.cursor()
        cursor.execute('SELECT username FROM orders WHERE user_id = ? LIMIT 1', (user_id,))
        result = cursor.fetchone()
        username = result[0] if result else "Пользователь"

        # Получаем реферальную ссылку
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            if not bot_username:
                referral_link = f"https://t.me/{bot_info.id}?start=ref_{user_id}"
            else:
                referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        except Exception:
            referral_link = f"t.me/ваш_бот?start=ref_{user_id}"

        # Формируем сообщение
        custom_message = ""
        if len(parts) > 1:
            custom_message = ' '.join(parts[1:])

        ref_message = f"""👋 Привет, @{username}!

Вот ваша персональная реферальная ссылка:

<code>{referral_link}</code>

{custom_message}

<b>💎 Как это работает:</b>
1. Вы приглашаете друга по своей ссылке
2. Друг получает скидку {config.REFERRED_DISCOUNT_PERCENT}% на первый заказ
3. Когда друг оплатит заказ, вы получаете {config.REFERRER_BONUS_PERCENT}% от суммы его заказа

<b>🎁 Ваша статистика:</b>
• Приглашено друзей: {stats.get('total_referred', 0)}
• Заработано: {stats.get('total_bonus', 0):.2f}₽

<b>Просто отправьте другу эту ссылку!</b>"""

        # Отправляем пользователю
        await bot.send_message(user_id, ref_message, parse_mode="HTML")

        await message.answer(f"✅ Реферальная ссылка отправлена пользователю @{username}",
                             reply_markup=create_admin_menu())

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка отправки реферальной ссылки: {e}")


# ========== ШАБЛОНЫ (КОМАНДЫ) ==========
@router.message(lambda message: message.text and message.text.startswith('/template'))
async def handle_quick_template(message: Message):
    """Обработка быстрых шаблонов админа"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Получаем все шаблоны
        templates = db.get_quick_templates()

        if not templates:
            await message.answer("📭 Нет сохраненных шаблонов")
            return

        # Если команда без номера - показываем список
        if message.text == "/template" or message.text == "/template_list":
            templates_text = "<b>📝 СПИСОК ШАБЛОНОВ</b>\n\n"

            for i, (template_id, name, text, created_at, updated_at) in enumerate(templates, 1):
                templates_text += f"{i}. <b>{name}</b>\n"
                templates_text += f"   ID: {template_id}\n"
                templates_text += f"   Текст: {text[:50]}...\n"
                templates_text += f"   Использовать: /template{template_id}_[order_id]\n\n"

            templates_text += "<b>📌 КОМАНДЫ:</b>\n"
            templates_text += "<code>/template_add [название] [текст]</code> - добавить шаблон\n"
            templates_text += "<code>/template_edit [id] [новый текст]</code> - изменить шаблон\n"
            templates_text += "<code>/template_del [id]</code> - удалить шаблон\n"

            await message.answer(templates_text, parse_mode="HTML")
            return

        # Проверяем, это добавление шаблона?
        if message.text.startswith("/template_add "):
            parts = message.text.split(' ', 2)
            if len(parts) < 3:
                await message.answer("❌ Формат: /template_add [название] [текст]")
                return

            name = parts[1]
            text = parts[2]

            if db.add_quick_template(name, text):
                await message.answer(f"✅ Шаблон '{name}' добавлен")
            else:
                await message.answer("❌ Ошибка добавления шаблона")
            return

        # Проверяем, это редактирование шаблона?
        if message.text.startswith("/template_edit "):
            parts = message.text.split(' ', 2)
            if len(parts) < 3:
                await message.answer("❌ Формат: /template_edit [id] [новый текст]")
                return

            try:
                template_id = int(parts[1])
                new_text = parts[2]

                if db.update_quick_template(template_id, text=new_text):
                    await message.answer(f"✅ Шаблон #{template_id} обновлен")
                else:
                    await message.answer("❌ Ошибка обновления шаблона")
            except ValueError:
                await message.answer("❌ ID шаблона должен быть числом")
            return

        # Проверяем, это удаление шаблона?
        if message.text.startswith("/template_del "):
            parts = message.text.split(' ', 1)
            if len(parts) < 2:
                await message.answer("❌ Формат: /template_del [id]")
                return

            try:
                template_id = int(parts[1])

                if db.delete_quick_template(template_id):
                    await message.answer(f"✅ Шаблон #{template_id} удален")
                else:
                    await message.answer("❌ Ошибка удаления шаблона")
            except ValueError:
                await message.answer("❌ ID шаблона должен быть числом")
            return

        # Если это использование шаблона с order_id
        # Формат: /template1_123 или /template_1_123
        parts = message.text.split('_')
        if len(parts) >= 2:
            try:
                # Пробуем разные форматы
                if parts[0] == "/template":
                    # Формат: /template_1_123
                    if len(parts) < 3:
                        await message.answer("❌ Формат: /template_[id]_[order_id]")
                        return

                    template_id = int(parts[1])
                    order_id = int(parts[2])
                else:
                    # Формат: /template1_123
                    template_num = parts[0].replace("/template", "")
                    if not template_num.isdigit():
                        await message.answer("❌ Формат: /template[номер]_[order_id]")
                        return

                    template_id = int(template_num)
                    order_id = int(parts[1])

                # Получаем текст шаблона
                template_text = db.get_quick_template(template_id)
                if not template_text:
                    await message.answer(f"❌ Шаблон #{template_id} не найден")
                    return

                # Получаем заказ
                order = db.get_order_by_id(order_id)
                if not order:
                    await message.answer(f"❌ Заказ #{order_id} не найден")
                    return

                user_id = order[1]

                # Отправляем ответ пользователю
                response_text = f"""<b>👨‍⚕️ ОТВЕТ НА ВАШ ЗАКАЗ #{order_id}</b>

{template_text}

<b>📝 После получения ответа вы можете:</b>"""

                from handlers.user_handlers import ClarificationHandler
                keyboard = ClarificationHandler.create_clarification_keyboard(order_id)
                await bot.send_message(user_id, response_text, parse_mode="HTML", reply_markup=keyboard)

                # Обновляем статус заказа
                db.update_order_status(order_id, OrderStatus.COMPLETED, admin_id=message.from_user.id)

                # Сохраняем ответ как уточнение
                db.add_clarification(
                    order_id=order_id,
                    user_id=message.from_user.id,
                    message_text=template_text,
                    is_from_user=False
                )

                await message.answer(f"✅ Шаблон #{template_id} отправлен на заказ #{order_id}")
                logger.info(f"Админ отправил шаблон #{template_id} на заказ #{order_id}")

            except (ValueError, IndexError) as e:
                await message.answer(f"❌ Ошибка формата: {e}")
            except Exception as e:
                await message.answer(f"❌ Ошибка: {str(e)[:200]}")
                logger.error(f"Ошибка отправки шаблона: {e}")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Ошибка обработки шаблона: {e}")


@router.message(lambda message: message.text and message.text.startswith('/mark_tax_reported'))
async def cmd_mark_tax_reported(message: Message):
    """Отметить платеж как отчитанный в налоговой"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        parts = message.text.split(' ')
        if len(parts) < 2:
            # Показываем список неотчитанных платежей
            cursor = db.conn.cursor()
            cursor.execute('''
                SELECT p.order_id, p.amount/100 as amount_rub, p.payment_date, 
                       o.service_type, o.username
                FROM payments p
                JOIN orders o ON p.order_id = o.id
                WHERE p.tax_reported = FALSE AND p.status = 'success'
                ORDER BY p.payment_date DESC
                LIMIT 10
            ''')

            unreported = cursor.fetchall()

            if not unreported:
                await message.answer("✅ Все платежи отчитаны в налоговой", reply_markup=create_admin_menu())
                return

            text = "<b>📋 НЕОТЧИТАННЫЕ ПЛАТЕЖИ</b>\n\n"

            for order_id, amount_rub, payment_date, service_type, username in unreported:
                text += f"<b>Заказ #{order_id}</b>\n"
                text += f"👤: @{username or 'без username'}\n"
                text += f"💰: {amount_rub}₽ ({service_type})\n"
                text += f"📅: {payment_date}\n"
                text += f"🔧: /mark_tax_reported {order_id}\n\n"

            text += "<b>📌 КОМАНДЫ:</b>\n"
            text += "<code>/mark_tax_reported [order_id]</code> - отметить как отчитанный\n"
            text += "<code>/mark_all_tax_reported</code> - отметить все как отчитанные"

            await message.answer(text, parse_mode="HTML")
            return

        # Отмечаем конкретный заказ
        try:
            order_id = int(parts[1])
        except ValueError:
            await message.answer("❌ Неверный ID заказа", reply_markup=create_admin_menu())
            return

        # Помечаем как отчитанный
        success = db.mark_tax_reported(order_id)

        if success:
            await message.answer(f"✅ Заказ #{order_id} отмечен как отчитанный в налоговой",
                                 reply_markup=create_admin_menu())
        else:
            await message.answer(f"❌ Ошибка при отметке заказа #{order_id}",
                                 reply_markup=create_admin_menu())

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка отметки налогового отчета: {e}")


@router.message(lambda message: message.text == '/export_stats')
async def cmd_export_stats(message: Message):
    """Экспорт статистики в CSV"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        await message.answer("📊 Подготовка статистики для экспорта...", reply_markup=create_admin_menu())

        # Получаем статистику
        stats = db.get_statistics()

        # Создаем CSV файл
        output = StringIO()
        writer = csv.writer(output)

        # Записываем заголовки
        writer.writerow(['Метрика', 'Значение'])

        # Общая статистика
        writer.writerow(['=== ОБЩАЯ СТАТИСТИКА ===', ''])
        writer.writerow(['Всего заказов', stats['total_orders']])
        writer.writerow(['Заказов сегодня', stats['today_orders']])
        writer.writerow(['Уникальных пользователей', stats['unique_users']])
        writer.writerow(['Приняли соглашение', stats['agreements_accepted']])

        # Статусы заказов
        writer.writerow(['', ''])
        writer.writerow(['=== СТАТУСЫ ЗАКАЗОВ ===', ''])
        writer.writerow(['Ожидают ответа', stats['pending_orders']])
        writer.writerow(['В обработке', stats['completed_orders']])
        writer.writerow(['Уточняются', stats['clarification_orders']])
        writer.writerow(['Нужны документы', stats['new_docs_orders']])
        writer.writerow(['Оплачено', stats['paid_orders']])

        # Финансы
        writer.writerow(['', ''])
        writer.writerow(['=== ФИНАНСЫ ===', ''])
        writer.writerow(['Общая выручка', f"{stats['total_revenue']}₽"])
        writer.writerow(['Средний чек', f"{stats['avg_price']}₽"])
        writer.writerow(['Сумма скидок', f"{stats['total_discounts']}₽"])
        writer.writerow(['Промокоды', f"{stats['promo_discounts']:.2f}₽"])
        writer.writerow(['Неотчитано в налоговой', f"{stats['unreported_amount']}₽"])

        # Оценки
        writer.writerow(['', ''])
        writer.writerow(['=== ОЦЕНКИ ===', ''])
        writer.writerow(['Всего оценок', stats['total_ratings']])
        writer.writerow(['Средняя оценка', f"{stats['avg_rating']:.1f}/5"])

        # Распределение оценок
        for rating, count in stats['rating_distribution']:
            writer.writerow([f'Оценка {rating} звезд', count])

        # Статистика по типам услуг
        writer.writerow(['', ''])
        writer.writerow(['=== ПО ТИПАМ УСЛУГ ===', ''])
        for service_type, count, avg_price, total_revenue in stats['service_stats']:
            writer.writerow([service_type, f"{count} зак., {avg_price:.0f}₽ средн., {total_revenue}₽ всего"])

        # Готовим файл для отправки
        output.seek(0)
        csv_content = output.getvalue()

        # Сохраняем во временный файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_file = f.name

        # Отправляем файл
        with open(temp_file, 'rb') as file:
            await message.answer_document(
                document=BufferedInputFile(file.read(),
                                           filename=f"statistics_{datetime.now().strftime('%Y%m%d')}.csv"),
                caption=f"📊 Статистика на {datetime.now().strftime('%d.%m.%Y')}"
            )

        # Удаляем временный файл
        os.unlink(temp_file)

        logger.info(f"Админ экспортировал статистику")

    except Exception as e:
        await message.answer(f"❌ Ошибка экспорта: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка экспорта статистики: {e}")


@router.message(lambda message: message.text == '/backup_db')
async def cmd_backup_db(message: Message):
    """Создать резервную копию БД"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    await handle_backup(message)  # Используем существующую функцию


@router.message(lambda message: message.text == '/cleanup_old')
async def cmd_cleanup_old(message: Message):
    """Очистить старые данные"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        await message.answer("🗑️ Начинаю очистку старых данных...", reply_markup=create_admin_menu())

        cursor = db.conn.cursor()

        # Получаем статистику до очистки
        cursor.execute("SELECT COUNT(*) FROM orders")
        total_orders_before = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM clarifications")
        total_clarifications_before = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM payments")
        total_payments_before = cursor.fetchone()[0]

        # Удаляем заказы старше 90 дней со статусом completed или cancelled
        cursor.execute('''
            DELETE FROM orders 
            WHERE status IN ('completed', 'cancelled') 
            AND created_at < datetime('now', '-90 days')
        ''')
        deleted_orders = cursor.rowcount

        # Удаляем уточнения для удаленных заказов
        cursor.execute('''
            DELETE FROM clarifications 
            WHERE order_id NOT IN (SELECT id FROM orders)
        ''')
        deleted_clarifications = cursor.rowcount

        # Удаляем платежи для удаленных заказов
        cursor.execute('''
            DELETE FROM payments 
            WHERE order_id NOT IN (SELECT id FROM orders)
        ''')
        deleted_payments = cursor.rowcount

        # Удаляем оценки для удаленных заказов
        cursor.execute('''
            DELETE FROM ratings 
            WHERE order_id NOT IN (SELECT id FROM orders)
        ''')
        deleted_ratings = cursor.rowcount

        # Удаляем использованные промокоды для удаленных заказов
        cursor.execute('''
            DELETE FROM used_promo_codes 
            WHERE order_id NOT IN (SELECT id FROM orders)
        ''')
        deleted_promo_uses = cursor.rowcount

        # Удаляем старые реферальные связи без заказов
        cursor.execute('''
            DELETE FROM referrals 
            WHERE status = 'pending' 
            AND created_at < datetime('now', '-30 days')
            AND order_id IS NULL
        ''')
        deleted_referrals = cursor.rowcount

        # Оптимизируем базу данных
        cursor.execute("VACUUM")

        db.conn.commit()

        # Получаем статистику после очистки
        cursor.execute("SELECT COUNT(*) FROM orders")
        total_orders_after = cursor.fetchone()[0]

        response = f"""✅ <b>ОЧИСТКА ЗАВЕРШЕНА</b>

<b>🗑️ УДАЛЕНО:</b>
• Заказов: {deleted_orders}
• Уточнений: {deleted_clarifications}
• Платежей: {deleted_payments}
• Оценок: {deleted_ratings}
• Использований промокодов: {deleted_promo_uses}
• Реферальных связей: {deleted_referrals}

<b>📊 СТАТИСТИКА ДО/ПОСЛЕ:</b>
• Заказы: {total_orders_before} → {total_orders_after}
• Уточнения: {total_clarifications_before} → {total_clarifications_before - deleted_clarifications}
• Платежи: {total_payments_before} → {total_payments_before - deleted_payments}

<b>⚙️ ОПЕРАЦИИ:</b>
• Удалены завершенные/отмененные заказы старше 90 дней
• Удалены неактивные реферальные связи старше 30 дней
• База данных оптимизирована (VACUUM)"""

        await message.answer(response, parse_mode="HTML")

        logger.info(f"Админ выполнил очистку старых данных")

    except Exception as e:
        await message.answer(f"❌ Ошибка очистки: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка очистки старых данных: {e}")


# ========== ИНФОРМАЦИЯ О ЗАКАЗЕ ==========
@router.message(lambda message: message.text and message.text.startswith('/order_'))
async def cmd_order_info(message: Message):
    """Полная информация о заказе"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        command_part = message.text.strip()

        if not command_part.startswith('/order_'):
            await message.answer("❌ Формат: /order_[id]", reply_markup=create_admin_menu())
            return

        try:
            order_id = int(command_part[7:])
        except ValueError:
            await message.answer("❌ Неверный ID заказа", reply_markup=create_admin_menu())
            return

        # Получаем заказ
        order = db.get_order_by_id(order_id)
        if not order:
            await message.answer(f"❌ Заказ #{order_id} не найден", reply_markup=create_admin_menu())
            return

        # Распаковываем поля заказа
        (_, user_id, username, age, sex, questions, documents_json,
         document_types_json, service_type, status, created_at, updated_at,
         answered_at, admin_id, price, original_price, payment_status,
         invoice_payload, agreement_accepted, agreement_version,
         tax_reported, rating, clarification_count, last_clarification_at,
         can_clarify_until, discount_applied, discount_type, promo_code,
         referrer_id, needs_demographics) = order

        # Парсим JSON поля
        documents = []
        document_types = []
        if documents_json:
            try:
                documents = json.loads(documents_json)
                document_types = json.loads(document_types_json) if document_types_json else []
            except:
                pass

        # Форматируем даты
        created_str = "н/д"
        if created_at:
            if isinstance(created_at, str):
                created_str = created_at[:19]
            else:
                created_str = created_at.strftime('%d.%m.%Y %H:%M:%S')

        updated_str = "н/д"
        if updated_at:
            if isinstance(updated_at, str):
                updated_str = updated_at[:19]
            else:
                updated_str = updated_at.strftime('%d.%m.%Y %H:%M:%S')

        answered_str = "н/д"
        if answered_at:
            if isinstance(answered_at, str):
                answered_str = answered_at[:19]
            else:
                answered_str = answered_at.strftime('%d.%m.%Y %H:%M:%S')

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

        text = f"""<b>{status_emoji} ЗАКАЗ #{order_id}</b>

<b>👤 КЛИЕНТ:</b>
• ID: {user_id}
• Username: @{username or 'не указан'}

<b>📋 ОСНОВНАЯ ИНФОРМАЦИЯ:</b>
• Услуга: {service_type}
• Статус: {status}
• Создан: {created_str}
• Обновлен: {updated_str}
• Ответ дан: {answered_str or 'еще нет'}

<b>💰 ФИНАНСЫ:</b>
• Цена: {price}₽
• Исходная цена: {original_price}₽
• Скидка: {discount_applied or 0}₽
• Тип скидки: {discount_type or 'нет'}
• Промокод: {promo_code or 'нет'}
• Статус оплаты: {payment_status}

<b>👤 ДЕМОГРАФИЯ:</b>
• Возраст: {age or 'не указан'}
• Пол: {sex or 'не указан'}

<b>📄 ДОКУМЕНТЫ:</b>
• Количество: {len(documents)} файлов
• Типы: {', '.join(document_types) if document_types else 'не указаны'}

<b>❓ ВОПРОС КЛИЕНТА:</b>
{questions[:500]}{'...' if questions and len(questions) > 500 else (questions or 'нет вопроса')}

<b>📊 ДОПОЛНИТЕЛЬНО:</b>
• Уточнений: {clarification_count}
• Оценка: {rating or 'еще нет'}
• Соглашение принято: {'✅' if agreement_accepted else '❌'}
• Налог отчитан: {'✅' if tax_reported else '❌'}
• Реферер: {referrer_id or 'нет'}

<b>🔧 ДЕЙСТВИЯ:</b>
• Ответить: /send_{order_id} [текст]
• Завершить: /complete_{order_id}
• Отменить: /cancel_{order_id}
• Запросить доки: /redocs_{order_id} [причина]
• Просмотреть уточнения: /clarifications_{order_id}
• Изменить цену: /price_{order_id} [новая цена]"""

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка получения информации о заказе: {e}")


# ========== КОМАНДА АДМИН ==========
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Команда админ-меню"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    await message.answer("👨‍💻 <b>Панель администратора</b>", parse_mode="HTML", reply_markup=create_admin_menu())