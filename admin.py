# admin/admin_handlers.py
import asyncio
import json
import csv
import tempfile
import os
from datetime import datetime
from io import StringIO
from html import escape as html_escape

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    BufferedInputFile
)
from aiogram.fsm.context import FSMContext

from utils.config import config
from database.database import Database  # Импортируем класс
from models.enums import OrderStatus, ServiceType, DocumentType, UserRole  # Исправляем импорты

# Создаем экземпляр базы данных
db = Database()

# Получаем бота и логгер через dependency injection
# Вместо импорта из bot.py мы будем получать их через router
router = Router(name="admin_router")


def create_admin_menu() -> ReplyKeyboardMarkup:
    """Создание меню администратора"""
    buttons = [
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📋 Все заказы")],
        [KeyboardButton(text="⏳ Ожидающие"), KeyboardButton(text="💾 Бэкап")],
        [KeyboardButton(text="🎫 Промокоды"), KeyboardButton(text="👥 Рефералы")],
        [KeyboardButton(text="📝 Шаблоны"), KeyboardButton(text="🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


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
            await message.answer(f"⚠️ Ошибка получения реферальной статистики: {str(e)[:100]}")
            # Логируем ошибку, но не прерываем выполнение

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
        # Логируем через встроенный логгер aiogram
        print(f"Ошибка получения статистики: {e}")


# ========== ВСЕ ЗАКАЗЫ ==========
@router.message(F.text == "📋 Все заказы")
async def handle_all_orders(message: Message):
    """Показать все заказы (последние сверху)"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        # Получаем заказы с сортировкой по убыванию (новые сверху)
        orders = db.get_all_orders(limit=20)  # Нужно добавить такой метод в database.py

        if not orders:
            await message.answer("📭 Нет заказов", reply_markup=create_admin_menu())
            return

        text_lines = []
        text_lines.append(f"<b>📋 ПОСЛЕДНИЕ ЗАКАЗЫ ({len(orders)})</b>\n")
        text_lines.append("<i>Новые заказы вверху ↓</i>\n")

        for order in orders:
            order_id, user_id, username, service_type, status, created_at, price, original_price = order

            # Эмодзи для статуса (используем наши enum)
            status_emoji = {
                OrderStatus.CREATED: '📝',
                OrderStatus.PAID: '💰',
                OrderStatus.DOCS_UPLOADED: '📎',
                OrderStatus.PROCESSING: '🔄',
                OrderStatus.COMPLETED: '✅',
                OrderStatus.CANCELLED: '❌',
                OrderStatus.CLARIFICATION: '❓'
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
        print(f"Ошибка отображения всех заказов: {e}")
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

        # Создаем директорию для бэкапов, если ее нет
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)

        success = db.backup(backup_dir)

        if success:
            # Получаем список последних бэкапов
            backups = sorted([f for f in os.listdir(backup_dir)
                              if f.startswith('backup_') and f.endswith('.db')])

            if backups:
                latest = backups[-1]
                file_size = os.path.getsize(os.path.join(backup_dir, latest))
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
        print(f"Ошибка создания бэкапа: {e}")


# ========== КОМАНДА АДМИН ==========
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Команда админ-меню"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен")
        return

    await message.answer("👨‍💻 <b>Панель администратора</b>", parse_mode="HTML", reply_markup=create_admin_menu())


