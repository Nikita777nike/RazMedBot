# database/database.py
import sqlite3
import os
import shutil
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import logging

from models.enums import OrderStatus, PaymentStatus, DiscountType

from utils.config import config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_name: str = 'orders.db'):
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
        self.create_backup_dir()

    def create_backup_dir(self):
        """Создание директории для бэкапов"""
        os.makedirs(config.BACKUP_DIR, exist_ok=True)

    def backup(self):
        """Создание резервной копии базы данных"""
        try:
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            backup_path = os.path.join(config.BACKUP_DIR, backup_name)
            shutil.copy2(self.db_name, backup_path)

            # Удаляем старые бэкапы
            backups = sorted([f for f in os.listdir(config.BACKUP_DIR)
                              if f.startswith('backup_') and f.endswith('.db')])
            if len(backups) > 10:
                for old_backup in backups[:-10]:
                    os.remove(os.path.join(config.BACKUP_DIR, old_backup))

            logger.info(f"Создан бэкап БД: {backup_name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка создания бэкапа: {e}")
            return False

    def create_tables(self):
        """Создание таблиц базы данных"""
        cursor = self.conn.cursor()

        # Таблица пользовательских соглашений
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_agreements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                agreement_version TEXT DEFAULT '2.1',
                accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_info TEXT,
                UNIQUE(user_id, agreement_version)
            )
        ''')

        # Таблица заказов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                age INTEGER,
                sex TEXT,
                questions TEXT,
                documents TEXT,
                document_types TEXT,
                service_type TEXT DEFAULT 'Не указано',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                answered_at TIMESTAMP,
                admin_id INTEGER,
                price INTEGER DEFAULT 490,
                original_price INTEGER DEFAULT 490,
                payment_status TEXT DEFAULT 'pending',
                invoice_payload TEXT,
                agreement_accepted BOOLEAN DEFAULT FALSE,
                agreement_version TEXT DEFAULT '2.1',
                tax_reported BOOLEAN DEFAULT FALSE,
                rating INTEGER DEFAULT NULL,
                clarification_count INTEGER DEFAULT 0,
                last_clarification_at TIMESTAMP,
                can_clarify_until TIMESTAMP,
                discount_applied REAL DEFAULT 0,
                discount_type TEXT,
                promo_code TEXT,
                referrer_id INTEGER,
                needs_demographics BOOLEAN DEFAULT TRUE
            )
        ''')

        # Таблица уточнений
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clarifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message_text TEXT,
                message_type TEXT DEFAULT 'text',
                file_id TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_from_user BOOLEAN DEFAULT TRUE,
                replied_to_clarification_id INTEGER,
                is_admin_request BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (order_id) REFERENCES orders (id)
            )
        ''')

        # Таблица платежей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                amount INTEGER,
                currency TEXT DEFAULT 'RUB',
                status TEXT,
                provider_payment_id TEXT,
                invoice_payload TEXT,
                payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tax_reported BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (order_id) REFERENCES orders (id)
            )
        ''')

        # Таблица оценок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER UNIQUE,
                rating INTEGER,
                rated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (id)
            )
        ''')

        # Таблица промокодов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                discount_type TEXT DEFAULT 'percent',
                discount_value REAL NOT NULL,
                uses_left INTEGER DEFAULT -1,
                valid_until TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                description TEXT
            )
        ''')

        # Таблица использованных промокодов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS used_promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                promo_code TEXT NOT NULL,
                order_id INTEGER NOT NULL,
                discount_amount REAL,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (id),
                FOREIGN KEY (promo_code) REFERENCES promo_codes (code)
            )
        ''')

        # Таблица рефералов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                order_id INTEGER,
                referrer_bonus REAL DEFAULT 0,
                referred_discount REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(referrer_id, referred_id)
            )
        ''')

        # Таблица быстрых шаблонов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quick_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Индексы для ускорения запросов
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ratings_order_id ON ratings(order_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_clarifications_order_id ON clarifications(order_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_clarifications_user_id ON clarifications(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id ON referrals(referrer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_referred_id ON referrals(referred_id)')

        self.conn.commit()
        self.add_missing_columns()
        self.initialize_default_templates()

    # ... (остальные методы из оригинального файла - их нужно перенести полностью)
    # Здесь должны быть все методы: add_missing_columns, initialize_default_templates,
    # record_agreement_acceptance, check_agreement_accepted, create_prepaid_order,
    # update_order_details, update_order_status, mark_order_needs_new_docs,
    # can_user_clarify, add_clarification, get_clarifications, set_invoice_payload,
    # process_payment, get_order_by_id, get_user_orders, get_all_orders,
    # get_pending_orders, save_rating, create_promo_code, get_promo_code,
    # apply_promo_code, get_all_promo_codes, deactivate_promo_code,
    # create_referral, get_referrer_stats, check_referral_discount,
    # apply_referral_discount, get_all_referrals_stats, get_quick_templates,
    # get_quick_template, add_quick_template, update_quick_template,
    # delete_quick_template, get_statistics, mark_tax_reported, change_order_price,
    # create_referrals_table_if_not_exists

    # Для экономии места я покажу структуру, а вы перенесете методы из оригинального файла
    def add_missing_columns(self):
        """Добавляем отсутствующие колонки"""
        cursor = self.conn.cursor()

        # Проверяем и добавляем колонки в таблицу orders
        cursor.execute("PRAGMA table_info(orders)")
        existing_columns_orders = [column[1] for column in cursor.fetchall()]

        required_columns_orders = [
            ('agreement_accepted', 'BOOLEAN DEFAULT FALSE'),
            ('agreement_version', 'TEXT DEFAULT "2.1"'),
            ('tax_reported', 'BOOLEAN DEFAULT FALSE'),
            ('rating', 'INTEGER DEFAULT NULL'),
            ('clarification_count', 'INTEGER DEFAULT 0'),
            ('last_clarification_at', 'TIMESTAMP'),
            ('can_clarify_until', 'TIMESTAMP'),
            ('original_price', 'INTEGER DEFAULT 490'),
            ('discount_applied', 'REAL DEFAULT 0'),
            ('discount_type', 'TEXT'),
            ('promo_code', 'TEXT'),
            ('referrer_id', 'INTEGER'),
            ('needs_demographics', 'BOOLEAN DEFAULT TRUE')
        ]

        for column_name, column_type in required_columns_orders:
            if column_name not in existing_columns_orders:
                try:
                    cursor.execute(f'ALTER TABLE orders ADD COLUMN {column_name} {column_type}')
                    logger.info(f"Добавлена колонка {column_name} в таблицу orders")
                except Exception as e:
                    logger.error(f"Ошибка добавления колонки {column_name} в orders: {e}")

        self.conn.commit()

    def initialize_default_templates(self):
        """Инициализация стандартных шаблонов"""
        cursor = self.conn.cursor()

        # Проверяем, есть ли уже шаблоны
        cursor.execute("SELECT COUNT(*) FROM quick_templates")
        count = cursor.fetchone()[0]

        if count == 0:
            default_templates = [
                ("Стандартный ответ",
                 "Спасибо за заказ! Ваши документы приняты на обработку. Ответ будет готов в течение 24 часов."),
                ("Срочный заказ", "Ваш заказ помечен как срочный. Обработаем в приоритетном порядке."),
                ("Нужны доп. документы", "Для более точного анализа нужны дополнительные документы: [укажите какие]"),
                ("Завершен", "Заказ завершен. Благодарим за обращение! Оцените качество услуги."),
                ("Нечитаемые документы",
                 "Пришлите, пожалуйста, более качественные фото/сканы документов. Текущие плохо читаются."),
                ("Вопрос по анализу",
                 "По вашему анализу: [краткий ответ]. Если нужны подробности - задайте уточняющий вопрос.")
            ]

            for name, text in default_templates:
                cursor.execute('''
                    INSERT INTO quick_templates (name, text) 
                    VALUES (?, ?)
                ''', (name, text))

            self.conn.commit()
            logger.info("Созданы стандартные шаблоны ответов")

    def record_agreement_acceptance(self, user_id: int, agreement_version: str = "2.1", ip_info: str = ""):
        """Запись факта принятия пользовательского соглашения"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO user_agreements (user_id, agreement_version, accepted_at, ip_info)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            ''', (user_id, agreement_version, ip_info))
            self.conn.commit()
            logger.info(f"Пользователь {user_id} принял соглашение версии {agreement_version}")
            return True
        except Exception as e:
            logger.error(f"Ошибка записи соглашения: {e}")
            return False

    def check_agreement_accepted(self, user_id: int, agreement_version: str = "2.1") -> bool:
        """Проверка, принял ли пользователь соглашение"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT 1 FROM user_agreements 
            WHERE user_id = ? AND agreement_version = ?
            LIMIT 1
        ''', (user_id, agreement_version))
        return cursor.fetchone() is not None

    def create_prepaid_order(self, user_id: int, username: str, service_type: str, price: int,
                             original_price: int = None, discount_applied: float = 0,
                             discount_type: str = None, promo_code: str = None,
                             referrer_id: int = None, needs_demographics: bool = True) -> int:
        """Создание заказа после оплаты"""
        cursor = self.conn.cursor()

        if original_price is None:
            original_price = price

        cursor.execute('''
            INSERT INTO orders (user_id, username, service_type, price, original_price,
                              payment_status, status, agreement_accepted, 
                              agreement_version, discount_applied, discount_type,
                              promo_code, referrer_id, needs_demographics,
                              created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'success', 'paid', TRUE, '2.1', ?, ?, ?, ?, ?, 
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ''', (user_id, username, service_type, price, original_price,
              discount_applied, discount_type, promo_code, referrer_id, needs_demographics))
        self.conn.commit()

        order_id = cursor.lastrowid
        logger.info(f"Создан предоплаченный заказ #{order_id} для @{username} ({service_type} - {price}₽)")
        return order_id

    def update_order_details(self, order_id: int, age: int = None, sex: str = None,
                             questions: str = None, documents: List[str] = None,
                             document_types: List[str] = None):
        """Обновление деталей заказа после оплаты"""
        cursor = self.conn.cursor()

        updates = []
        params = []

        if age is not None:
            updates.append("age = ?")
            params.append(age)

        if sex is not None:
            updates.append("sex = ?")
            params.append(sex)

        if questions is not None:
            updates.append("questions = ?")
            params.append(questions)

        if documents is not None and document_types is not None:
            updates.append("documents = ?")
            updates.append("document_types = ?")
            params.append(json.dumps(documents))
            params.append(json.dumps(document_types))

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(order_id)

        if updates:
            query = f"UPDATE orders SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            self.conn.commit()
            logger.info(f"Детали обновлены для заказа #{order_id}")

    def update_order_status(self, order_id: int, status: str,
                            admin_id: int = None, details: str = "") -> bool:
        try:
            cursor = self.conn.cursor()

            if status == OrderStatus.COMPLETED:
                # Устанавливаем время для уточнений (24 часа)
                clarify_until = datetime.now() + timedelta(hours=config.CLARIFICATION_TIME_LIMIT_HOURS)
                cursor.execute('''
                    UPDATE orders 
                    SET status = ?, answered_at = CURRENT_TIMESTAMP, 
                        admin_id = ?, updated_at = CURRENT_TIMESTAMP,
                        can_clarify_until = ?
                    WHERE id = ?
                ''', (status, admin_id, clarify_until, order_id))
            else:
                cursor.execute('''
                    UPDATE orders 
                    SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (status, order_id))

            self.conn.commit()
            logger.info(f"Статус заказа #{order_id} изменен на {status}")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления статуса заказа #{order_id}: {e}")
            return False

    def mark_order_needs_new_docs(self, order_id: int, reason: str, admin_id: int) -> bool:
        """Пометить заказ как нуждающийся в новых документах"""
        try:
            cursor = self.conn.cursor()

            # Обновляем статус заказа
            cursor.execute('''
                UPDATE orders 
                SET status = 'needs_new_docs', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (order_id,))

            # Добавляем запрос от админа
            cursor.execute('''
                INSERT INTO clarifications (order_id, user_id, message_text, is_from_user, is_admin_request)
                VALUES (?, ?, ?, FALSE, TRUE)
            ''', (order_id, admin_id, f"Админ запросил новые документы: {reason}"))

            self.conn.commit()
            logger.info(f"Заказ #{order_id} помечен как нуждающийся в новых документах")
            return True
        except Exception as e:
            logger.error(f"Ошибка при отметке заказа #{order_id}: {e}")
            return False

    def can_user_clarify(self, order_id: int, user_id: int) -> Tuple[bool, str]:
        """Проверка, может ли пользователь задать уточняющий вопрос"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT status, can_clarify_until, user_id
            FROM orders 
            WHERE id = ?
        ''', (order_id,))

        order = cursor.fetchone()
        if not order:
            return False, "Заказ не найден"

        status, can_clarify_until, order_user_id = order

        if order_user_id != user_id:
            return False, "Это не ваш заказ"

        if status not in [OrderStatus.COMPLETED, OrderStatus.NEEDS_NEW_DOCS]:
            return False, "Заказ еще не завершен"

        if status == OrderStatus.NEEDS_NEW_DOCS:
            return True, ""  # Для заказов с нужными документами - всегда можно

        if not can_clarify_until:
            return False, "Время для уточнений истекло"

        now = datetime.now()

        try:
            # Пробуем разные форматы даты
            if isinstance(can_clarify_until, str):
                # Пробуем с миллисекундами
                try:
                    clarify_time = datetime.strptime(can_clarify_until, '%Y-%m-%d %H:%M:%S.%f')
                except ValueError:
                    # Пробуем без миллисекунд
                    try:
                        clarify_time = datetime.strptime(can_clarify_until, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        # Если вообще не парсится, считаем что время истекло
                        return False, "Ошибка формата времени"
            else:
                clarify_time = can_clarify_until
        except Exception as e:
            logger.error(f"Ошибка парсинга времени уточнений: {e}")
            return False, "Ошибка проверки времени"

        if now > clarify_time:
            # Форматируем время для пользователя
            time_str = clarify_time.strftime('%d.%m.%Y %H:%M')
            return False, f"Время для уточнений истекло. Вы могли задавать вопросы до {time_str}"

        return True, ""

    def add_clarification(self, order_id: int, user_id: int, message_text: str,
                          message_type: str = "text", file_id: str = None,
                          is_from_user: bool = True, replied_to: int = None,
                          is_admin_request: bool = False) -> int:
        """Добавление уточняющего вопроса/ответа"""
        cursor = self.conn.cursor()

        # Если это вопрос от пользователя и не админский запрос, увеличиваем счетчик
        if is_from_user and not is_admin_request:
            cursor.execute('''
                UPDATE orders 
                SET clarification_count = clarification_count + 1,
                    last_clarification_at = CURRENT_TIMESTAMP,
                    status = 'awaiting_clarification',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (order_id,))

        cursor.execute('''
            INSERT INTO clarifications 
            (order_id, user_id, message_text, message_type, file_id, 
             is_from_user, replied_to_clarification_id, is_admin_request, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (order_id, user_id, message_text, message_type, file_id,
              is_from_user, replied_to, is_admin_request))

        clarification_id = cursor.lastrowid
        self.conn.commit()

        action = "вопрос" if is_from_user else "ответ"
        logger.info(f"Добавлено уточнение #{clarification_id} ({action}) для заказа #{order_id}")
        return clarification_id

    def get_clarifications(self, order_id: int, limit: int = 50) -> List[tuple]:
        """Получение истории уточнений для заказа"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM clarifications 
            WHERE order_id = ? 
            ORDER BY sent_at ASC
            LIMIT ?
        ''', (order_id, limit))
        return cursor.fetchall()

    def set_invoice_payload(self, order_id: int, invoice_payload: str) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE orders 
                SET invoice_payload = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (invoice_payload, order_id))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка установки invoice_payload для заказа #{order_id}: {e}")
            return False

    def process_payment(self, invoice_payload: str, provider_payment_id: str,
                        amount: int) -> Tuple[bool, Optional[int]]:
        try:
            cursor = self.conn.cursor()

            # Находим заказ по invoice_payload
            cursor.execute('SELECT id, user_id, price FROM orders WHERE invoice_payload = ?',
                           (invoice_payload,))
            order = cursor.fetchone()

            if not order:
                logger.error(f"Заказ с invoice_payload {invoice_payload} не найден")
                return False, None

            order_id, user_id, expected_price = order

            # Проверяем сумму (делим на 100, так как в копейках)
            expected_amount = expected_price * 100
            if abs(amount - expected_amount) > 1:  # Допускаем небольшую погрешность
                logger.warning(f"Несоответствие суммы для заказа #{order_id}: "
                               f"ожидалось {expected_amount}, получено {amount}")

            # Обновляем статус заказа
            cursor.execute('''
                UPDATE orders 
                SET payment_status = 'success', status = 'paid', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (order_id,))

            # Записываем платеж
            cursor.execute('''
                INSERT INTO payments (order_id, amount, status, provider_payment_id, 
                                    invoice_payload, payment_date)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (order_id, amount, PaymentStatus.SUCCESS,
                  provider_payment_id, invoice_payload))

            # Если есть реферер, начисляем бонус
            cursor.execute('SELECT referrer_id FROM orders WHERE id = ?', (order_id,))
            referrer_result = cursor.fetchone()
            if referrer_result and referrer_result[0]:
                referrer_id = referrer_result[0]
                bonus_amount = (amount / 100) * (config.REFERRER_BONUS_PERCENT / 100)

                # Обновляем реферальную запись
                cursor.execute('''
                    UPDATE referrals 
                    SET order_id = ?, referrer_bonus = ?, status = 'completed',
                        completed_at = CURRENT_TIMESTAMP
                    WHERE referred_id = ? AND status = 'pending'
                ''', (order_id, bonus_amount, user_id))

                logger.info(f"Начислен бонус {bonus_amount}₽ рефереру {referrer_id} за заказ #{order_id}")

            self.conn.commit()

            logger.info(f"Платеж для заказа #{order_id} обработан успешно")
            return True, order_id

        except Exception as e:
            logger.error(f"Ошибка обработки платежа: {e}")
            self.conn.rollback()
            return False, None

    def get_order_by_id(self, order_id: int) -> Optional[tuple]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        return cursor.fetchone()

    def get_user_orders(self, user_id: int, limit: int = 10) -> List[tuple]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM orders 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (user_id, limit))
        return cursor.fetchall()

    def get_all_orders(self, limit: int = 20) -> List[tuple]:
        """Получение всех заказов (для админа)"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM orders 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()

    def get_pending_orders(self, limit: int = 20) -> List[tuple]:
        """Получение ожидающих заказов (для админа)"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM orders 
            WHERE status IN ('pending', 'processing', 'awaiting_clarification', 'needs_new_docs')
            ORDER BY created_at ASC 
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()

    def save_rating(self, order_id: int, rating: int) -> bool:
        """Сохранение оценки заказа"""
        try:
            cursor = self.conn.cursor()

            # Сохраняем в таблицу ratings
            cursor.execute('''
                INSERT OR REPLACE INTO ratings (order_id, rating)
                VALUES (?, ?)
            ''', (order_id, rating))

            # Обновляем оценку в таблице orders
            cursor.execute('''
                UPDATE orders 
                SET rating = ?
                WHERE id = ?
            ''', (rating, order_id))

            self.conn.commit()
            logger.info(f"Оценка {rating} сохранена для заказа #{order_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения оценки для заказа #{order_id}: {e}")
            return False

    # ========== ПРОМОКОДЫ ==========

    def create_promo_code(self, code: str, discount_type: str, discount_value: float,
                          uses_left: int = -1, valid_until: datetime = None,
                          description: str = "") -> bool:
        """Создание промокода"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO promo_codes (code, discount_type, discount_value, 
                                       uses_left, valid_until, description)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (code.upper(), discount_type, discount_value, uses_left, valid_until, description))
            self.conn.commit()
            logger.info(f"Создан промокод: {code} ({discount_type} {discount_value})")
            return True
        except sqlite3.IntegrityError:
            logger.error(f"Промокод {code} уже существует")
            return False
        except Exception as e:
            logger.error(f"Ошибка создания промокода: {e}")
            return False

    def get_promo_code(self, code: str) -> Optional[tuple]:
        """Получение информации о промокоде"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM promo_codes 
            WHERE code = ? AND is_active = TRUE 
            AND (valid_until IS NULL OR valid_until > CURRENT_TIMESTAMP)
        ''', (code.upper(),))
        return cursor.fetchone()

    def apply_promo_code(self, promo_code: str, user_id: int, order_id: int,
                         original_price: int) -> Tuple[float, int, str]:
        """Применение промокода к заказу"""
        promo = self.get_promo_code(promo_code)
        if not promo:
            return 0, original_price, "Промокод не найден или недействителен"

        promo_id, code, discount_type, discount_value, uses_left, valid_until, created_at, is_active, description = promo

        # Проверка количества использований
        if uses_left == 0:
            return 0, original_price, "Промокод закончился"

        # Проверка на повторное использование одним пользователем
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT 1 FROM used_promo_codes 
            WHERE user_id = ? AND promo_code = ?
        ''', (user_id, code))
        if cursor.fetchone():
            return 0, original_price, "Вы уже использовали этот промокод"

        # Рассчитываем скидку
        if discount_type == DiscountType.PERCENT:
            discount_amount = original_price * (discount_value / 100)
            final_price = max(0, original_price - discount_amount)
        else:  # FIXED
            discount_amount = min(discount_value, original_price)
            final_price = max(0, original_price - discount_amount)

        # Уменьшаем количество использований
        if uses_left > 0:
            cursor.execute('''
                UPDATE promo_codes 
                SET uses_left = uses_left - 1 
                WHERE id = ?
            ''', (promo_id,))

        # Записываем использование
        cursor.execute('''
            INSERT INTO used_promo_codes (user_id, promo_code, order_id, discount_amount)
            VALUES (?, ?, ?, ?)
        ''', (user_id, code, order_id, discount_amount))

        self.conn.commit()

        logger.info(f"Промокод {code} применен к заказу #{order_id}, скидка: {discount_amount}₽")
        return discount_amount, int(final_price), ""

    def get_all_promo_codes(self) -> List[tuple]:
        """Получение всех промокодов"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM promo_codes ORDER BY created_at DESC')
        return cursor.fetchall()

    def deactivate_promo_code(self, code: str) -> bool:
        """Деактивация промокода"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                UPDATE promo_codes 
                SET is_active = FALSE 
                WHERE code = ?
            ''', (code.upper(),))
            self.conn.commit()
            logger.info(f"Промокод {code} деактивирован")
            return True
        except Exception as e:
            logger.error(f"Ошибка деактивации промокода: {e}")
            return False

    # ========== РЕФЕРАЛЬНАЯ СИСТЕМА ==========

    def create_referral(self, referrer_id: int, referred_id: int) -> bool:
        """Создание реферальной связи"""
        if referrer_id == referred_id:
            return False

        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO referrals (referrer_id, referred_id)
                VALUES (?, ?)
            ''', (referrer_id, referred_id))
            self.conn.commit()

            if cursor.rowcount > 0:
                logger.info(f"Создана реферальная связь: {referrer_id} → {referred_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка создания реферальной связи: {e}")
            return False

    def get_referrer_stats(self, user_id: int) -> Dict[str, Any]:
        """Статистика по рефералам пользователя"""
        try:
            cursor = self.conn.cursor()

            # Проверяем существование таблицы referrals
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='referrals'")
            if not cursor.fetchone():
                # Таблица не существует
                return {
                    'total_referred': 0,
                    'completed_referred': 0,
                    'total_bonus': 0.0
                }

            # Количество приглашенных
            cursor.execute('''
                SELECT COUNT(*) FROM referrals 
                WHERE referrer_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            total_referred = result[0] if result else 0

            # Количество завершенных заказов
            cursor.execute('''
                SELECT COUNT(*) FROM referrals 
                WHERE referrer_id = ? AND status = 'completed'
            ''', (user_id,))
            result = cursor.fetchone()
            completed_referred = result[0] if result else 0

            # Общая сумма бонусов
            cursor.execute('''
                SELECT COALESCE(SUM(referrer_bonus), 0) FROM referrals 
                WHERE referrer_id = ? AND status = 'completed'
            ''', (user_id,))
            result = cursor.fetchone()
            total_bonus = float(result[0]) if result and result[0] else 0.0

            return {
                'total_referred': total_referred,
                'completed_referred': completed_referred,
                'total_bonus': total_bonus
            }

        except Exception as e:
            logger.error(f"Ошибка в get_referrer_stats: {e}")
            return {
                'total_referred': 0,
                'completed_referred': 0,
                'total_bonus': 0.0
            }

    def check_referral_discount(self, user_id: int) -> Tuple[bool, float]:
        """Проверка, имеет ли пользователь право на реферальную скидку"""
        cursor = self.conn.cursor()

        # Проверяем, является ли пользователь приглашенным
        cursor.execute('''
            SELECT 1 FROM referrals 
            WHERE referred_id = ? AND status = 'pending'
        ''', (user_id,))

        if cursor.fetchone():
            # Начисляем скидку приглашенному
            discount_percent = config.REFERRED_DISCOUNT_PERCENT
            return True, discount_percent

        return False, 0

    def apply_referral_discount(self, user_id: int, order_id: int, original_price: int) -> Tuple[float, int, int]:
        """Применение реферальной скидки"""
        cursor = self.conn.cursor()

        # Получаем реферальную запись
        cursor.execute('''
            SELECT id, referrer_id FROM referrals 
            WHERE referred_id = ? AND status = 'pending'
        ''', (user_id,))

        referral = cursor.fetchone()
        if not referral:
            return 0, original_price, 0

        referral_id, referrer_id = referral

        # Рассчитываем скидку
        discount_amount = original_price * (config.REFERRED_DISCOUNT_PERCENT / 100)
        final_price = max(0, original_price - discount_amount)

        # Обновляем реферальную запись
        cursor.execute('''
            UPDATE referrals 
            SET referred_discount = ?, order_id = ?
            WHERE id = ?
        ''', (discount_amount, order_id, referral_id))

        self.conn.commit()

        logger.info(f"Реферальная скидка {discount_amount}₽ применена для пользователя {user_id}")
        return discount_amount, int(final_price), referrer_id

    def get_all_referrals_stats(self) -> Dict[str, Any]:
        """Общая статистика по рефералам"""
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM referrals")
        total_referrals = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM referrals WHERE status = 'completed'")
        completed_referrals = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(referrer_bonus), 0) FROM referrals WHERE status = 'completed'")
        total_bonuses = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(referred_discount), 0) FROM referrals")
        total_discounts = cursor.fetchone()[0]

        # Топ рефереров
        cursor.execute('''
            SELECT referrer_id, COUNT(*) as count, SUM(referrer_bonus) as total_bonus
            FROM referrals 
            WHERE status = 'completed'
            GROUP BY referrer_id 
            ORDER BY total_bonus DESC 
            LIMIT 10
        ''')
        top_referrers = cursor.fetchall()

        return {
            'total_referrals': total_referrals,
            'completed_referrals': completed_referrals,
            'total_bonuses': total_bonuses,
            'total_discounts': total_discounts,
            'top_referrers': top_referrers
        }

    # ========== БЫСТРЫЕ ШАБЛОНЫ ==========

    def get_quick_templates(self) -> List[tuple]:
        """Получение всех шаблонов"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM quick_templates ORDER BY name')
        return cursor.fetchall()

    def get_quick_template(self, template_id: int) -> Optional[str]:
        """Получение текста шаблона по ID"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT text FROM quick_templates WHERE id = ?', (template_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def add_quick_template(self, name: str, text: str) -> bool:
        """Добавление нового шаблона"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO quick_templates (name, text)
                VALUES (?, ?)
            ''', (name, text))
            self.conn.commit()
            logger.info(f"Добавлен шаблон: {name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления шаблона: {e}")
            return False

    def update_quick_template(self, template_id: int, name: str = None, text: str = None) -> bool:
        """Обновление шаблона"""
        cursor = self.conn.cursor()
        try:
            if name and text:
                cursor.execute('''
                    UPDATE quick_templates 
                    SET name = ?, text = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (name, text, template_id))
            elif name:
                cursor.execute('''
                    UPDATE quick_templates 
                    SET name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (name, template_id))
            elif text:
                cursor.execute('''
                    UPDATE quick_templates 
                    SET text = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (text, template_id))

            self.conn.commit()
            logger.info(f"Обновлен шаблон ID: {template_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления шаблона: {e}")
            return False

    def delete_quick_template(self, template_id: int) -> bool:
        """Удаление шаблона"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('DELETE FROM quick_templates WHERE id = ?', (template_id,))
            self.conn.commit()
            logger.info(f"Удален шаблон ID: {template_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления шаблона: {e}")
            return False

    # ========== СТАТИСТИКА ==========

    def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        cursor = self.conn.cursor()

        # Общая статистика
        cursor.execute("SELECT COUNT(*) FROM orders")
        total_orders = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = DATE('now')")
        today_orders = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
        pending_orders = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'")
        completed_orders = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'awaiting_clarification'")
        clarification_orders = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'needs_new_docs'")
        new_docs_orders = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM orders WHERE payment_status = 'success'")
        paid_orders = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(price) FROM orders WHERE payment_status = 'success'")
        avg_price = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(price) FROM orders WHERE payment_status = 'success'")
        total_revenue = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(discount_applied) FROM orders WHERE payment_status = 'success'")
        total_discounts = cursor.fetchone()[0] or 0

        cursor.execute(f"""
            SELECT COUNT(DISTINCT user_id) 
            FROM orders 
            WHERE created_at >= datetime('now', '-{days} days')
        """)
        unique_users = cursor.fetchone()[0]

        # Статистика по уточнениям
        cursor.execute("SELECT COUNT(*) FROM clarifications WHERE is_from_user = TRUE")
        total_clarifications = cursor.fetchone()[0]

        # Статистика по типам услуг
        cursor.execute("""
            SELECT service_type, COUNT(*), AVG(price), SUM(price)
            FROM orders 
            GROUP BY service_type
            ORDER BY COUNT(*) DESC
        """)
        service_stats = cursor.fetchall()

        # Статистика по дням (последние 7 дней)
        cursor.execute("""
            SELECT DATE(created_at), COUNT(*), SUM(CASE WHEN payment_status = 'success' THEN price ELSE 0 END)
            FROM orders 
            WHERE created_at >= datetime('now', '-7 days')
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at)
        """)
        daily_stats = cursor.fetchall()

        # Статистика по принятию соглашений
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM user_agreements")
        agreements_accepted = cursor.fetchone()[0]

        # Статистика по налогам (неотчитанные платежи)
        cursor.execute(
            "SELECT COUNT(*), SUM(amount/100) FROM payments WHERE tax_reported = FALSE AND status = 'success'")
        unreported = cursor.fetchone()
        unreported_count = unreported[0] or 0
        unreported_amount = unreported[1] or 0

        # Статистика по оценкам
        cursor.execute("SELECT COUNT(*), AVG(rating) FROM ratings")
        rating_stats = cursor.fetchone()
        total_ratings = rating_stats[0] or 0
        avg_rating = rating_stats[1] or 0

        # Распределение оценки
        cursor.execute("""
            SELECT rating, COUNT(*) 
            FROM ratings 
            GROUP BY rating 
            ORDER BY rating DESC
        """)
        rating_distribution = cursor.fetchall()

        # Статистика по промокодам
        cursor.execute("SELECT COUNT(*) FROM promo_codes")
        total_promo_codes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM used_promo_codes")
        promo_uses = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(discount_amount), 0) FROM used_promo_codes")
        promo_discounts = cursor.fetchone()[0]

        return {
            'total_orders': total_orders,
            'today_orders': today_orders,
            'pending_orders': pending_orders,
            'completed_orders': completed_orders,
            'clarification_orders': clarification_orders,
            'new_docs_orders': new_docs_orders,
            'paid_orders': paid_orders,
            'avg_price': int(avg_price),
            'total_revenue': int(total_revenue),
            'total_discounts': int(total_discounts),
            'unique_users': unique_users,
            'agreements_accepted': agreements_accepted,
            'unreported_payments': unreported_count,
            'unreported_amount': int(unreported_amount),
            'total_ratings': total_ratings,
            'avg_rating': float(avg_rating),
            'rating_distribution': rating_distribution,
            'total_clarifications': total_clarifications,
            'service_stats': service_stats,
            'daily_stats': daily_stats,
            'total_promo_codes': total_promo_codes,
            'promo_uses': promo_uses,
            'promo_discounts': promo_discounts
        }

    def mark_tax_reported(self, order_id: int) -> bool:
        """Пометить платеж как отчитанный в налоговой"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE payments 
                SET tax_reported = TRUE 
                WHERE order_id = ? AND status = 'success'
            ''', (order_id,))

            cursor.execute('''
                UPDATE orders 
                SET tax_reported = TRUE 
                WHERE id = ?
            ''', (order_id,))

            self.conn.commit()
            logger.info(f"Платеж по заказу #{order_id} отмечен как отчитанный в налоговой")
            return True
        except Exception as e:
            logger.error(f"Ошибка отметки налогового отчета: {e}")
            return False

    def change_order_price(self, order_id: int, new_price: int) -> bool:
        """Изменение цены заказа"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE orders 
                SET price = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_price, order_id))
            self.conn.commit()
            logger.info(f"Цена заказа #{order_id} изменена на {new_price}₽")
            return True
        except Exception as e:
            logger.error(f"Ошибка изменения цены заказа #{order_id}: {e}")
            return False

    def create_referrals_table_if_not_exists(self):
        """Создать таблицу referrals если она не существует"""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                order_id INTEGER,
                referrer_bonus REAL DEFAULT 0,
                referred_discount REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(referrer_id, referred_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id ON referrals(referrer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_referred_id ON referrals(referred_id)')
        self.conn.commit()
        logger.info("Таблица referrals проверена/создана")