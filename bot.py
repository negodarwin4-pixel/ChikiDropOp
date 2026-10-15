import os
import asyncio
import logging
import random
import sqlite3
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
DB_PATH = os.getenv("DB_PATH", "casebot.sqlite3")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("neon_cases")

# One case. Chance percentages total exactly 100%.
CASE = {
    "id": "neon",
    "name": "🌌 Неоновый кейс",
    "cost": 1,
    "items": [
        {"name": "🟣 Фиолетовый осколок", "rank": "F", "rarity": "Обычный", "chance": 50.0, "value": 1},
        {"name": "💚 Неоновый кристалл", "rank": "E", "rarity": "Необычный", "chance": 25.0, "value": 2},
        {"name": "🔷 Кристалл глубины", "rank": "D", "rarity": "Редкий", "chance": 15.0, "value": 5},
        {"name": "🟣 Эпическая сфера", "rank": "C", "rarity": "Эпический", "chance": 7.0, "value": 12},
        {"name": "👑 Корона бездны", "rank": "B", "rarity": "Легендарный", "chance": 2.5, "value": 30},
        {"name": "🔴 Сердце сингулярности", "rank": "A", "rarity": "Мифический", "chance": 0.5, "value": 100},
    ],
}
RANK_EMOJI = {"F": "⚪", "E": "🟢", "D": "🔵", "C": "🟣", "B": "🟠", "A": "🔴"}

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY, username TEXT NOT NULL DEFAULT '',
            first_name TEXT NOT NULL DEFAULT '', tickets INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS inventory(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            item_name TEXT NOT NULL, rank TEXT NOT NULL, rarity TEXT NOT NULL,
            value INTEGER NOT NULL, case_name TEXT NOT NULL, won_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS openings(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            item_name TEXT NOT NULL, rank TEXT NOT NULL, chance REAL NOT NULL,
            opened_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS ticket_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL, delta INTEGER NOT NULL,
            note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""")

def register(user):
    with connect() as con:
        con.execute("""INSERT INTO users(user_id, username, first_name, tickets, created_at)
            VALUES(?,?,?,0,?) ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username, first_name=excluded.first_name""",
            (user.id, user.username or "", user.first_name or "", now()))

def admin(user_id):
    return user_id in ADMIN_IDS

def menu(user_id):
    rows = [
        [InlineKeyboardButton("🎁 Открыть кейс", callback_data="case")],
        [InlineKeyboardButton("🎟 Мои билеты", callback_data="balance"),
         InlineKeyboardButton("🎒 Инвентарь", callback_data="inventory")],
        [InlineKeyboardButton("📜 История", callback_data="history"),
         InlineKeyboardButton("📊 Шансы и экономика", callback_data="odds")],
    ]
    if admin(user_id):
        rows.append([InlineKeyboardButton("🛠 Админ-панель", callback_data="admin")])
    return InlineKeyboardMarkup(rows)

def back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В меню", callback_data="home")]])

def get_balance(uid):
    with connect() as con:
        row = con.execute("SELECT tickets FROM users WHERE user_id=?", (uid,)).fetchone()
        return int(row["tickets"]) if row else 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register(update.effective_user)
    await update.message.reply_text(
        "💜 <b>NEON CASES</b>\n\n"
        "Один кейс. Шесть рангов — от F до A.\n"
        "Открытие стоит 1 🎟 билет.\n\n"
        "Билеты выдаёт только администратор.\n"
        "Выбирай действие:",
        parse_mode=ParseMode.HTML, reply_markup=menu(update.effective_user.id))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — главное меню\n/id — твой Telegram ID\n\n"
        "Администратор: /give USER_ID КОЛИЧЕСТВО [примечание]\n"
        "/take USER_ID КОЛИЧЕСТВО\n/balance USER_ID\n/users\n/ticketlog")

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Твой Telegram ID: <code>{update.effective_user.id}</code>",
                                    parse_mode=ParseMode.HTML)

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    register(q.from_user)
    data = q.data

    if data == "home":
        await q.edit_message_text("💜 <b>NEON CASES</b>\nВыбери действие:",
                                  parse_mode=ParseMode.HTML, reply_markup=menu(uid))
    elif data == "case":
        await q.edit_message_text(
            f"<b>{CASE['name']}</b>\n\nСтоимость: <b>{CASE['cost']} 🎟</b>\n"
            "Шансы и стоимость предметов доступны в разделе «Шансы и экономика».",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎲 Открыть за 1 🎟", callback_data="open")],
                [InlineKeyboardButton("📊 Шансы и экономика", callback_data="odds")],
                [InlineKeyboardButton("⬅️ В меню", callback_data="home")]]))
    elif data == "balance":
        await q.edit_message_text(f"🎟 Твой баланс: <b>{get_balance(uid)}</b>",
                                  parse_mode=ParseMode.HTML, reply_markup=back())
    elif data == "odds":
        lines = ["<b>📊 Шансы и игровая стоимость</b>", "",
                 "Стоимость открытия: 1 🎟", "Ценность — условные игровые единицы, не деньги.", ""]
        for item in CASE["items"]:
            lines.append(f"{RANK_EMOJI[item['rank']]} <b>Ранг {item['rank']} — {item['rarity']}</b>")
            lines.append(f"Шанс: {item['chance']:g}% · Ценность: {item['value']} ед.")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=back())
    elif data == "open":
        # Atomic balance check/debit prevents concurrent double spending.
        with connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT tickets FROM users WHERE user_id=?", (uid,)).fetchone()
            balance = int(row["tickets"]) if row else 0
            if balance < CASE["cost"]:
                con.rollback()
                await q.edit_message_text(
                    f"❌ Не хватает билетов.\nБаланс: {balance} 🎟\nНужно: 1 🎟",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🎟 Мои билеты", callback_data="balance")],
                        [InlineKeyboardButton("⬅️ В меню", callback_data="home")]]))
                return
            con.execute("UPDATE users SET tickets=tickets-1 WHERE user_id=?", (uid,))
            con.commit()

        item = random.choices(CASE["items"], weights=[x["chance"] for x in CASE["items"]], k=1)[0]
        frames = [
            "🎁 <b>Открываем НЕОНОВЫЙ КЕЙС</b>\n\n▰▱▱▱▱ 20%\n🟣 Заряжаем кристалл...",
            "🎁 <b>Открываем НЕОНОВЫЙ КЕЙС</b>\n\n▰▰▱▱▱ 40%\n💠 Сканируем предметы...",
            "🎁 <b>Открываем НЕОНОВЫЙ КЕЙС</b>\n\n▰▰▰▱▱ 60%\n⚡ Ранг почти определён...",
            "🎁 <b>Открываем НЕОНОВЫЙ КЕЙС</b>\n\n▰▰▰▰▱ 80%\n🌌 Материализуем награду...",
        ]
        for frame in frames:
            try:
                await q.edit_message_text(frame, parse_mode=ParseMode.HTML)
            except Exception:
                pass
            await asyncio.sleep(0.55)

        with connect() as con:
            con.execute("INSERT INTO inventory(user_id,item_name,rank,rarity,value,case_name,won_at) VALUES(?,?,?,?,?,?,?)",
                        (uid, item["name"], item["rank"], item["rarity"], item["value"], CASE["name"], now()))
            con.execute("INSERT INTO openings(user_id,item_name,rank,chance,opened_at) VALUES(?,?,?,?,?)",
                        (uid, item["name"], item["rank"], item["chance"], now()))
        await q.edit_message_text(
            f"✨ <b>ПРЕДМЕТ ВЫПАЛ!</b> ✨\n\n"
            f"{RANK_EMOJI[item['rank']]} <b>{item['name']}</b>\n"
            f"Ранг: <b>{item['rank']} — {item['rarity']}</b>\n"
            f"Шанс выпадения: <b>{item['chance']:g}%</b>\n"
            f"Игровая ценность: <b>{item['value']} ед.</b>\n\n"
            f"🎟 Осталось билетов: {get_balance(uid)}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎁 Открыть ещё", callback_data="case")],
                [InlineKeyboardButton("🎒 Инвентарь", callback_data="inventory")],
                [InlineKeyboardButton("⬅️ В меню", callback_data="home")]]))
    elif data == "inventory":
        with connect() as con:
            rows = con.execute("SELECT item_name,rank,rarity,value FROM inventory WHERE user_id=? ORDER BY id DESC LIMIT 25",
                               (uid,)).fetchall()
        if rows:
            body = "\n".join(f"{RANK_EMOJI[r['rank']]} <b>{r['item_name']}</b> — {r['rank']} ({r['rarity']}) · {r['value']} ед." for r in rows)
        else:
            body = "Инвентарь пока пуст. Открой кейс!"
        await q.edit_message_text("🎒 <b>Инвентарь</b>\n\n" + body, parse_mode=ParseMode.HTML, reply_markup=back())
    elif data == "history":
        with connect() as con:
            rows = con.execute("SELECT item_name,rank,chance,opened_at FROM openings WHERE user_id=? ORDER BY id DESC LIMIT 10",
                               (uid,)).fetchall()
        body = "\n".join(f"{RANK_EMOJI[r['rank']]} {r['item_name']} · ранг {r['rank']} · {r['chance']:g}%" for r in rows) if rows else "Открытий пока нет."
        await q.edit_message_text("📜 <b>История открытий</b>\n\n" + body, parse_mode=ParseMode.HTML, reply_markup=back())
    elif data == "admin":
        if not admin(uid):
            await q.edit_message_text("⛔ Нет доступа.")
            return
        await q.edit_message_text(
            "🛠 <b>Админ-панель</b>\n\n"
            "/give USER_ID КОЛИЧЕСТВО [примечание]\n"
            "/take USER_ID КОЛИЧЕСТВО\n"
            "/balance USER_ID\n/users\n/ticketlog",
            parse_mode=ParseMode.HTML, reply_markup=back())

async def give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin(update.effective_user.id):
        await update.message.reply_text("⛔ Команда доступна только администратору."); return
    if len(context.args) < 2:
        await update.message.reply_text("Формат: /give USER_ID КОЛИЧЕСТВО [примечание]"); return
    try:
        target, amount = int(context.args[0]), int(context.args[1])
        if amount < 1 or amount > 100000: raise ValueError
    except ValueError:
        await update.message.reply_text("Укажи корректный ID и количество от 1 до 100000."); return
    with connect() as con:
        if not con.execute("SELECT 1 FROM users WHERE user_id=?", (target,)).fetchone():
            await update.message.reply_text("Игрок не найден. Пусть сначала нажмёт /start."); return
        con.execute("UPDATE users SET tickets=tickets+? WHERE user_id=?", (amount, target))
        con.execute("INSERT INTO ticket_log(admin_id,user_id,delta,note,created_at) VALUES(?,?,?,?,?)",
                    (update.effective_user.id,target,amount," ".join(context.args[2:])[:200],now()))
    await update.message.reply_text(f"✅ Выдано {amount} 🎟 пользователю {target}.")

async def take(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin(update.effective_user.id):
        await update.message.reply_text("⛔ Команда доступна только администратору."); return
    if len(context.args) != 2:
        await update.message.reply_text("Формат: /take USER_ID КОЛИЧЕСТВО"); return
    try:
        target, amount = int(context.args[0]), int(context.args[1])
        if amount < 1: raise ValueError
    except ValueError:
        await update.message.reply_text("Укажи корректный ID и количество."); return
    with connect() as con:
        row = con.execute("SELECT tickets FROM users WHERE user_id=?", (target,)).fetchone()
        if not row:
            await update.message.reply_text("Пользователь не найден."); return
        removed = min(amount, int(row["tickets"]))
        con.execute("UPDATE users SET tickets=tickets-? WHERE user_id=?", (removed,target))
        con.execute("INSERT INTO ticket_log(admin_id,user_id,delta,note,created_at) VALUES(?,?,?,?,?)",
                    (update.effective_user.id,target,-removed,"admin take",now()))
    await update.message.reply_text(f"✅ Списано {removed} 🎟.")

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа."); return
    if len(context.args) != 1:
        await update.message.reply_text("Формат: /balance USER_ID"); return
    try: target = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом."); return
    with connect() as con:
        row = con.execute("SELECT tickets,first_name,username FROM users WHERE user_id=?", (target,)).fetchone()
    await update.message.reply_text(f'🎟 {row["tickets"]} билетов · {row["first_name"]} (@{row["username"] or "нет"})' if row else "Пользователь не найден.")

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа."); return
    with connect() as con:
        rows = con.execute("SELECT user_id,first_name,username,tickets FROM users ORDER BY created_at DESC LIMIT 50").fetchall()
    body = "\n".join(f'{r["first_name"]} (@{r["username"] or "нет"}) · <code>{r["user_id"]}</code> · 🎟 {r["tickets"]}' for r in rows)
    await update.message.reply_text("<b>Пользователи</b>\n\n"+(body or "Пока пусто."), parse_mode=ParseMode.HTML)

async def ticketlog_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа."); return
    with connect() as con:
        rows = con.execute("SELECT admin_id,user_id,delta,note FROM ticket_log ORDER BY id DESC LIMIT 20").fetchall()
    body = "\n".join(f'Админ {r["admin_id"]} → {r["user_id"]}: {r["delta"]:+} 🎟 {r["note"]}' for r in rows)
    await update.message.reply_text("📒 <b>История билетов</b>\n\n"+(body or "Записей пока нет."), parse_mode=ParseMode.HTML)

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Нажми /start, чтобы открыть меню.")

def main():
    if not TOKEN: raise SystemExit("Задай переменную BOT_TOKEN.")
    if not ADMIN_IDS: raise SystemExit("Задай ADMIN_IDS — Telegram ID администратора.")
    init_db()
    app = Application.builder().token(TOKEN).build()
    for command, handler in [
        ("start", start), ("help", help_cmd), ("id", id_cmd),
        ("give", give), ("take", take), ("balance", balance_cmd),
        ("users", users_cmd), ("ticketlog", ticketlog_cmd),
    ]:
        app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    log.info("NEON CASES started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
