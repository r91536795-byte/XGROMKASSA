import os
import sqlite3
import time
import threading
from datetime import datetime
from flask import Flask, request
import telebot
from telebot import types

TOKEN = os.environ.get("TOKEN")
MAIN_ADMIN = int(os.environ.get("MAIN_ADMIN", 8763658506))
SUPPORT = "@GromsupBot"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
bot_active = True
temp_data = {}
payment_timers = {}

def init_db():
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, join_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (chat_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, account_id TEXT, photo_id TEXT, status TEXT, date TEXT, time TEXT)''')
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

def get_all_users():
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
    print(f"QR сохранен: {file_id}")

def get_last_qr():
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('SELECT file_id FROM qr_codes ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    if row:
        print(f"QR найден: {row[0][:50]}...")
        return row[0]
    else:
        print("QR не найден в базе")
        return None

def get_stats():
    conn = sqlite3.connect('xgromkassa.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM deposits WHERE status="pending"')
    pending = c.fetchone()[0]
    c.execute('SELECT SUM(amount) FROM deposits WHERE status="approved"')
    total = c.fetchone()[0] or 0
    conn.close()
    return {'users': users, 'pending': pending, 'total': total}

init_db()

def cancel_payment(user_id):
    if user_id in temp_data:
        del temp_data[user_id]
        try:
            bot.send_message(user_id, "⏰ ВРЕМЯ ОПЛАТЫ ИСТЕКЛО!\n\nЗаявка отменена.")
        except:
            pass

def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Пополнение", "💸 Вывод")
    markup.add("👨‍💻 Поддержка")
    if user_id in get_admins():
        markup.add("⚙️ Админ")
    return markup

def admin_menu():
    global bot_active
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📋 Заявки", "📊 Статистика")
    markup.add("🖼 Изменить QR", "➕ Админ")
    markup.add("📢 Рассылка")
    status_btn = "🔴 ВЫКЛ" if bot_active else "🟢 ВКЛ"
    markup.add(status_btn)
    markup.add("🔙 Главное меню")
    return markup

def back_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔙 Назад")
    return markup

@bot.message_handler(commands=['start'])
def start(msg):
    add_user(msg.chat.id)
    bot.send_message(msg.chat.id, f"🚀 Добро пожаловать в XGROMKASSA, {msg.from_user.first_name}!", reply_markup=main_menu(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def back_to_main(msg):
    start(msg)

@bot.message_handler(func=lambda m: m.text == "👨‍💻 Поддержка")
def support(msg):
    bot.send_message(msg.chat.id, f"📞 Поддержка: {SUPPORT}")

@bot.message_handler(func=lambda m: m.text == "🔙 Главное меню")
def back(msg):
    start(msg)

@bot.message_handler(func=lambda m: m.text == "⚙️ Админ" and m.from_user.id in get_admins())
def admin_panel(msg):
    bot.send_message(msg.chat.id, "⚙️ Админ панель", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "➕ Админ" and m.from_user.id in get_admins())
def add_admin_btn(msg):
    bot.send_message(msg.chat.id, "👤 Введите ID:")
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(msg):
    try:
        add_admin(int(msg.text))
        bot.send_message(msg.chat.id, "✅ Админ добавлен!", reply_markup=admin_menu())
    except:
        bot.send_message(msg.chat.id, "❌ Ошибка!")

@bot.message_handler(func=lambda m: m.text in ["🔴 ВЫКЛ", "🟢 ВКЛ"] and m.from_user.id in get_admins())
def toggle_bot(msg):
    global bot_active
    bot_active = (msg.text == "🟢 ВКЛ")
    bot.send_message(msg.chat.id, f"{'🟢 Бот ВКЛЮЧЕН' if bot_active else '🔴 Бот ВЫКЛЮЧЕН'}", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "🖼 Изменить QR" and m.from_user.id in get_admins())
def change_qr(msg):
    bot.send_message(msg.chat.id, "🖼 Отправьте новый QR-код (фото):", reply_markup=back_menu())
    bot.register_next_step_handler(msg, save_new_qr)

def save_new_qr(msg):
    if msg.text == "🔙 Назад":
        admin_panel(msg)
        return
    if msg.photo:
        file_id = msg.photo[-1].file_id
        save_qr(file_id)
        bot.send_message(msg.chat.id, "✅ QR-код успешно сохранен!", reply_markup=admin_menu())
    else:
        bot.send_message(msg.chat.id, "❌ Отправьте фото QR-кода!", reply_markup=back_menu())
        bot.register_next_step_handler(msg, save_new_qr)

@bot.message_handler(func=lambda m: m.text == "💰 Пополнение")
def deposit(msg):
    bot.send_message(msg.chat.id, "🆔 Введите ID счета 1xBet:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, get_account_id)

def get_account_id(msg):
    if msg.text == "🔙 Назад":
        start(msg)
        return
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
    user_1xbet_id = temp_data.get(user_id, {}).get("account_id", "Не указан")
    temp_data[user_id]["amount"] = amount
    
    # Отправляем QR-код
    qr_file_id = get_last_qr()
    if qr_file_id:
        try:
            bot.send_photo(msg.chat.id, qr_file_id, caption=f"📱 ОПЛАТИТЕ {amount} сом\n⏳ 5 минут на оплату")
        except Exception as e:
            print(f"Ошибка отправки QR: {e}")
            bot.send_message(msg.chat.id, "❌ Ошибка отправки QR-кода")
    else:
        bot.send_message(msg.chat.id, "📱 QR-код временно отсутствует. Добавьте его через админ панель.")
    
    text = f"""📎 **Прикрепите скриншот чека**

━━━━━━━━━━━━━━━━━━━━━

🆔 **Аккаунт ID:** `{user_1xbet_id}`
💰 **Сумма:** {amount} сом ✅

━━━━━━━━━━━━━━━━━━━━━

⚠️ **Оплатите и отправьте скриншот чека в течение 5 минут!**
Чек должен быть в формате картинки"""
    
    bot.send_message(msg.chat.id, text, parse_mode='Markdown', reply_markup=back_menu())
    
    timer = threading.Timer(300, cancel_payment, args=[user_id])
    payment_timers[user_id] = timer
    timer.start()
    
    bot.register_next_step_handler(msg, get_check_photo)

def get_check_photo(msg):
    if msg.text == "🔙 Назад":
        if msg.chat.id in payment_timers:
            payment_timers[msg.chat.id].cancel()
        start(msg)
        return
    if not msg.photo:
        bot.send_message(msg.chat.id, "❌ Отправьте фото чека!", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_check_photo)
        return
    
    user_id = msg.chat.id
    if user_id in payment_timers:
        payment_timers[user_id].cancel()
    
    account_id = temp_data[user_id].get("account_id")
    amount = temp_data[user_id].get("amount")
    photo_id = msg.photo[-1].file_id
    
    if not account_id or not amount:
        bot.send_message(msg.chat.id, "❌ Ошибка! Начните заново.")
        start(msg)
        return
    
    dep_id = add_deposit(user_id, amount, account_id, photo_id)
    
    admins = get_admins()
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
    )
    
    for admin in admins:
        try:
            bot.send_photo(admin, photo_id, 
                caption=f"🆕 ЗАЯВКА #{dep_id}\n👤 {user_id}\n💰 {amount} сом\n🆔 {account_id}",
                reply_markup=markup)
        except:
            pass
    
    bot.send_message(msg.chat.id, 
        f"✅ ЗАЯВКА ПРИНЯТА!\n\n🆔 ID: {account_id}\n💰 СУММА: {amount} сом\n\n⏳ ОЖИДАЙТЕ ОБРАБОТКИ ОПЕРАТОРОМ...", 
        reply_markup=main_menu(user_id))
    
    del temp_data[user_id]

@bot.message_handler(func=lambda m: m.text == "💸 Вывод")
def withdraw(msg):
    text = f"💸 ДЛЯ ВЫВОДА СРЕДСТВ ОБРАТИТЕСЬ К ОПЕРАТОРУ:\n\n👨‍💻 {SUPPORT}\n\n💰 Мин. сумма: 150 сом\n💰 Макс. сумма: 50 000 сом"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📞 ОПЕРАТОР", url="https://t.me/ggKassaHelpbot"))
    bot.send_message(msg.chat.id, text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📋 Заявки" and m.from_user.id in get_admins())
def view_requests(msg):
    deposits = get_pending_deposits()
    if not deposits:
        bot.send_message(msg.chat.id, "📭 Нет заявок")
        return
    for dep in deposits:
        dep_id, user_id, amount, account_id, photo_id, date, time = dep
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
        )
        try:
            bot.send_photo(msg.chat.id, photo_id, 
                caption=f"🆕 ЗАЯВКА #{dep_id}\n👤 {user_id}\n💰 {amount} сом\n🆔 {account_id}",
                reply_markup=markup)
        except:
            bot.send_message(msg.chat.id, 
                f"🆕 ЗАЯВКА #{dep_id}\n👤 {user_id}\n💰 {amount} сом\n🆔 {account_id}", 
                reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and m.from_user.id in get_admins())
def stats(msg):
    s = get_stats()
    bot.send_message(msg.chat.id, 
        f"📊 СТАТИСТИКА\n\n👥 Пользователей: {s['users']}\n⏳ Заявок: {s['pending']}\n💰 Всего: {s['total']} сом")

@bot.message_handler(func=lambda m: m.text == "📢 Рассылка" and m.from_user.id in get_admins())
def broadcast_start(msg):
    bot.send_message(msg.chat.id, "📝 Отправьте сообщение для рассылки:")
    bot.register_next_step_handler(msg, broadcast_send)

def broadcast_send(msg):
    users = get_all_users()
    success = 0
    for user_id in users:
        try:
            bot.send_message(user_id, msg.text)
            success += 1
        except:
            pass
        time.sleep(0.05)
    bot.send_message(msg.chat.id, f"✅ Рассылка: {success}/{len(users)}", reply_markup=admin_menu())

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
            bot.answer_callback_query(call.id, "✅ Одобрено!")
            try:
                bot.send_message(user_id, 
                    f"✅ ВАША ЗАЯВКА НА ПОПОЛНЕНИЕ ОДОБРЕНА!\n\n"
                    f"💰 Сумма: {amount} сом\n"
                    f"🆔 ID: {account_id}\n\n"
                    f"Средства успешно зачислены на ваш игровой счет!")
            except:
                pass
            bot.edit_message_text(f"✅ ЗАЯВКА #{dep_id} ОДОБРЕНА", call.message.chat.id, call.message.message_id)
    
    elif data.startswith('reject_'):
        dep_id = int(data.split('_')[1])
        conn = sqlite3.connect('xgromkassa.db')
        c = conn.cursor()
        c.execute('SELECT user_id, amount FROM deposits WHERE id = ?', (dep_id,))
        result = c.fetchone()
        conn.close()
        if result:
            user_id, amount = result
            update_deposit_status(dep_id, "rejected")
            bot.answer_callback_query(call.id, "❌ Отклонено!")
            try:
                bot.send_message(user_id, f"❌ ЗАЯВКА {amount} сом ОТКЛОНЕНА!\n📞 {SUPPORT}")
            except:
                pass
            bot.edit_message_text(f"❌ ЗАЯВКА #{dep_id} ОТКЛОНЕНА", call.message.chat.id, call.message.message_id)

def run_bot():
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)

threading.Thread(target=run_bot, daemon=True).start()

@app.route('/')
def home():
    return "XGROMKASSA Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
