import os
import json
import sqlite3
import logging
import threading
import requests
from datetime import datetime
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

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


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "PriceBot — отслеживаю цены\n\n"
        "/add_wb <артикул> — товар Wildberries\n"
        "/add_tim <ссылка> — товар TIM-Зейслер\n"
        "/list — мои товары\n"
        "/check — проверить цены\n"
        "/remove <id> — удалить товар"
    )


async def cmd_add_wb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /add_wb 12345678")
        return
    article = context.args[0].strip()
    if not article.isdigit():
        await update.message.reply_text("Артикул WB должен быть числом.")
        return
    conn = get_db()
    conn.execute("INSERT INTO products(chat_id, article, store) VALUES(?, ?, 'wb')", (update.effective_chat.id, article))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Добавлен {article}. Проверка каждые {CHECK_INTERVAL}ч.")


async def cmd_add_tim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /add_tim <ссылка>")
        return
    url = context.args[0].strip()
    if not url.startswith("http"):
        await update.message.reply_text("Нужна ссылка на товар TIM.")
        return
    conn = get_db()
    conn.execute("INSERT INTO products(chat_id, article, store) VALUES(?, ?, 'tim')", (update.effective_chat.id, url))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Добавлен товар TIM. Проверка каждые {CHECK_INTERVAL}ч.")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    rows = conn.execute("SELECT id, article, store, last_price FROM products WHERE chat_id=?", (update.effective_chat.id,)).fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("Пусто. Добавь: /add_wb 12345678")
        return
    text = "Твои товары:\n\n"
    for r in rows:
        store_name = STORE_NAMES.get(r["store"], r["store"])
        price = f"{r['last_price']:.2f} ₽" if r["last_price"] > 0 else "ожидание"
        text += f"ID {r['id']} | {store_name} | {r['article']}\n💰 {price}\n\n"
    await update.message.reply_text(text)


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    rows = conn.execute("SELECT id, article, store, last_price FROM products WHERE chat_id=?", (update.effective_chat.id,)).fetchall()
    if not rows:
        conn.close()
        await update.message.reply_text("Нет товаров.")
        return
    await update.message.reply_text("Проверяю...")
    for r in rows:
        pid, article, store, last_price = r["id"], r["article"], r["store"], r["last_price"]
        info = get_product(article, store)
        if not info:
            await update.message.reply_text(f"{article} — ошибка")
            continue
        new_price = info["sale_price"]
        store_name = STORE_NAMES.get(store, store)
        if last_price > 0 and new_price != last_price:
            diff = new_price - last_price
            sym = "+" if diff > 0 else ""
            msg = f"{info['name']}\n{store_name} | {article}\n{last_price:.2f} → {new_price:.2f} ({sym}{diff:.2f})\n{info['link']}"
        else:
            msg = f"{info['name']}\n{store_name} | {article}\n{new_price:.2f} ₽ — без изменений\n{info['link']}"
        conn.execute("UPDATE products SET last_price=? WHERE id=?", (new_price, pid))
        conn.commit()
        await update.message.reply_text(msg)
    conn.close()


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /remove <id>")
        return
    try:
        pid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом.")
        return
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    await update.message.reply_text("Удалено.")


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
            prefix = "ПОДОРОЖАЛ" if diff > 0 else "ПОДЕШЕВЕЛ"
            msg = f"{prefix}\n{info['name']}\n{store_name} | {article}\n{last_price:.2f} → {new_price:.2f} ({diff:+.2f})\n{info['link']}"
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
    app.add_handler(CommandHandler("add_wb", cmd_add_wb))
    app.add_handler(CommandHandler("add_tim", cmd_add_tim))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("remove", cmd_remove))
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
