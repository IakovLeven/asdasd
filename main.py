import datetime
import sqlite3
from datetime import date

import telebot
from telebot import types
import requests

TOKEN = '6931853039:AAECuwckDNtwhqjaNp07TGh_gR36w57dDdw'
bot = telebot.TeleBot(TOKEN)
WRONG_VALUE_MESSAGE = "Вы ввели некорректное число."
RETRY_MESSAGE = "Ошибка. Попробуйте еще раз"
DB_NAME = "pythonsqlite.db"

GIPHY_API_KEY = 'tvtco2T1PPDenWYcrnR2E61IAmfRmMKT'

# Создаем соединение с бд.
def create_connection(db_file):
    try:
        return sqlite3.connect(db_file)
    except:
        return None


# Отправляем приветственное сообщение и ждем ввода следующей команды.
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup()
    btn_expenses = types.InlineKeyboardButton('Ввод расходов', callback_data='start_expenses')
    btn_budget = types.InlineKeyboardButton('Планирование бюджета', callback_data='start_budget')
    btn_advice = types.InlineKeyboardButton('GIF про финансы', callback_data='start_getgif')
    btn_analysis = types.InlineKeyboardButton('Анализ расходов', callback_data='start_analysis')

    markup.add(btn_expenses, btn_budget, btn_advice, btn_analysis, row_width=2)

    bot.send_message(message.chat.id, "Выберите команду:", reply_markup=markup)


# По пришедшей команде опряделяем что делать дальше.
@bot.callback_query_handler(func=lambda call: True)
def general_handler(call):
    if "budget_" in call.data:
        handle_budget_query(call)
    elif "start_" in call.data:
        query_handler(call)
    elif "analysis_" in call.data:
        analysis_query(call)
    elif call.data == "escape":
        send_welcome(call.message)

# Определяем, что делать после ввода стартовой команды.
def query_handler(call):
    if call.data == 'start_expenses':
        expenses(call.message)
    elif call.data == 'start_budget':
        budget(call.message)
    elif call.data == 'start_analysis':
        analysis(call.message)
    elif call.data == 'start_getgif':
        send_gif(call.message)


# Обрабатываем команду /expenses.
@bot.message_handler(commands=['expenses'])
def expenses(message):
    msg = bot.reply_to(message, "Введите сумму расходов")
    bot.register_next_step_handler(msg, process_expense_step)


# Записываем траты пользователя в бд. Если есть лимиты, сообщаем, сколько из них потрачено.
def process_expense_step(message):
    try:
        user_id = message.chat.id
        parts = message.text.split(' ', 1)
        amount = float(parts[0])
        expense_date = date.today().strftime('%Y-%m-%d')

        conn = create_connection("pythonsqlite.db")
        if conn is not None:
            total_for_day = add_or_update_expense(conn, user_id, expense_date, amount)[1]
            total_for_week = get_spent_this_week(conn, user_id)
            daily_limit = get_daily_limit(conn, message.chat.id)
            weekly_limit = get_weekly_limit(conn, message.chat.id)
            answ = "Расход сохранен."
            if daily_limit:
                answ += f"\nПотрачено из дневного лимита: {str(total_for_day)}/{str(daily_limit)}"
            if weekly_limit:
                answ += f"\nПотрачено из недельного лимита: {str(total_for_week)}/{str(weekly_limit)}"
            bot.reply_to(message, answ)
        else:
            bot.reply_to(message, "Ошибка. Попробуйте еще раз.")
    except ValueError:
        bot.reply_to(message, WRONG_VALUE_MESSAGE)


# Получаем дневной лимит пользователя из бд.
def get_daily_limit(conn, user_id):
    cur = conn.cursor()
    cur.execute("SELECT amount FROM daily_limits WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else None


# Получаем недельный лимит пользователя из бд.
def get_weekly_limit(conn, user_id):
    cur = conn.cursor()
    cur.execute("SELECT amount FROM weekly_limits WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else None


# Получаем траты пользователя по дате.
def get_expense_for_user_and_date(conn, user_id, expense_date):
    cur = conn.cursor()
    cur.execute("SELECT id, amount FROM expenses WHERE user_id=? AND expense_date=?", (user_id, expense_date))
    return cur.fetchone()


# Обновляем трату пользователя в бд. Считаем, что запись за определенную дату уже существует.
def update_expense(conn, expense_id, new_amount):
    sql = ''' UPDATE expenses
              SET amount = amount + ?
              WHERE id = ?'''
    cur = conn.cursor()
    cur.execute(sql, (new_amount, expense_id))
    conn.commit()


# Устанавливаем трату за определенную дату.
def add_expense(conn, expense):
    sql = ''' INSERT INTO expenses(user_id, expense_date, amount)
              VALUES(?,?,?) '''
    cur = conn.cursor()
    cur.execute(sql, expense)
    conn.commit()
    return cur.lastrowid


# Определяем, есть ли траты за определенную дату. Если есть, прибавляем сумму к текущим тратам,
# если нет - указываем новую.
def add_or_update_expense(conn, user_id, expense_date, amount):
    existing_expense = get_expense_for_user_and_date(conn, user_id, expense_date)
    if existing_expense:
        update_expense(conn, existing_expense[0], amount)
    else:
        add_expense(conn, (user_id, expense_date, amount))
    return get_expense_for_user_and_date(conn, user_id, expense_date)


# Обработчик команд для установления лимитов.
@bot.message_handler(commands=['budget'])
def budget(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Установить лимит на день", callback_data="budget_set_daily_limit"))
    markup.add(types.InlineKeyboardButton("Установить лимит на неделю", callback_data="budget_set_weekly_limit"))
    markup.add(types.InlineKeyboardButton("Удалить лимит на день", callback_data="budget_delete_daily_limit"))
    markup.add(types.InlineKeyboardButton("Удалить лимит на неделю", callback_data="budget_delete_weekly_limit"))
    markup.add(types.InlineKeyboardButton("Назад", callback_data="escape"))
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)


# Определяем какое конкретно действие с лимитами нужно совершить и вызываем соответствующую функцию.
def handle_budget_query(call):
    user_id = call.from_user.id
    conn = create_connection(DB_NAME)

    def request_limit_amount(next_call, limit_type):
        msg = bot.send_message(next_call.message.chat.id, "Введите сумму лимита:")
        bot.register_next_step_handler(msg, lambda message: handle_set_limit(message, limit_type))

    if call.data == "budget_set_daily_limit":
        request_limit_amount(call, "daily")
    elif call.data == "budget_set_weekly_limit":
        request_limit_amount(call, "weekly")
    elif call.data == "budget_delete_daily_limit":
        if delete_daily_limit(conn, user_id):
            bot.answer_callback_query(call.id, "Дневной лимит удален.")
            bot.send_message(call.message.chat.id, "Дневной лимит удален.")
        else:
            bot.send_message(call.message.chat.id, "Удалить лимит не удалось, попробуйте еще раз.")
    elif call.data == "budget_delete_weekly_limit":
        if delete_weekly_limit(conn, user_id):
            bot.answer_callback_query(call.id, "Недельный лимит удален.")
            bot.send_message(call.message.chat.id, "Недельный лимит удален.")
        else:
            bot.send_message(call.message.chat.id, "Удалить лимит не удалось, попробуйте еще раз.")


# Определяем какой лимит нужно установить.
def handle_set_limit(message, limit_type):
    try:
        amount = float(message.text)
        user_id = message.chat.id

        conn = create_connection("pythonsqlite.db")
        if conn is not None:
            if limit_type == "daily":
                set_daily_limit(conn, user_id, amount)
                bot.send_message(message.chat.id, "Дневной лимит установлен.")
            elif limit_type == "weekly":
                set_weekly_limit(conn, user_id, amount)
                bot.send_message(message.chat.id, "Недельный лимит установлен.")
        else:
            bot.send_message(message.chat.id, "Ошибка при соединении с базой данных.")
    except ValueError:
        bot.reply_to(message, WRONG_VALUE_MESSAGE)


# Устанавливаем дневной лимит.
def set_daily_limit(conn, user_id, amount):
    cur = conn.cursor()
    cur.execute("REPLACE INTO daily_limits (user_id, amount) VALUES (?, ?)", (user_id, amount))
    conn.commit()


# Устанавливаем недельный лимит.
def set_weekly_limit(conn, user_id, amount):
    cur = conn.cursor()
    cur.execute("REPLACE INTO weekly_limits (user_id, amount) VALUES (?, ?)", (user_id, amount))
    conn.commit()


# Удаляем дневной лимит.
def delete_daily_limit(conn, user_id):
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM daily_limits WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except:
        return False


# Удаляем недельный лимит.
def delete_weekly_limit(conn, user_id):
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM weekly_limits WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except:
        return False


# Определяем, что какой анализ трат нужно произвести.
def analysis_query(call):
    if call.data == 'analysis_weekly_report':
        weekly_report(call.message)
    elif call.data == 'analysis_monthly_report':
        monthly_report(call.message)


# Составляем недельный отчет о тратах
@bot.message_handler(commands=['monthly_report'])
def monthly_report(message):
    conn = create_connection(DB_NAME)
    amount_spent = get_spent_this_month(conn, message.chat.id)
    bot.reply_to(message, f"Ваши расходы за текущий месяц составили: {amount_spent}")


# Составляем месячный отчет о тратах
@bot.message_handler(commands=['weekly_report'])
def weekly_report(message):
    conn = create_connection(DB_NAME)
    amount_spent = get_spent_this_week(conn, message.chat.id)
    bot.reply_to(message, f"Ваши расходы за текущую неделю составили: {amount_spent}")


# Пользователь выбирает анализ, который хочет получить.
@bot.message_handler(commands=['analysis'])
def analysis(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Отчет за неделю", callback_data="analysis_weekly_report"))
    markup.add(types.InlineKeyboardButton("Отчет за месяц", callback_data="analysis_monthly_report"))
    markup.add(types.InlineKeyboardButton("Назад", callback_data="escape"))
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)


# Получаем дату старта текущей недели.
def get_start_of_current_week():
    today = datetime.datetime.now()
    start_of_week = today - datetime.timedelta(days=today.weekday())
    return start_of_week.strftime('%Y-%m-%d')


# Получаем траты за неделю.
def get_spent_this_week(conn, user_id):
    cur = conn.cursor()
    start_of_week = get_start_of_current_week()

    cur.execute("""
        SELECT SUM(amount) 
        FROM expenses 
        WHERE user_id = ? AND expense_date >= ?
        """, (user_id, start_of_week))
    result = cur.fetchone()
    return result[0] if result[0] is not None else 0


# Получаем траты за месяц
def get_spent_this_month(conn, user_id):
    cur = conn.cursor()

    current_date = datetime.datetime.now()
    first_day_of_month = datetime.datetime(current_date.year, current_date.month, 1).strftime('%Y-%m-%d')
    current_date_str = current_date.strftime('%Y-%m-%d')

    query = """
        SELECT SUM(amount) 
        FROM expenses 
        WHERE user_id = ? AND expense_date >= ? AND expense_date <= ?
    """
    cur.execute(query, (user_id, first_day_of_month, current_date_str))
    result = cur.fetchone()

    return result[0] if result[0] is not None else 0


# Получаем URL гифки.
def get_gif_url(tag):
    url = f"https://api.giphy.com/v1/gifs/random?api_key={GIPHY_API_KEY}&tag={tag}"
    response = requests.get(url)
    data = response.json()
    try:
        gif_url = data['data']['images']['original']['url']
        return gif_url
    except KeyError:
        return None


# Отправляем гифку.
@bot.message_handler(commands=['getgif'])
def send_gif(message):
    gif_url = get_gif_url("finance")
    if gif_url:
        bot.send_animation(chat_id=message.chat.id, animation=gif_url)
    else:
        bot.send_message(chat_id=message.chat.id, text="Не удалось найти подходящий GIF. Попробуйте снова.")


# Создание таблицы sqlite.
def create_table(conn, create_table_sql):
    c = conn.cursor()
    c.execute(create_table_sql)


# Подключение к базе данных и создание необходимых таблиц.
def connect():
    sql_create_expenses_table = """ CREATE TABLE IF NOT EXISTS expenses (
                                        id integer PRIMARY KEY,
                                        user_id integer NOT NULL,
                                        expense_date text NOT NULL,
                                        amount real NOT NULL
                                    ); """

    sql_create_daily_limits_table = """ CREATE TABLE IF NOT EXISTS daily_limits (
                                            user_id INTEGER PRIMARY KEY,
                                            amount REAL NOT NULL
                                        );"""
    sql_create_weekly_limits_table = """ CREATE TABLE IF NOT EXISTS weekly_limits (
                                            user_id INTEGER PRIMARY KEY,
                                            amount REAL NOT NULL
                                            );"""

    conn = create_connection(DB_NAME)

    if conn is not None:
        create_table(conn, sql_create_expenses_table)
        create_table(conn, sql_create_daily_limits_table)
        create_table(conn, sql_create_weekly_limits_table)
        return True
    else:
        return False


cn = connect()
while not cn:
    cn = connect()

bot.polling()
