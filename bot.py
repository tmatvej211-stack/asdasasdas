# lolz_market_bot.py
import sqlite3
import json
import uuid
import logging
import asyncio
import html
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode
from functools import wraps

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8973197320:AAFgg1rOOK2ogmkGNg3Vj1Bnl6fCkEj-Hxo"  # Замените на ваш токен!

# Администраторы (ID через запятую)
SUPER_ADMIN_IDS = {5688999382, 8727416659}  # Замените на ваши ID

# Базовые настройки
TON_ADDRESS = "UQCl9NJH5wQF-U_isFQnhPW9YUMSKpEvt9c7JdZoVF49afhn"
SBP_CARD = "2204320988836187 - Озон банк"
MANAGER_USERNAME = "@LolzTeamChanger"

# ========== ЛОГГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self, db_name="lolz_market.db"):
        self.db_name = db_name
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_name)
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                ton_wallet TEXT,
                card_details TEXT,
                balance TON REAL DEFAULT 0,
                balance_rub REAL DEFAULT 0,
                balance_usd REAL DEFAULT 0,
                successful_deals INTEGER DEFAULT 0,
                lang TEXT DEFAULT 'ru',
                is_admin INTEGER DEFAULT 0,
                is_verified INTEGER DEFAULT 0,
                referrals INTEGER DEFAULT 0,
                referred_by INTEGER,
                join_date TEXT,
                last_active TEXT
            )
        ''')
        
        # Таблица товаров/лотов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                item_id TEXT PRIMARY KEY,
                seller_id INTEGER,
                game TEXT,
                title TEXT,
                description TEXT,
                price REAL,
                currency TEXT DEFAULT 'TON',
                screenshots TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT,
                views INTEGER DEFAULT 0,
                FOREIGN KEY (seller_id) REFERENCES users(user_id)
            )
        ''')
        
        # Таблица сделок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deals (
                deal_id TEXT PRIMARY KEY,
                item_id TEXT,
                seller_id INTEGER,
                buyer_id INTEGER,
                amount REAL,
                currency TEXT,
                status TEXT DEFAULT 'pending',
                payment_method TEXT,
                created_at TEXT,
                completed_at TEXT,
                FOREIGN KEY (item_id) REFERENCES items(item_id),
                FOREIGN KEY (seller_id) REFERENCES users(user_id),
                FOREIGN KEY (buyer_id) REFERENCES users(user_id)
            )
        ''')
        
        # Таблица игр
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                name TEXT,
                icon TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # Добавляем игры по умолчанию
        default_games = [
            ('brawl_stars', 'Brawl Stars', '🥊'),
            ('steam', 'Steam', '🎮'),
            ('cs2', 'CS:GO/CS2', '🔫'),
            ('dota2', 'Dota 2', '⚔️'),
            ('valorant', 'Valorant', '🎯'),
            ('genshin', 'Genshin Impact', '🗡️'),
            ('minecraft', 'Minecraft', '⛏️'),
            ('roblox', 'Roblox', '🧸'),
            ('fortnite', 'Fortnite', '🏆'),
            ('pubg', 'PUBG', '🪂'),
            ('apex', 'Apex Legends', '🔥'),
            ('wow', 'World of Warcraft', '🐉'),
            ('osu', 'osu!', '🎵'),
            ('telegram', 'Telegram Premium', '📱'),
            ('other', 'Другое', '📦'),
        ]
        
        for game_id, name, icon in default_games:
            cursor.execute('''
                INSERT OR IGNORE INTO games (game_id, name, icon) VALUES (?, ?, ?)
            ''', (game_id, name, icon))
        
        # Таблица для жалоб
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS complaints (
                complaint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                target_id INTEGER,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    
    # === Пользователи ===
    def add_user(self, user_id: int, username: str = None, referred_by: int = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (user_id, username, join_date, referred_by, is_admin)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username or str(user_id), datetime.now().strftime("%d.%m.%Y"), 
                  referred_by, 1 if user_id in SUPER_ADMIN_IDS else 0))
            conn.commit()
            logger.info(f"New user added: {user_id}")
        
        conn.close()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'user_id': row[0],
                'username': row[1],
                'ton_wallet': row[2],
                'card_details': row[3],
                'balance_ton': row[4],
                'balance_rub': row[5],
                'balance_usd': row[6],
                'successful_deals': row[7],
                'lang': row[8],
                'is_admin': row[9],
                'is_verified': row[10],
                'referrals': row[11],
                'referred_by': row[12],
                'join_date': row[13],
                'last_active': row[14],
            }
        return None
    
    def update_user_activity(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET last_active = ? WHERE user_id = ?', 
                      (datetime.now().strftime("%d.%m.%Y %H:%M"), user_id))
        conn.commit()
        conn.close()
    
    def is_admin(self, user_id: int) -> bool:
        return user_id in SUPER_ADMIN_IDS or self.get_user(user_id, {}).get('is_admin', False)
    
    # === Товары ===
    def add_item(self, seller_id: int, game: str, title: str, description: str, 
                 price: float, currency: str, screenshots: List[str]) -> str:
        item_id = str(uuid.uuid4())[:12]
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO items (item_id, seller_id, game, title, description, price, currency, 
                             screenshots, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (item_id, seller_id, game, title, description, price, currency, 
              json.dumps(screenshots), datetime.now().strftime("%d.%m.%Y %H:%M")))
        conn.commit()
        conn.close()
        return item_id
    
    def get_item(self, item_id: str) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM items WHERE item_id = ?', (item_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'item_id': row[0],
                'seller_id': row[1],
                'game': row[2],
                'title': row[3],
                'description': row[4],
                'price': row[5],
                'currency': row[6],
                'screenshots': json.loads(row[7]) if row[7] else [],
                'status': row[8],
                'created_at': row[9],
                'views': row[10],
            }
        return None
    
    def search_items(self, query: str, game: str = None) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if game and game != 'all':
            cursor.execute('''
                SELECT * FROM items 
                WHERE status = 'active' AND game = ? 
                AND (title LIKE ? OR description LIKE ?)
                ORDER BY created_at DESC
            ''', (game, f'%{query}%', f'%{query}%'))
        else:
            cursor.execute('''
                SELECT * FROM items 
                WHERE status = 'active' 
                AND (title LIKE ? OR description LIKE ?)
                ORDER BY created_at DESC
            ''', (f'%{query}%', f'%{query}%'))
        
        rows = cursor.fetchall()
        conn.close()
        
        items = []
        for row in rows:
            items.append({
                'item_id': row[0],
                'seller_id': row[1],
                'game': row[2],
                'title': row[3],
                'description': row[4],
                'price': row[5],
                'currency': row[6],
                'screenshots': json.loads(row[7]) if row[7] else [],
                'status': row[8],
                'created_at': row[9],
                'views': row[10],
            })
        return items
    
    def get_user_items(self, user_id: int) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM items WHERE seller_id = ? ORDER BY created_at DESC', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        items = []
        for row in rows:
            items.append({
                'item_id': row[0],
                'seller_id': row[1],
                'game': row[2],
                'title': row[3],
                'description': row[4],
                'price': row[5],
                'currency': row[6],
                'screenshots': json.loads(row[7]) if row[7] else [],
                'status': row[8],
                'created_at': row[9],
                'views': row[10],
            })
        return items
    
    def delete_item(self, item_id: str, user_id: int) -> bool:
        item = self.get_item(item_id)
        if not item or item['seller_id'] != user_id:
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE items SET status = ? WHERE item_id = ?', ('deleted', item_id))
        conn.commit()
        conn.close()
        return True
    
    # === Сделки ===
    def create_deal(self, item_id: str, buyer_id: int) -> str:
        item = self.get_item(item_id)
        if not item:
            return None
        
        deal_id = str(uuid.uuid4())[:8]
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO deals (deal_id, item_id, seller_id, buyer_id, amount, currency, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (deal_id, item_id, item['seller_id'], buyer_id, item['price'], item['currency'],
              datetime.now().strftime("%d.%m.%Y %H:%M")))
        conn.commit()
        conn.close()
        return deal_id
    
    def get_deal(self, deal_id: str) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM deals WHERE deal_id = ?', (deal_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'deal_id': row[0],
                'item_id': row[1],
                'seller_id': row[2],
                'buyer_id': row[3],
                'amount': row[4],
                'currency': row[5],
                'status': row[6],
                'payment_method': row[7],
                'created_at': row[8],
                'completed_at': row[9],
            }
        return None
    
    def update_deal_status(self, deal_id: str, status: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE deals SET status = ?, completed_at = ? WHERE deal_id = ?',
                      (status, datetime.now().strftime("%d.%m.%Y %H:%M") if status == 'completed' else None, deal_id))
        conn.commit()
        conn.close()
    
    def get_user_deals(self, user_id: int) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM deals 
            WHERE seller_id = ? OR buyer_id = ? 
            ORDER BY created_at DESC
        ''', (user_id, user_id))
        rows = cursor.fetchall()
        conn.close()
        
        deals = []
        for row in rows:
            deals.append({
                'deal_id': row[0],
                'item_id': row[1],
                'seller_id': row[2],
                'buyer_id': row[3],
                'amount': row[4],
                'currency': row[5],
                'status': row[6],
                'created_at': row[8],
            })
        return deals
    
    # === Игры ===
    def get_games(self) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT game_id, name, icon FROM games WHERE is_active = 1 ORDER BY name')
        rows = cursor.fetchall()
        conn.close()
        return [{'id': r[0], 'name': r[1], 'icon': r[2]} for r in rows]
    
    # === Статистика ===
    def get_stats(self) -> Dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM items WHERE status = "active"')
        active_items = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM deals')
        total_deals = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM deals WHERE status = "completed"')
        completed_deals = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(price) FROM deals WHERE status = "completed"')
        total_volume = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_users': total_users,
            'active_items': active_items,
            'total_deals': total_deals,
            'completed_deals': completed_deals,
            'total_volume': total_volume,
        }

# ========== ИНИЦИАЛИЗАЦИЯ ==========
db = Database()

# Эмодзи для кнопок
EMOJI = {
    'shop': '🛒', 'sell': '📦', 'search': '🔍', 'profile': '👤',
    'balance': '💰', 'deals': '📋', 'admin': '⚙️', 'support': '📞',
    'back': '◀️', 'check': '✅', 'cross': '❌', 'warning': '⚠️',
    'ton': '⚡', 'rub': '🇷🇺', 'usd': '💵', 'stars': '⭐',
    'verified': '✅', 'unverified': '❌'
}

# ========== ДЕКОРАТОРЫ ==========
def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not db.is_admin(user_id):
            await update.message.reply_text(f"{EMOJI['cross']} <b>Доступ запрещён!</b>\nЭта команда только для администраторов.", 
                                           parse_mode=ParseMode.HTML)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Главное меню"""
    user = db.get_user(user_id)
    is_admin = db.is_admin(user_id)
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['shop']} Магазин", callback_data='browse_items'),
         InlineKeyboardButton(f"{EMOJI['sell']} Выставить товар", callback_data='sell_menu')],
        [InlineKeyboardButton(f"{EMOJI['search']} Поиск", callback_data='search_menu'),
         InlineKeyboardButton(f"{EMOJI['deals']} Мои сделки", callback_data='my_deals')],
        [InlineKeyboardButton(f"{EMOJI['profile']} Профиль", callback_data='profile'),
         InlineKeyboardButton(f"{EMOJI['balance']} Баланс", callback_data='balance_menu')],
        [InlineKeyboardButton(f"{EMOJI['support']} Поддержка", url=f'https://t.me/{MANAGER_USERNAME[1:]}')],
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton(f"{EMOJI['admin']} Админ-панель", callback_data='admin_panel')])
    
    return InlineKeyboardMarkup(keyboard)

def get_games_keyboard(prefix: str = 'game_') -> InlineKeyboardMarkup:
    """Клавиатура с играми"""
    games = db.get_games()
    keyboard = []
    row = []
    
    for game in games:
        row.append(InlineKeyboardButton(f"{game['icon']} {game['name']}", callback_data=f'{prefix}{game["id"]}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='menu')])
    return InlineKeyboardMarkup(keyboard)

def get_items_keyboard(items: List[Dict], page: int = 0, items_per_page: int = 5, prefix: str = 'item_') -> Tuple[str, InlineKeyboardMarkup]:
    """Клавиатура для списка товаров"""
    total = len(items)
    start = page * items_per_page
    end = min(start + items_per_page, total)
    
    if not items:
        return "📭 <b>Товары не найдены</b>", InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='menu')]])
    
    text = f"🛒 <b>Товары</b> (стр. {page + 1}/{(total + items_per_page - 1) // items_per_page})\n\n"
    
    keyboard = []
    for item in items[start:end]:
        keyboard.append([InlineKeyboardButton(
            f"{item.get('game_icon', '📦')} {item['title'][:30]} - {item['price']} {item['currency']}",
            callback_data=f'{prefix}{item["item_id"]}'
        )])
    
    # Пагинация
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data=f'page_{page - 1}'))
    if end < total:
        nav_row.append(InlineKeyboardButton("Вперёд ▶️", callback_data=f'page_{page + 1}'))
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='menu')])
    
    return text, InlineKeyboardMarkup(keyboard)

# ========== ОБРАБОТЧИКИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /start"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Обработка реферальной ссылки
    args = context.args
    referred_by = int(args[0]) if args and args[0].isdigit() else None
    
    db.add_user(user_id, username, referred_by)
    db.update_user_activity(user_id)
    
    welcome_text = f"""
<b>🛡️ Добро пожаловать в Lolz Market!</b>

{EMOJI['shop']} <b>Крупнейшая P2P-площадка</b>

<b>Что мы предлагаем:</b>
• {EMOJI['sell']} Продажа игровых аккаунтов
• {EMOJI['balance']} Безопасные сделки с гарантом
• {EMOJI['check']} Защита продавца и покупателя
• {EMOJI['support']} Поддержка 24/7

<b>Доступные игры:</b> Brawl Stars, Steam, CS2, Dota 2, Valorant и другие!

{EMOJI['shop']} <b>Начните прямо сейчас!</b>
"""
    
    await update.message.reply_photo(
        photo="https://i.ibb.co/Y49N8TYG/photo.jpg",
        caption=welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    await query.answer()
    db.update_user_activity(user_id)
    
    # Главное меню
    if data == 'menu':
        await query.message.edit_caption(
            caption="🛡️ <b>Главное меню</b>\n\nВыберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    # Меню выставления товара
    elif data == 'sell_menu':
        context.user_data['selling'] = {'step': 'game'}
        await query.message.edit_caption(
            caption=f"{EMOJI['sell']} <b>Выберите игру для товара:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard('sell_game_')
        )
        return
    
    elif data.startswith('sell_game_'):
        game_id = data.replace('sell_game_', '')
        games = db.get_games()
        game = next((g for g in games if g['id'] == game_id), None)
        
        if game:
            context.user_data['selling']['game'] = game_id
            context.user_data['selling']['game_name'] = game['name']
            context.user_data['selling']['step'] = 'title'
            
            await query.message.edit_caption(
                caption=f"{EMOJI['sell']} <b>Выставление товара</b>\n\n"
                       f"Игра: {game['icon']} {game['name']}\n\n"
                       f"<b>Введите название товара:</b>\n"
                       f"<i>Пример: Brawl Stars аккаунт 50к трофеев</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='sell_menu')]])
            )
        return
    
    # Поиск
    elif data == 'search_menu':
        await query.message.edit_caption(
            caption=f"{EMOJI['search']} <b>Поиск товаров</b>\n\n"
                   f"Выберите игру или отправьте текстовый поиск:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard('search_game_')
        )
        context.user_data['search_mode'] = True
        return
    
    elif data.startswith('search_game_'):
        game_id = data.replace('search_game_', '')
        if game_id == 'all':
            context.user_data['search_game'] = None
        else:
            games = db.get_games()
            game = next((g for g in games if g['id'] == game_id), None)
            context.user_data['search_game'] = game_id
            context.user_data['search_game_name'] = game['name'] if game else None
        
        await query.message.edit_caption(
            caption=f"{EMOJI['search']} <b>Поиск товаров</b>\n\n"
                   f"<b>Отправьте текст для поиска:</b>\n"
                   f"<i>Пример: аккаунт с легендарками</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='search_menu')]])
        )
        context.user_data['awaiting_search'] = True
    
    # Просмотр товаров
    elif data == 'browse_items':
        items = db.search_items('', 'all')
        text, keyboard = get_items_keyboard(items, 0, 5, 'view_item_')
        await query.message.edit_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    
    elif data.startswith('view_item_'):
        item_id = data.replace('view_item_', '')
        item = db.get_item(item_id)
        
        if not item or item['status'] != 'active':
            await query.message.edit_caption(
                caption=f"{EMOJI['cross']} <b>Товар не найден или удалён</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='browse_items')]])
            )
            return
        
        # Формируем описание
        screenshots = item.get('screenshots', [])
        seller = db.get_user(item['seller_id'])
        
        text = f"""
{EMOJI['shop']} <b>{item['title']}</b>

{EMOJI['balance']} <b>Цена:</b> {item['price']} {item['currency']}
{EMOJI['profile']} <b>Продавец:</b> @{seller['username'] if seller else '?'}
{EMOJI['check']} <b>Статус:</b> {'Верифицирован' if seller and seller['is_verified'] else 'Не верифицирован'}

<b>📝 Описание:</b>
{item['description']}

{EMOJI['warning']} <i>После оплаты средства замораживаются до получения товара!</i>
"""
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['balance']} Купить", callback_data=f'buy_item_{item_id}')],
            [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='browse_items')],
        ]
        
        # Отправка с фото
        if screenshots:
            media = []
            for i, ss in enumerate(screenshots[:5]):
                if ss.startswith('http'):
                    if i == 0:
                        await query.message.edit_media(
                            media=InputMediaPhoto(media=ss, caption=text, parse_mode=ParseMode.HTML),
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                    else:
                        await query.message.reply_photo(ss)
            return
        
        await query.message.edit_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # Покупка товара
    elif data.startswith('buy_item_'):
        item_id = data.replace('buy_item_', '')
        item = db.get_item(item_id)
        
        if not item or item['status'] != 'active':
            await query.message.edit_caption(
                caption=f"{EMOJI['cross']} <b>Товар уже продан или удалён!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='browse_items')]])
            )
            return
        
        if item['seller_id'] == user_id:
            await query.message.edit_caption(
                caption=f"{EMOJI['warning']} <b>Вы не можете купить свой товар!</b>",
                parse_mode=ParseMode.HTML
            )
            return
        
        context.user_data['buying_item'] = item_id
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['ton']} TON", callback_data=f'pay_method_TON_{item_id}'),
             InlineKeyboardButton(f"{EMOJI['rub']} RUB", callback_data=f'pay_method_RUB_{item_id}')],
            [InlineKeyboardButton(f"{EMOJI['usd']} USD", callback_data=f'pay_method_USD_{item_id}'),
             InlineKeyboardButton(f"{EMOJI['stars']} Stars", callback_data=f'pay_method_STARS_{item_id}')],
            [InlineKeyboardButton(f"{EMOJI['back']} Отмена", callback_data=f'view_item_{item_id}')],
        ]
        
        await query.message.edit_caption(
            caption=f"{EMOJI['balance']} <b>Выберите способ оплаты</b>\n\n"
                   f"Товар: {item['title']}\n"
                   f"Сумма: {item['price']} {item['currency']}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data.startswith('pay_method_'):
        parts = data.split('_')
        method = parts[2]
        item_id = parts[3]
        item = db.get_item(item_id)
        
        if not item:
            await query.message.edit_caption(f"{EMOJI['cross']} <b>Ошибка!</b>", parse_mode=ParseMode.HTML)
            return
        
        # Создаём сделку
        deal_id = db.create_deal(item_id, user_id)
        
        if method == 'TON':
            payment_text = f"""
{EMOJI['ton']} <b>Оплата TON</b>

<b>Сделка:</b> #{deal_id}
<b>Товар:</b> {item['title']}
<b>Сумма:</b> {item['price']} TON

<b>💳 Реквизиты для оплаты:</b>
<code>{TON_ADDRESS}</code>

<b>Инструкция:</b>
1. Переведите {item['price']} TON на указанный кошелёк
2. Нажмите кнопку "✅ Я оплатил"
3. После проверки вы получите товар

{EMOJI['warning']} <b>Важно:</b> Не отправляйте средства напрямую продавцу!
"""
        else:
            payment_text = f"""
{EMOJI['rub']} <b>Оплата картой</b>

<b>Сделка:</b> #{deal_id}
<b>Товар:</b> {item['title']}
<b>Сумма:</b> {item['price']} {method}

<b>💳 Реквизиты для оплаты:</b>
<code>{SBP_CARD}</code>

<b>Инструкция:</b>
1. Переведите {item['price']} {method} по реквизитам
2. Сохраните чек перевода
3. Нажмите кнопку "✅ Я оплатил"

{EMOJI['warning']} <b>Важно:</b> Отправьте чек в поддержку для подтверждения!
"""
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['check']} Я оплатил", callback_data=f'confirm_payment_{deal_id}')],
            [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f'view_item_{item_id}')],
        ]
        
        await query.message.edit_caption(
            caption=payment_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # Подтверждение оплаты
    elif data.startswith('confirm_payment_'):
        deal_id = data.replace('confirm_payment_', '')
        deal = db.get_deal(deal_id)
        
        if not deal:
            await query.message.edit_caption(f"{EMOJI['cross']} <b>Сделка не найдена</b>", parse_mode=ParseMode.HTML)
            return
        
        db.update_deal_status(deal_id, 'paid')
        
        # Уведомляем продавца
        seller = db.get_user(deal['seller_id'])
        if seller:
            try:
                await context.bot.send_message(
                    deal['seller_id'],
                    f"{EMOJI['balance']} <b>Новая оплата!</b>\n\n"
                    f"Сделка: #{deal_id}\n"
                    f"Сумма: {deal['amount']} {deal['currency']}\n\n"
                    f"Отправьте товар покупателю и подтвердите отправку:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{EMOJI['check']} Подтвердить отправку", callback_data=f'seller_sent_{deal_id}')]
                    ])
                )
            except:
                pass
        
        await query.message.edit_caption(
            caption=f"{EMOJI['check']} <b>Оплата подтверждена!</b>\n\n"
                   f"Сделка #{deal_id}\n\n"
                   f"<i>Ожидайте получения товара от продавца...</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['shop']} В магазин", callback_data='browse_items')]])
        )
    
    # Продавец подтвердил отправку
    elif data.startswith('seller_sent_'):
        deal_id = data.replace('seller_sent_', '')
        deal = db.get_deal(deal_id)
        
        if not deal:
            await query.message.edit_caption(f"{EMOJI['cross']} <b>Сделка не найдена</b>", parse_mode=ParseMode.HTML)
            return
        
        db.update_deal_status(deal_id, 'shipped')
        
        # Уведомляем покупателя
        try:
            await context.bot.send_message(
                deal['buyer_id'],
                f"{EMOJI['deals']} <b>Товар отправлен!</b>\n\n"
                f"Сделка: #{deal_id}\n\n"
                f"Продавец подтвердил отправку товара.\n"
                f"После получения нажмите кнопку подтверждения:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['check']} Подтвердить получение", callback_data=f'buyer_received_{deal_id}')]
                ])
            )
        except:
            pass
        
        await query.message.edit_caption(
            caption=f"{EMOJI['check']} <b>Отправка подтверждена!</b>\n\n"
                   f"Ожидайте подтверждения от покупателя.",
            parse_mode=ParseMode.HTML
        )
    
    # Покупатель подтвердил получение
    elif data.startswith('buyer_received_'):
        deal_id = data.replace('buyer_received_', '')
        deal = db.get_deal(deal_id)
        
        if not deal:
            await query.message.edit_caption(f"{EMOJI['cross']} <b>Сделка не найдена</b>", parse_mode=ParseMode.HTML)
            return
        
        db.update_deal_status(deal_id, 'completed')
        
        # Начисляем средства продавцу
        seller = db.get_user(deal['seller_id'])
        if seller:
            # Обновляем баланс продавца
            conn = db.get_connection()
            cursor = conn.cursor()
            if deal['currency'] == 'TON':
                cursor.execute('UPDATE users SET balance_ton = balance_ton + ? WHERE user_id = ?', 
                              (deal['amount'], deal['seller_id']))
            elif deal['currency'] == 'RUB':
                cursor.execute('UPDATE users SET balance_rub = balance_rub + ? WHERE user_id = ?', 
                              (deal['amount'], deal['seller_id']))
            conn.commit()
            conn.close()
        
        # Уведомляем продавца
        try:
            await context.bot.send_message(
                deal['seller_id'],
                f"{EMOJI['check']} <b>Сделка завершена!</b>\n\n"
                f"Сделка: #{deal_id}\n"
                f"Сумма: {deal['amount']} {deal['currency']}\n\n"
                f"Средства зачислены на ваш баланс!",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        
        await query.message.edit_caption(
            caption=f"{EMOJI['check']} <b>Сделка успешно завершена!</b>\n\n"
                   f"Спасибо, что воспользовались нашим сервисом!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['shop']} В магазин", callback_data='browse_items')]])
        )
    
    # Профиль
    elif data == 'profile':
        user = db.get_user(user_id)
        if not user:
            return
        
        items_count = len(db.get_user_items(user_id))
        deals = db.get_user_deals(user_id)
        
        text = f"""
{EMOJI['profile']} <b>Профиль</b>

<b>ID:</b> <code>{user_id}</code>
<b>Username:</b> @{user['username']}
{EMOJI['verified'] if user['is_verified'] else EMOJI['unverified']} <b>Верификация:</b> {'Да' if user['is_verified'] else 'Нет'}

<b>📊 Статистика:</b>
{EMOJI['deals']} Сделок: {user['successful_deals']}
{EMOJI['sell']} Товаров: {items_count}
{EMOJI['balance']} Объём продаж: {sum(d['amount'] for d in deals if d['seller_id'] == user_id and d['status'] == 'completed')}

<b>💰 Баланс:</b>
{EMOJI['ton']} TON: {user['balance_ton']}
{EMOJI['rub']} RUB: {user['balance_rub']}
{EMOJI['usd']} USD: {user['balance_usd']}
"""
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['deals']} Мои товары", callback_data='my_items'),
             InlineKeyboardButton(f"{EMOJI['balance']} Вывести средства", callback_data='withdraw_menu')],
            [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='menu')],
        ]
        
        await query.message.edit_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # Мои товары
    elif data == 'my_items':
        items = db.get_user_items(user_id)
        
        if not items:
            await query.message.edit_caption(
                caption=f"{EMOJI['sell']} <b>У вас нет активных товаров</b>\n\n"
                       f"Нажмите «Выставить товар», чтобы начать продажу!",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['sell']} Выставить товар", callback_data='sell_menu')]])
            )
            return
        
        text = f"{EMOJI['sell']} <b>Ваши товары:</b>\n\n"
        keyboard = []
        
        for item in items:
            text += f"• <b>{item['title'][:30]}</b> - {item['price']} {item['currency']}\n"
            keyboard.append([InlineKeyboardButton(f"❌ {item['title'][:25]}", callback_data=f'delete_item_{item["item_id"]}')])
        
        keyboard.append([InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='profile')])
        
        await query.message.edit_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # Удаление товара
    elif data.startswith('delete_item_'):
        item_id = data.replace('delete_item_', '')
        if db.delete_item(item_id, user_id):
            await query.answer("✅ Товар удалён!", show_alert=True)
            await query.message.edit_caption(
                caption=f"{EMOJI['check']} <b>Товар удалён</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='my_items')]])
            )
        else:
            await query.answer("❌ Ошибка удаления!", show_alert=True)
    
    # Мои сделки
    elif data == 'my_deals':
        deals = db.get_user_deals(user_id)
        
        if not deals:
            await query.message.edit_caption(
                caption=f"{EMOJI['deals']} <b>У вас нет сделок</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='menu')]])
            )
            return
        
        status_icons = {
            'pending': '🟡 Ожидает оплаты',
            'paid': '🟢 Оплачено',
            'shipped': '📦 Отправлено',
            'completed': '✅ Завершена',
            'cancelled': '❌ Отменена',
        }
        
        text = f"{EMOJI['deals']} <b>Мои сделки:</b>\n\n"
        for deal in deals[:10]:
            role = "Продавец" if deal['seller_id'] == user_id else "Покупатель"
            status = status_icons.get(deal['status'], deal['status'])
            text += f"#{deal['deal_id']} | {deal['amount']} {deal['currency']} | {role} | {status}\n"
        
        keyboard = [[InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='menu')]]
        await query.message.edit_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # Админ-панель
    elif data == 'admin_panel' and db.is_admin(user_id):
        stats = db.get_stats()
        
        text = f"""
{EMOJI['admin']} <b>Административная панель</b>

{EMOJI['profile']} <b>Пользователей:</b> {stats['total_users']}
{EMOJI['sell']} <b>Активных товаров:</b> {stats['active_items']}
{EMOJI['deals']} <b>Всего сделок:</b> {stats['total_deals']}
{EMOJI['check']} <b>Завершённых:</b> {stats['completed_deals']}
{EMOJI['balance']} <b>Общий объём:</b> {stats['total_volume']} TON

<b>Выберите действие:</b>
"""
        
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats'),
             InlineKeyboardButton("👥 Пользователи", callback_data='admin_users')],
            [InlineKeyboardButton("📦 Все товары", callback_data='admin_items'),
             InlineKeyboardButton("📋 Все сделки", callback_data='admin_deals')],
            [InlineKeyboardButton("🎮 Управление играми", callback_data='admin_games'),
             InlineKeyboardButton("📢 Рассылка", callback_data='admin_broadcast')],
            [InlineKeyboardButton("💰 Управление балансом", callback_data='admin_balance'),
             InlineKeyboardButton("✅ Верификация", callback_data='admin_verify')],
            [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='menu')],
        ]
        
        await query.message.edit_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    text = update.message.text
    
    db.update_user_activity(user_id)
    
    # Процесс создания товара
    if context.user_data.get('selling', {}).get('step') == 'title':
        context.user_data['selling']['title'] = text
        context.user_data['selling']['step'] = 'description'
        
        await update.message.reply_text(
            f"{EMOJI['sell']} <b>Введите описание товара:</b>\n\n"
            f"<i>Пример: Аккаунт 50к трофеев, 15 легендарок, 50 скинов</i>\n\n"
            f"<b>Текущий товар:</b> {text}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['back']} Отмена", callback_data='sell_menu')]])
        )
        return
    
    elif context.user_data.get('selling', {}).get('step') == 'description':
        context.user_data['selling']['description'] = text
        context.user_data['selling']['step'] = 'price'
        
        await update.message.reply_text(
            f"{EMOJI['balance']} <b>Введите цену:</b>\n\n"
            f"<i>Пример: 100 TON, 5000 RUB</i>\n\n"
            f"<b>Товар:</b> {context.user_data['selling']['title']}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['back']} Отмена", callback_data='sell_menu')]])
        )
        return
    
    elif context.user_data.get('selling', {}).get('step') == 'price':
        try:
            # Парсим цену и валюту
            parts = text.split()
            price = float(parts[0])
            currency = parts[1].upper() if len(parts) > 1 else 'TON'
            
            if currency not in ['TON', 'RUB', 'USD', 'STARS']:
                currency = 'TON'
            
            context.user_data['selling']['price'] = price
            context.user_data['selling']['currency'] = currency
            context.user_data['selling']['step'] = 'screenshots'
            context.user_data['selling']['screenshots'] = []
            
            await update.message.reply_text(
                f"{EMOJI['shop']} <b>Отправьте скриншоты аккаунта:</b>\n\n"
                f"Вы можете отправить до 5 фото\n"
                f"После отправки всех фото нажмите «Готово»\n\n"
                f"<b>Товар:</b> {context.user_data['selling']['title']}\n"
                f"<b>Цена:</b> {price} {currency}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['check']} Готово", callback_data='finish_item_creation')],
                    [InlineKeyboardButton(f"{EMOJI['back']} Отмена", callback_data='sell_menu')]
                ])
            )
        except ValueError:
            await update.message.reply_text(
                f"{EMOJI['cross']} <b>Неверный формат!</b>\n\n"
                f"Введите цену и валюту:\n"
                f"<code>100 TON</code>\n"
                f"<code>5000 RUB</code>",
                parse_mode=ParseMode.HTML
            )
        return
    
    # Обработка скриншотов
    if context.user_data.get('selling', {}).get('step') == 'screenshots':
        if update.message.photo:
            photo = update.message.photo[-1]
            file = await photo.get_file()
            file_path = f"temp_{user_id}_{len(context.user_data['selling']['screenshots'])}.jpg"
            await file.download_to_drive(file_path)
            
            # Здесь можно загрузить на сервер, но пока сохраняем локально
            context.user_data['selling']['screenshots'].append(file_path)
            
            remaining = 5 - len(context.user_data['selling']['screenshots'])
            await update.message.reply_text(
                f"{EMOJI['check']} <b>Скриншот добавлен!</b>\n"
                f"Осталось: {remaining}\n\n"
                f"Отправьте ещё фото или нажмите «Готово»",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                f"{EMOJI['warning']} <b>Отправьте фото!</b>",
                parse_mode=ParseMode.HTML
            )
        return
    
    # Поиск
    elif context.user_data.get('awaiting_search'):
        query = text
        game = context.user_data.get('search_game')
        
        items = db.search_items(query, game)
        
        if not items:
            await update.message.reply_text(
                f"{EMOJI['cross']} <b>Ничего не найдено</b>\n\nПопробуйте изменить запрос.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='search_menu')]])
            )
            return
        
        text, keyboard = get_items_keyboard(items, 0, 5, 'view_item_')
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        context.user_data['awaiting_search'] = False
        return

async def finish_item_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение создания товара"""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    selling = context.user_data.get('selling', {})
    
    if not selling or selling.get('step') != 'screenshots':
        await query.message.edit_caption(
            caption=f"{EMOJI['cross']} <b>Ошибка! Начните создание заново.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    # Сохраняем товар
    item_id = db.add_item(
        seller_id=user_id,
        game=selling['game'],
        title=selling['title'],
        description=selling['description'],
        price=selling['price'],
        currency=selling['currency'],
        screenshots=selling.get('screenshots', [])
    )
    
    bot_username = (await context.bot.get_me()).username
    item_link = f"https://t.me/{bot_username}?start={item_id}"
    
    text = f"""
{EMOJI['check']} <b>Товар успешно создан!</b>

{EMOJI['shop']} <b>Название:</b> {selling['title']}
{EMOJI['balance']} <b>Цена:</b> {selling['price']} {selling['currency']}
{EMOJI['deals']} <b>ID товара:</b> <code>{item_id}</code>

<b>🔗 Ссылка на товар:</b>
<code>{item_link}</code>

{EMOJI['warning']} <i>Отправьте эту ссылку покупателю для покупки!</i>
"""
    
    await query.message.edit_caption(
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{EMOJI['shop']} В магазин", callback_data='browse_items')],
            [InlineKeyboardButton(f"{EMOJI['profile']} Мои товары", callback_data='my_items')]
        ])
    )
    
    # Очищаем состояние
    context.user_data.pop('selling', None)

# ========== АДМИН-КОМАНДЫ ==========
@admin_only
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Блокировка пользователя: /ban <user_id>"""
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id> [reason]", parse_mode=ParseMode.HTML)
        return
    
    try:
        target_id = int(context.args[0])
        reason = ' '.join(context.args[1:]) if len(context.args) > 1 else 'Не указана'
        
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_blocked = 1 WHERE user_id = ?', (target_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"{EMOJI['cross']} <b>Пользователь заблокирован!</b>\n"
            f"ID: {target_id}\n"
            f"Причина: {reason}",
            parse_mode=ParseMode.HTML
        )
    except ValueError:
        await update.message.reply_text(f"{EMOJI['cross']} <b>Неверный ID!</b>", parse_mode=ParseMode.HTML)

@admin_only
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Разблокировка: /unban <user_id>"""
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>", parse_mode=ParseMode.HTML)
        return
    
    try:
        target_id = int(context.args[0])
        
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_blocked = 0 WHERE user_id = ?', (target_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"{EMOJI['check']} <b>Пользователь разблокирован!</b>\nID: {target_id}",
            parse_mode=ParseMode.HTML
        )
    except ValueError:
        await update.message.reply_text(f"{EMOJI['cross']} <b>Неверный ID!</b>", parse_mode=ParseMode.HTML)

@admin_only
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика: /stats"""
    stats = db.get_stats()
    
    text = f"""
{EMOJI['admin']} <b>Статистика бота</b>

{EMOJI['profile']} <b>Пользователей:</b> {stats['total_users']}
{EMOJI['sell']} <b>Активных товаров:</b> {stats['active_items']}
{EMOJI['deals']} <b>Всего сделок:</b> {stats['total_deals']}
{EMOJI['check']} <b>Завершённых:</b> {stats['completed_deals']}
{EMOJI['balance']} <b>Общий объём:</b> {stats['total_volume']} TON
"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

@admin_only
async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список пользователей: /users"""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, is_admin, is_verified FROM users LIMIT 20')
    rows = cursor.fetchall()
    conn.close()
    
    text = f"{EMOJI['profile']} <b>Список пользователей:</b>\n\n"
    for row in rows:
        admin_mark = "👑 " if row[2] else ""
        verified_mark = "✅" if row[3] else "❌"
        text += f"{verified_mark} {admin_mark}<code>{row[0]}</code> @{row[1] or '?'}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

@admin_only
async def cmd_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить админа: /add_admin <user_id>"""
    if not context.args:
        await update.message.reply_text("Usage: /add_admin <user_id>", parse_mode=ParseMode.HTML)
        return
    
    try:
        target_id = int(context.args[0])
        
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (target_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"{EMOJI['check']} <b>Администратор добавлен!</b>\nID: {target_id}",
            parse_mode=ParseMode.HTML
        )
    except ValueError:
        await update.message.reply_text(f"{EMOJI['cross']} <b>Неверный ID!</b>", parse_mode=ParseMode.HTML)

# ========== ЗАПУСК ==========
def main():
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ban", cmd_ban))
    application.add_handler(CommandHandler("unban", cmd_unban))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("users", cmd_users))
    application.add_handler(CommandHandler("add_admin", cmd_add_admin))
    
    # Обработчики кнопок
    application.add_handler(CallbackQueryHandler(button_handler, pattern='^(?!finish_item_creation).*$'))
    application.add_handler(CallbackQueryHandler(finish_item_creation, pattern='^finish_item_creation$'))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(MessageHandler(filters.PHOTO, message_handler))
    
    # Запуск
    print("🤖 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
