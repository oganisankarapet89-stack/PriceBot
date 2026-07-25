import os
import json
import sqlite3
import logging
import threading
import requests
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8871269578:AAEpCKDtZIbcQzgnPWjvw1P4vekwL1FVH28")
CHECK_INTERVAL = 6
DB = "prices.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PriceBot")

STORE_NAMES = {"wb": "Wildberries", "tim": "TIM-Зейслер"}


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        article TEXT NOT NULL,
        store TEXT NOT NULL DEFAULT 'wb',
        last_price REAL DEFAULT 0
    )""")
    conn.commit()
    conn.close()


def parse_wb(article):
    url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=RUB&dest=-1257786&nm={article}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        return None
    products = r.json().get("data", {}).get("products", [])
    if not products:
        return None
    p = products[0]
    for s in p.get("sizes", []):
        pr = s.get("price", {})
        if pr and pr.get("product", 0) > 0:
            return {
                "name": p.get("name", ""),
                "sale_price": pr.get("product", 0) / 100,
                "link": f"https://www.wildberries.ru/catalog/{article}/detail.aspx",
            }
    return None


def parse_tim(url):
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html"}
    r = requests.get(url, headers=headers, timeout=20, verify=False)
    if r.status_code != 200:
        return None
    import re
    match = re.search(r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>', r.text, re.DOTALL)
    if not match:
        return None
    ld = json.loads(match.group(1))
    if isinstance(ld, list):
        ld = ld[0]
    offers = ld.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = float(offers.get("price", 0))
    if price <= 0:
        return None
    return {"name": ld.get("name", "TIM товар"), "sale_price": price, "link": url}


def get_product(article, store):
    try:
        if store == "wb":
            return parse_wb(article)
        elif store == "tim":
            return parse_tim(article)
    except Exception as e:
        logger.error(f"Parse error: {e}")
    return None


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Добавить товар", callback_data="add"),
            InlineKeyboardButton("📦 Мои товары", callback_data="list"),
        ],
        [
            InlineKeyboardButton("🔄 Проверить цены", callback_data="check"),
        ],
    ])


def store_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟣 Wildberries", callback_data="store_wb"),
            InlineKeyboardButton("🔵 TIM-Зейслер", callback_data="store_tim"),
        ],
    ])


def products_keyboard(rows):
    buttons = []
    for r in rows:
        store_name = STORE_NAMES.get(r["store"], r["store"])
        price = f"{r['last_price']:.0f}₽" if r["last_price"] > 0 else "—"
        text = f"❌ {r['id']} | {store_name} | {price}"
        buttons.append([InlineKeyboardButton(text, callback_data=f"remove_{r['id']}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(buttons)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "PriceBot\n\nОтслеживаю цены на WB и TIM-Зейслер.\n"
        "Выбери действие:",
        reply_markup=main_menu_keyboard(),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id

    if data == "back":
        await query.edit_message_text(
            "PriceBot\n\nВыбери действие:",
            reply_markup=main_menu_keyboard(),
        )

    elif data == "add":
        await query.edit_message_text(
            "Выбери магазин:",
            reply_markup=store_keyboard(),
        )

    elif data == "store_wb":
        context.user_data["add_store"] = "wb"
        await query.edit_message_text("Отправь артикул товара с Wildberries\n(число из URL)")

    elif data == "store_tim":
        context.user_data["add_store"] = "tim"
        await query.edit_message_text("Отправь ссылку на товар TIM-Зейслер")

    elif data == "list":
        conn = get_db()
        rows = conn.execute(
            "SELECT id, article, store, last_price FROM products WHERE chat_id=?",
            (chat_id,),
        ).fetchall()
        conn.close()
        if not rows:
            await query.edit_message_text(
                "Нет товаров.\n\nНажми «Добавить товар»:",
                reply_markup=main_menu_keyboard(),
            )
            return
        text = "Твои товары:\nНажми чтобы удалить:\n\n"
        await query.edit_message_text(text, reply_markup=products_keyboard(rows))

    elif data == "check":
        conn = get_db()
        rows = conn.execute(
            "SELECT id, article, store, last_price FROM products WHERE chat_id=?",
            (chat_id,),
        ).fetchall()
        conn.close()
        if not rows:
            await query.edit_message_text("Нет товаров.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text("Проверяю цены...")
        for r in rows:
            pid, article, store, last_price = r["id"], r["article"], r["store"], r["last_price"]
            info = get_product(article, store)
            if not info:
                await query.message.reply_text(f"❌ {article} — ошибка")
                continue
            new_price = info["sale_price"]
            store_name = STORE_NAMES.get(store, store)
            if last_price > 0 and new_price != last_price:
                diff = new_price - last_price
                sym = "+" if diff > 0 else ""
                msg = (
                    f"📦 {info['name']}\n"
                    f"🏪 {store_name}\n"
                    f"💰 {last_price:.0f} → {new_price:.0f} ₽ ({sym}{diff:.0f})\n"
                    f"🔗 {info['link']}"
                )
            else:
                msg = (
                    f"📦 {info['name']}\n"
                    f"🏪 {store_name}\n"
                    f"💰 {new_price:.0f} ₽ — без изменений\n"
                    f"🔗 {info['link']}"
                )
            conn.execute("UPDATE products SET last_price=? WHERE id=?", (new_price, pid))
            conn.commit()
            await query.message.reply_text(msg)

    elif data.startswith("remove_"):
        pid = int(data.split("_")[1])
        conn = get_db()
        conn.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        rows = conn.execute(
            "SELECT id, article, store, last_price FROM products WHERE chat_id=?",
            (chat_id,),
        ).fetchall()
        conn.close()
        if rows:
            await query.edit_message_text(
                "Удалено.\n\nНажми чтобы удалить ещё:",
                reply_markup=products_keyboard(rows),
            )
        else:
            await query.edit_message_text(
                "Удалено.\nВсе товары удалены.",
                reply_markup=main_menu_keyboard(),
            )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store = context.user_data.get("add_store")
    if not store:
        return

    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if store == "wb":
        if not text.isdigit():
            await update.message.reply_text("Артикул WB должен быть числом. Попробуй ещё:")
            return
        article = text
    else:
        if not text.startswith("http"):
            await update.message.reply_text("Нужна ссылка на товар. Попробуй ещё:")
            return
        article = text

    await update.message.reply_text("Получаю цену...")

    info = get_product(article, store)
    if not info:
        await update.message.reply_text("Не удалось получить данные. Проверь правильность.")
        return

    conn = get_db()
    conn.execute(
        "INSERT INTO products(chat_id, article, store, last_price) VALUES(?, ?, ?, ?)",
        (chat_id, article, store, info["sale_price"]),
    )
    conn.commit()
    conn.close()

    store_name = STORE_NAMES.get(store, store)
    await update.message.reply_text(
        f"✅ Добавлено!\n\n"
        f"📦 {info['name']}\n"
        f"🏪 {store_name}\n"
        f"💰 {info['sale_price']:.0f} ₽\n"
        f"🔗 {info['link']}\n\n"
        f"Бот будет проверять цену каждые {CHECK_INTERVAL}ч.\n"
        f"Уведомлю если цена поменяется.",
        reply_markup=main_menu_keyboard(),
    )

    context.user_data.pop("add_store", None)


async def check_prices(context):
    bot = context.bot
    conn = get_db()
    rows = conn.execute("SELECT id, chat_id, article, store, last_price FROM products").fetchall()
    if not rows:
        conn.close()
        return
    logger.info(f"Checking {len(rows)} products...")
    for r in rows:
        pid, chat_id, article, store, last_price = r["id"], r["chat_id"], r["article"], r["store"], r["last_price"]
        info = get_product(article, store)
        if not info:
            continue
        new_price = info["sale_price"]
        if last_price == 0:
            conn.execute("UPDATE products SET last_price=? WHERE id=?", (new_price, pid))
            conn.commit()
            continue
        if new_price != last_price:
            diff = new_price - last_price
            store_name = STORE_NAMES.get(store, store)
            if diff > 0:
                emoji = "🔴"
                label = f"Подорожал на {abs(diff):.0f} ₽"
            else:
                emoji = "🟢"
                label = f"Подешевел на {abs(diff):.0f} ₽"
            msg = (
                f"{emoji} {label}\n\n"
                f"📦 {info['name']}\n"
                f"🏪 {store_name}\n"
                f"💰 {last_price:.0f} → {new_price:.0f} ₽\n"
                f"🔗 {info['link']}"
            )
            try:
                await bot.send_message(chat_id=chat_id, text=msg)
            except Exception as e:
                logger.error(f"Send error: {e}")
            conn.execute("UPDATE products SET last_price=? WHERE id=?", (new_price, pid))
            conn.commit()
    conn.close()


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    web.run(host="0.0.0.0", port=port)


def run_bot():
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    init_db()
    logger.info("PriceBot starting...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.job_queue.run_repeating(
        check_prices,
        interval=CHECK_INTERVAL * 3600,
        first=10,
    )
    logger.info("Bot running!")

    async def _run():
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

    loop.run_until_complete(_run())


web = Flask(__name__)


@web.route("/")
def index():
    return "PriceBot is running"


@web.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
