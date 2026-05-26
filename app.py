import os
import sqlite3
import time
import threading
from datetime import datetime
from flask import Flask, request
import telebot
from telebot import types

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get("TOKEN")
MAIN_ADMIN = 8763658506
SUPPORT = "@ggKassaHelpbot"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
bot_active = True
temp_data = {}
payment_timers = {}

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, join_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (chat_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, account_id TEXT, photo_id TEXT, status TEXT, date TEXT, time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdraw_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, user_1xbet_id TEXT, withdraw_code TEXT, qr_photo TEXT, status TEXT, date TEXT, time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS qr_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, date TEXT)''')
    c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (MAIN_ADMIN,))
    conn.commit()
    conn.close()

def add_user(chat_id):
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (chat_id, join_date) VALUES (?, ?)', (chat_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
    conn.commit()
    conn.close()

def get_all_users_list():
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('SELECT chat_id FROM users')
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_admins():
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('SELECT chat_id FROM admins')
    admins = [row[0] for row in c.fetchall()]
    conn.close()
    return admins

def add_admin(chat_id):
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (chat_id,))
    conn.commit()
    conn.close()

def add_deposit(user_id, amount, account_id, photo_id):
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    now = datetime.now()
    c.execute('INSERT INTO deposits (user_id, amount, account_id, photo_id, status, date, time) VALUES (?, ?, ?, ?, ?, ?, ?)',
              (user_id, amount, account_id, photo_id, 'pending', now.strftime("%d.%m.%Y"), now.strftime("%H:%M:%S")))
    dep_id = c.lastrowid
    conn.commit()
    conn.close()
    return dep_id

def update_deposit_status(dep_id, status):
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('UPDATE deposits SET status = ? WHERE id = ?', (status, dep_id))
    conn.commit()
    conn.close()

def get_pending_deposits():
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('SELECT id, user_id, amount, account_id, photo_id, date, time FROM deposits WHERE status = "pending"')
    rows = c.fetchall()
    conn.close()
    return rows

def save_qr(file_id):
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('INSERT INTO qr_codes (file_id, date) VALUES (?, ?)', (file_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
    conn.commit()
    conn.close()

def get_last_qr():
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('SELECT file_id FROM qr_codes ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def add_withdraw_request(user_id, user_1xbet_id, withdraw_code, qr_photo):
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    now = datetime.now()
    c.execute('INSERT INTO withdraw_requests (user_id, user_1xbet_id, withdraw_code, qr_photo, status, date, time) VALUES (?, ?, ?, ?, ?, ?, ?)',
              (user_id, user_1xbet_id, withdraw_code, qr_photo, 'pending', now.strftime("%d.%m.%Y"), now.strftime("%H:%M:%S")))
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    return req_id

def update_withdraw_status(req_id, status):
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('UPDATE withdraw_requests SET status = ? WHERE id = ?', (status, req_id))
    conn.commit()
    conn.close()

def get_pending_withdraws():
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('SELECT id, user_id, user_1xbet_id, withdraw_code, qr_photo, date, time FROM withdraw_requests WHERE status = "pending"')
    rows = c.fetchall()
    conn.close()
    return rows

def get_stats():
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM deposits WHERE status="pending"')
    pending_dep = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM withdraw_requests WHERE status="pending"')
    pending_wd = c.fetchone()[0]
    c.execute('SELECT SUM(amount) FROM deposits WHERE status="approved"')
    total = c.fetchone()[0] or 0
    conn.close()
    return {'users': users, 'pending_dep': pending_dep, 'pending_wd': pending_wd, 'total': total}

init_db()

def cancel_payment(user_id):
    if user_id in temp_data:
        del temp_data[user_id]
        try:
            bot.send_message(user_id, 
                f"⏰ **ВРЕМЯ ОПЛАТЫ ИСТЕКЛО!**\n\nЗаявка на пополнение отменена.\n💰 Для нового пополнения нажмите кнопку снова.",
                parse_mode='Markdown',
                reply_markup=main_menu(user_id))
        except:
            pass

# ========== МЕНЮ ==========
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Пополнение", "💸 Вывод")
    markup.add("👨‍💻 Поддержка")
    if user_id in get_admins():
        markup.add("⚙️ Админ панель")
    return markup

def admin_menu():
    global bot_active
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📋 Заявки", "💸 Заявки на вывод")
    markup.add("📊 Статистика", "🖼 Изменить QR")
    markup.add("➕ Добавить админа", "📢 Рассылка")
    status_btn = "🔴 ВЫКЛЮЧИТЬ БОТА" if bot_active else "🟢 ВКЛЮЧИТЬ БОТА"
    markup.add(status_btn)
    markup.add("🔙 Главное меню")
    return markup

def back_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔙 Назад")
    return markup

# ========== КОМАНДЫ ==========
@bot.message_handler(commands=['start'])
def start(msg):
    add_user(msg.chat.id)
    bot.send_message(msg.chat.id, 
        f"✨ Добро пожаловать в **XGROMKASSA**, {msg.from_user.first_name}! ✨\n\n"
        f"🏦 **XGROMKASSA** - ваш надежный финансовый помощник\n\n"
        f"⚡️ **Быстрые операции:**\n• 💰 Мгновенное пополнение счета\n• 💸 Надежный вывод средств\n\n"
        f"👨‍💻 **Поддержка:** {SUPPORT}\n\n"
        f"🛡 Ваши транзакции защищены\n\n"
        f"🚀 **Начните управлять своими финансами с нами уже сегодня!**\n\n👇 *Выберите действие в меню ниже* 👇", 
        parse_mode='Markdown',
        reply_markup=main_menu(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def back_to_main(msg):
    start(msg)

@bot.message_handler(func=lambda m: not bot_active and m.from_user.id not in get_admins())
def bot_disabled(msg):
    bot.send_message(msg.chat.id, "🔴 Бот временно недоступен. Зайдите позже.")

@bot.message_handler(func=lambda m: m.text == "👨‍💻 Поддержка")
def support(msg):
    if not bot_active and msg.from_user.id not in get_admins():
        bot.send_message(msg.chat.id, "🔴 Бот недоступен.")
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📞 НАПИСАТЬ", url="https://t.me/ggKassaHelpbot"))
    bot.send_message(msg.chat.id, 
        f"📞 **СЛУЖБА ПОДДЕРЖКИ XGROMKASSA**\n\n👨‍💻 **ОПЕРАТОР:** {SUPPORT}\n\n⏰ **РЕЖИМ РАБОТЫ:** КРУГЛОСУТОЧНО\n\n✅ **ОТВЕТИМ В ТЕЧЕНИЕ 15 МИНУТ!**",
        parse_mode='Markdown', reply_markup=markup)

# ========== ПОПОЛНЕНИЕ ==========
@bot.message_handler(func=lambda m: m.text == "💰 Пополнение")
def deposit(msg):
    if not bot_active and msg.from_user.id not in get_admins():
        bot.send_message(msg.chat.id, "🔴 Пополнение временно недоступно.")
        return
    bot.send_message(msg.chat.id, "🆔 Введите ID счета для пополнения:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, get_account_id)

def get_account_id(msg):
    if msg.text == "🔙 Назад":
        start(msg)
        return
    if msg.chat.id in payment_timers:
        payment_timers[msg.chat.id].cancel()
    temp_data[msg.chat.id] = {"account_id": msg.text}
    bot.send_message(msg.chat.id, "💰 Введите сумму (от 50 до 100 000 сом):", reply_markup=back_menu())
    bot.register_next_step_handler(msg, get_amount)

def get_amount(msg):
    if msg.text == "🔙 Назад":
        start(msg)
        return
    if not msg.text.isdigit():
        bot.send_message(msg.chat.id, "❌ Введите число!", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_amount)
        return
    amount = int(msg.text)
    if amount < 50 or amount > 100000:
        bot.send_message(msg.chat.id, "❌ Сумма от 50 до 100 000 сом!", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_amount)
        return
    user_id = msg.chat.id
    temp_data[user_id]["amount"] = amount
    qr_file_id = get_last_qr()
    if qr_file_id:
        bot.send_photo(msg.chat.id, qr_file_id, caption=f"📱 **ОПЛАТИТЕ {amount} сом**\n\n⏳ **Время на оплату: 5 минут**\nПосле оплаты отправьте ЧЕК.\n⚠️ Если не оплатите в течение 5 минут, заявка отменится.", parse_mode='Markdown')
    else:
        bot.send_message(msg.chat.id, f"📱 QR-код временно отсутствует.\n💰 Сумма: {amount} сом\n\n⏳ **Время на оплату: 5 минут**\nСвяжитесь с поддержкой: {SUPPORT}", parse_mode='Markdown')
    bot.send_message(msg.chat.id, f"📸 **ОТПРАВЬТЕ ФОТО ЧЕКА** после оплаты.\n\n⏳ У вас есть **5 минут** на оплату!", parse_mode='Markdown', reply_markup=back_menu())
    timer = threading.Timer(300, cancel_payment, args=[user_id])
    payment_timers[user_id] = timer
    timer.start()
    bot.register_next_step_handler(msg, get_check_photo)

def get_check_photo(msg):
    if msg.text == "🔙 Назад":
        if msg.chat.id in payment_timers:
            payment_timers[msg.chat.id].cancel()
            del payment_timers[msg.chat.id]
        start(msg)
        return
    if not msg.photo:
        bot.send_message(msg.chat.id, "❌ Отправьте фото чека!", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_check_photo)
        return
    user_id = msg.chat.id
    if user_id in payment_timers:
        payment_timers[user_id].cancel()
        del payment_timers[user_id]
    account_id = temp_data.get(user_id, {}).get("account_id")
    amount = temp_data.get(user_id, {}).get("amount")
    photo_id = msg.photo[-1].file_id
    if not account_id or not amount:
        bot.send_message(msg.chat.id, "❌ Ошибка! Начните пополнение заново.")
        start(msg)
        return
    dep_id = add_deposit(user_id, amount, account_id, photo_id)
    admins = get_admins()
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"), types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}"))
    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%d.%m.%Y")
    for admin in admins:
        try:
            bot.send_photo(admin, photo_id, caption=f"🆕 **НОВАЯ ЗАЯВКА #{dep_id}**\n\n👤 Пользователь: {user_id}\n💰 Сумма: {amount} сом\n🆔 Счет: {account_id}\n📅 Дата: {date_str}\n🕐 Время: {time_str}", parse_mode='Markdown', reply_markup=markup)
        except:
            pass
    bot.send_message(msg.chat.id, f"✅ **ЗАЯВКА ОТПРАВЛЕНА!**\n\n💰 Сумма: {amount} сом\n🆔 Счет: {account_id}\n🕐 Время: {time_str}\n\n⏳ Ожидайте подтверждения администратора.", parse_mode='Markdown', reply_markup=main_menu(user_id))
    if user_id in temp_data:
        del temp_data[user_id]

# ========== ВЫВОД (ИНСТРУКЦИЯ) ==========
@bot.message_handler(func=lambda m: m.text == "💸 Вывод")
def withdraw(msg):
    if not bot_active and msg.from_user.id not in get_admins():
        bot.send_message(msg.chat.id, "🔴 Вывод временно недоступен.")
        return
    
    text = """📍 **ИНСТРУКЦИЯ ПО ВЫВОДУ СРЕДСТВ XGROMKASSA**

━━━━━━━━━━━━━━━━━━━━━

📌 **ШАГ 1:** Перейдите по адресу:
🏙 **г. Бишкек**
🏢 **Улица: XMoreDep** (работает 24/7)

━━━━━━━━━━━━━━━━━━━━━

📌 **ШАГ 2:** Назовите оператору:
• Ваш **1xBet ID**
• Сумму вывода (от 150 сом)

━━━━━━━━━━━━━━━━━━━━━

📌 **ШАГ 3:** Получите **КОД** от оператора

━━━━━━━━━━━━━━━━━━━━━

📌 **ШАГ 4:** Отправьте полученный КОД в этот бот

━━━━━━━━━━━━━━━━━━━━━

💰 **УСЛОВИЯ:**
• Мин. сумма: 150 сом
• Макс. сумма: 50 000 сом
• Комиссия: 0%

━━━━━━━━━━━━━━━━━━━━━

💻 **ОПЕРАТОР:** @ggKassaHelpbot

━━━━━━━━━━━━━━━━━━━━━

⚠️ Если возникли проблемы — свяжитесь с оператором!"""
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📞 СВЯЗАТЬСЯ С ОПЕРАТОРОМ", url="https://t.me/ggKassaHelpbot"))
    
    bot.send_message(msg.chat.id, text, parse_mode='Markdown', reply_markup=markup)

# ========== АДМИН ПАНЕЛЬ ==========
@bot.message_handler(func=lambda m: m.text == "⚙️ Админ панель" and m.from_user.id in get_admins())
def admin_panel(msg):
    bot.send_message(msg.chat.id, "⚙️ **АДМИН ПАНЕЛЬ XGROMKASSA**", parse_mode='Markdown', reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "➕ Добавить админа" and m.from_user.id in get_admins())
def add_admin_btn(msg):
    bot.send_message(msg.chat.id, "👤 Отправьте Telegram ID пользователя:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(msg):
    if msg.text == "🔙 Назад":
        admin_panel(msg)
        return
    try:
        new_admin_id = int(msg.text)
        add_admin(new_admin_id)
        bot.send_message(msg.chat.id, f"✅ Пользователь {new_admin_id} добавлен в админы!", reply_markup=admin_menu())
    except:
        bot.send_message(msg.chat.id, "❌ Ошибка! Отправьте числовой ID.", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text in ["🔴 ВЫКЛЮЧИТЬ БОТА", "🟢 ВКЛЮЧИТЬ БОТА"] and m.from_user.id in get_admins())
def toggle_bot(msg):
    global bot_active
    if msg.text == "🔴 ВЫКЛЮЧИТЬ БОТА":
        bot_active = False
        bot.send_message(msg.chat.id, "🔴 Бот ВЫКЛЮЧЕН. Пользователи не смогут им пользоваться.", reply_markup=admin_menu())
    else:
        bot_active = True
        bot.send_message(msg.chat.id, "🟢 Бот ВКЛЮЧЕН. Все функции доступны.", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📋 Заявки" and m.from_user.id in get_admins())
def view_requests(msg):
    deposits = get_pending_deposits()
    if not deposits:
        bot.send_message(msg.chat.id, "📭 Нет новых заявок", reply_markup=admin_menu())
        return
    for dep in deposits:
        dep_id, user_id, amount, account_id, photo_id, date, time = dep
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"), types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}"))
        text = f"🆕 **ЗАЯВКА #{dep_id}**\n👤 {user_id}\n💰 {amount} сом\n🆔 {account_id}\n📅 {date}\n🕐 {time}"
        try:
            bot.send_photo(msg.chat.id, photo_id, caption=text, parse_mode='Markdown', reply_markup=markup)
        except:
            bot.send_message(msg.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "💸 Заявки на вывод" and m.from_user.id in get_admins())
def view_withdraw_requests(msg):
    withdraws = get_pending_withdraws()
    if not withdraws:
        bot.send_message(msg.chat.id, "📭 Нет новых заявок на вывод", reply_markup=admin_menu())
        return
    for wd in withdraws:
        req_id, user_id, user_1xbet_id, withdraw_code, qr_photo, date, time = wd
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_withdraw_{req_id}"), types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_withdraw_{req_id}"))
        text = f"💸 **ЗАЯВКА НА ВЫВОД #{req_id}**\n👤 {user_id}\n🆔 1xBet ID: {user_1xbet_id}\n🔢 Код: {withdraw_code}\n📅 {date}\n🕐 {time}"
        try:
            bot.send_photo(msg.chat.id, qr_photo, caption=text, parse_mode='Markdown', reply_markup=markup)
        except:
            bot.send_message(msg.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and m.from_user.id in get_admins())
def stats(msg):
    stats_data = get_stats()
    bot.send_message(msg.chat.id, 
        f"📊 **СТАТИСТИКА XGROMKASSA**\n\n"
        f"👥 Пользователей: {stats_data['users']}\n"
        f"⏳ Заявок на пополнение: {stats_data['pending_dep']}\n"
        f"⏳ Заявок на вывод: {stats_data['pending_wd']}\n"
        f"💰 Всего пополнений: {stats_data['total']} сом\n"
        f"🟢 Бот: {'ВКЛЮЧЕН' if bot_active else 'ВЫКЛЮЧЕН'}", 
        parse_mode='Markdown', reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🖼 Изменить QR" and m.from_user.id in get_admins())
def change_qr(msg):
    bot.send_message(msg.chat.id, "🖼 Отправьте НОВЫЙ QR-код для оплаты (фото):", reply_markup=back_menu())
    bot.register_next_step_handler(msg, save_new_qr)

def save_new_qr(msg):
    if msg.text == "🔙 Назад":
        admin_panel(msg)
        return
    if msg.photo:
        save_qr(msg.photo[-1].file_id)
        bot.send_message(msg.chat.id, "✅ QR-код успешно обновлен!", reply_markup=admin_menu())
    else:
        bot.send_message(msg.chat.id, "❌ Отправьте фото QR-кода!", reply_markup=back_menu())
        bot.register_next_step_handler(msg, save_new_qr)

@bot.message_handler(func=lambda m: m.text == "📢 Рассылка" and m.from_user.id in get_admins())
def broadcast_start(msg):
    bot.send_message(msg.chat.id, "📝 Отправьте сообщение для рассылки ВСЕМ пользователям:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, broadcast_send)

def broadcast_send(msg):
    if msg.text == "🔙 Назад":
        admin_panel(msg)
        return
    users = get_all_users_list()
    success = 0
    bot.send_message(msg.chat.id, f"⏳ Начинаю рассылку {len(users)} пользователям...")
    for user_id in users:
        try:
            if msg.photo:
                bot.send_photo(user_id, msg.photo[-1].file_id, caption=msg.caption)
            elif msg.text:
                bot.send_message(user_id, msg.text)
            else:
                bot.copy_message(user_id, msg.chat.id, msg.message_id)
            success += 1
        except:
            pass
        time.sleep(0.05)
    bot.send_message(msg.chat.id, f"✅ **РАССЫЛКА ЗАВЕРШЕНА!**\n\n📨 Доставлено: {success}/{len(users)}", parse_mode='Markdown', reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🔙 Главное меню")
def back(msg):
    start(msg)

# ========== ОБРАБОТКА ЗАЯВОК ==========
@bot.callback_query_handler(func=lambda call: True)
def handle_call(call):
    admin_id = call.from_user.id
    if admin_id not in get_admins():
        bot.answer_callback_query(call.id, "❌ Нет прав!")
        return
    
    data = call.data
    
    if data.startswith('approve_'):
        dep_id = int(data.split('_')[1])
        conn = sqlite3.connect('xgromkassa.db')
        c = conn.cursor()
        c.execute('SELECT user_id, amount, account_id FROM deposits WHERE id = ?', (dep_id,))
        result = c.fetchone()
        conn.close()
        if result:
            user_id, amount, account_id = result
            update_deposit_status(dep_id, "approved")
            bo
