import os
import re
import sqlite3
import logging
import asyncio
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB = "prices.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PriceBot")


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        store TEXT DEFAULT 'senstroy',
        name TEXT DEFAULT '',
        article TEXT DEFAULT '',
        last_price REAL DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS settings(
        chat_id INTEGER PRIMARY KEY,
        interval_hours INTEGER DEFAULT 2
    )""")
    try:
        conn.execute("ALTER TABLE products ADD COLUMN article TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def get_interval(chat_id):
    conn = get_db()
    row = conn.execute("SELECT interval_hours FROM settings WHERE chat_id=?", (chat_id,)).fetchone()
    conn.close()
    return row["interval_hours"] if row else 2


def set_interval(chat_id, hours):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings(chat_id, interval_hours) VALUES(?, ?)",
        (chat_id, hours),
    )
    conn.commit()
    conn.close()


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

# ─── Senstroy ────────────────────────────────────────────────────

def parse_senstroy(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except:
        return None
    if r.status_code != 200:
        return None
    html = r.text

    name = ""
    og = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
    if og:
        name = og.group(1).strip()
    if not name:
        t = re.search(r"<title>([^<]+)</title>", html)
        if t:
            name = t.group(1).split("|")[0].strip()
    if not name:
        name = "Senstroy товар"

    price = 0.0
    m = re.search(r'<meta\s+itemprop="price"\s+content="([\d.]+)"', html)
    if m:
        price = float(m.group(1))
    if not price:
        m = re.search(r'data-value="([\d.]+)"', html)
        if m:
            price = float(m.group(1))
    if not price:
        m = re.search(r'"price"\s*:\s*"?([\d.]+)"?', html)
        if m:
            price = float(m.group(1))
    if price <= 0:
        return None

    return {"name": name, "sale_price": price / 2, "link": url, "store": "senstroy"}


def search_senstroy(article):
    import html as html_mod
    url = f"https://senstroy.ru/catalog/?q={article}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except:
        return []
    if r.status_code != 200:
        return []
    html = r.text

    results = []
    blocks = re.split(r'item_block\s+"', html)

    for block in blocks[1:]:
        link_m = re.search(
            r'<a\s+href="(/catalog/[^"]+)"\s+class="dark_link\s+js-notice-block__title[^"]*"[^>]*><span>([^<]+)</span>', block
        )
        if not link_m:
            link_m = re.search(r'<a\s+href="(/catalog/[^"]+)"\s+class="dark_link[^"]*"[^>]*><span>([^<]+)</span>', block)
        if not link_m:
            continue

        href, title = link_m.group(1), link_m.group(2)
        full_url = "https://senstroy.ru" + href

        price = 0
        p = re.search(r'data-value="([\d.]+)"', block)
        if p:
            price = float(p.group(1))
        if not price:
            p = re.search(r'class="price_value[^"]*"[^>]*>([\d.,\s]+)', block)
            if p:
                price = float(p.group(1).replace("\xa0", "").replace(" ", "").replace(",", ""))

        art = ""
        a = re.search(r'article_block[^>]*data-value="([^"]+)"', block)
        if a:
            art = html_mod.unescape(a.group(1).strip())

        if any(r["link"] == full_url for r in results):
            continue
        results.append({
            "name": html_mod.unescape(title.strip()),
            "article": art,
            "sale_price": price / 2 if price else 0,
            "link": full_url,
            "store": "senstroy",
        })

    return results[:5]


# ─── Яндекс Маркет ──────────────────────────────────────────────

YAMARKET_HEADERS = {
    **HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Cookie": "spravka=dD0xNzI3MDYyNjI5O2k9MjE2LjE3MC4yMDQuMjU7RD1GRTt1PXlhbmRleDtsPXJ1O209Y29udGluZW50Ow==",
}


def parse_yamarket(url):
    try:
        r = requests.get(url, headers=YAMARKET_HEADERS, timeout=25)
    except:
        return None
    if r.status_code != 200:
        return None
    html = r.text

    name = ""
    t = re.search(r"<title>([^<]+)</title>", html)
    if t:
        name = t.group(1).split("—")[0].split("›")[0].strip()
    if not name:
        name = "Яндекс Маркет товар"

    price = 0.0
    ld = re.search(r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if ld:
        try:
            data = json.loads(ld.group(1))
            if isinstance(data, dict):
                off = data.get("offers", data)
                if isinstance(off, dict):
                    price = float(off.get("price", 0))
        except:
            pass
    if not price:
        for pat in [
            r'<span\s+data-auto="price"[^>]*>([\d\s]+)',
            r'<meta\s+itemprop="price"\s+content="([\d.]+)"',
            r'"price":\s*["\']?(\d+\.?\d*)["\']?',
            r'data-price="([\d.]+)"',
            r'"priceRu":\s*["\']?(\d+\.?\d*)["\']?',
        ]:
            m = re.search(pat, html)
            if m:
                price = float(m.group(1).replace("\xa0", "").replace(" ", ""))
                if price > 0:
                    break

    if price <= 0:
        return None

    return {"name": name, "sale_price": price, "link": url, "store": "yamarket"}


def search_yamarket(text):
    encoded = requests.utils.quote(text)
    urls = [
        f"https://market.yandex.ru/search?text={encoded}&cpa=0",
        f"https://m.market.yandex.ru/search?text={encoded}",
    ]

    html = None
    for url in urls:
        try:
            r = requests.get(url, headers=YAMARKET_HEADERS, timeout=25)
            if r.status_code == 200 and len(r.text) > 500:
                html = r.text
                break
        except:
            continue

    if not html:
        return []

    results = []
    seen_links = set()

    for pat in [
        r'href="(https?://market\.yandex\.ru/(?:product|cc)/[^"]+)"',
        r'href="(/product/[^"]+)"',
    ]:
        for m in re.finditer(pat, html):
            href = m.group(1)
            if not href.startswith("http"):
                href = "https://market.yandex.ru" + href
            if "market.yandex" not in href or href in seen_links:
                continue
            seen_links.add(href)
            results.append({
                "name": f"Яндекс Маркет #{len(results) + 1}",
                "article": text,
                "sale_price": 0,
                "link": href,
                "store": "yamarket",
            })
            if len(results) >= 5:
                break
        if results:
            break

    return results


# ─── Ozon ────────────────────────────────────────────────────────

OZON_HEADERS = {
    **HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


def parse_ozon(url):
    try:
        r = requests.get(url, headers=OZON_HEADERS, timeout=20)
    except:
        return None
    if r.status_code != 200:
        return None
    html = r.text

    name = ""
    n = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    if n:
        name = re.sub(r'<[^>]+>', '', n.group(1)).strip()
    if not name:
        t = re.search(r"<title>([^<]+)</title>", html)
        if t:
            name = t.group(1).split("—")[0].strip()
    if not name:
        name = "Ozon товар"

    price = 0.0
    for pat in [
        (r'"price":\s*"?(\d+\.?\d*)"?', 1),
        (r'"final_price":\s*"?(\d+\.?\d*)"?', 1),
        (r'"min_price":"?(\d+\.?\d*)"?', 1),
        (r'"priceRu":"?(\d+\.?\d*)"?', 1),
        (r'<span[^>]*data-price[^>]*>([\d\s]+)', 1),
        (r'<span[^>]*>([\d\s]+)\s*₽', 1),
    ]:
        m = re.search(pat[0], html)
        if m:
            price = float(m.group(pat[1]).replace("\xa0", "").replace(" ", ""))
            if price > 0:
                break

    if not price:
        ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
        if ld:
            try:
                data = json.loads(ld.group(1))
                if isinstance(data, dict):
                    off = data.get("offers", data)
                    if isinstance(off, dict):
                        price = float(off.get("price", 0))
                    elif isinstance(off, list):
                        price = float(off[0].get("price", 0))
            except:
                pass

    if price <= 0:
        m = re.search(r'(\d[\d\s]*\d)\s*[₽руб]', html[:20000])
        if m:
            price = float(m.group(1).replace("\xa0", "").replace(" ", ""))

    if price <= 0:
        return None

    return {"name": name, "sale_price": price, "link": url, "store": "ozon"}


def search_ozon(text):
    if text.startswith("http") and "ozon.ru" in text:
        info = parse_ozon(text)
        return [info] if info else []

    encoded = requests.utils.quote(text)
    urls = [
        f"https://www.ozon.ru/search/?text={encoded}&from_global=true",
        f"https://www.ozon.ru/search/?text={encoded}",
    ]

    html = None
    for url in urls:
        try:
            r = requests.get(url, headers=OZON_HEADERS, timeout=20)
            if r.status_code == 200 and len(r.text) > 1000:
                html = r.text
                break
        except:
            continue

    if not html:
        return []

    results = []
    seen_links = set()

    for pat in [
        r'href="(/product/[^"]+/)"',
        r'href="(https?://(?:www\.)?ozon\.ru/product/[^"]+)"',
        r'"link":"(/product/[^"]+)"',
    ]:
        for m in re.finditer(pat, html):
            href = m.group(1)
            if not href.startswith("http"):
                href = "https://www.ozon.ru" + href
            if "ozon.ru/product" not in href or href in seen_links:
                continue
            seen_links.add(href)
            results.append({
                "name": f"Ozon #{len(results) + 1}",
                "article": text,
                "sale_price": 0,
                "link": href,
                "store": "ozon",
            })
            if len(results) >= 5:
                break
        if results:
            break

    return results


# ─── Wildberries ───────────────────────────────────────────────────

def _wb_basket(article: str) -> str:
    try:
        n = int(article[:2])
        baskets = [
            (0, 100, "01"), (100, 200, "02"), (200, 300, "03"), (300, 400, "04"),
            (400, 500, "05"), (500, 600, "06"), (600, 700, "07"), (700, 800, "08"),
            (800, 900, "09"), (900, 1000, "10"), (1000, 1100, "11"), (1100, 1200, "12"),
            (1200, 1300, "13"), (1300, 1400, "14"), (1400, 1500, "15"), (1500, 1600, "16"),
            (1600, 1700, "17"), (1700, 1800, "18"), (1800, 1900, "19"), (1900, 2000, "20"),
            (2000, 3000, "21"), (3000, 4000, "22"),
        ]
        for low, high, b in baskets:
            if low <= n < high:
                return b
    except:
        pass
    return "01"


def parse_wildberries(url):
    m = re.search(r"/catalog/(\d+)", url)
    if not m:
        m = re.search(r"wildberries\.ru/(\d+)", url)
    if not m:
        return None
    art = m.group(1)
    basket = _wb_basket(art)
    vol = art[:-2] if len(art) > 2 else "0"
    part = art[:-2] if len(art) > 2 else "0"
    api = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{art}/info/ru/card.json"
    try:
        r = requests.get(api, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
    except:
        return None

    name = data.get("imt_name", data.get("subject", "Wildberries товар"))
    sizes = data.get("sizes", [])
    price = 0
    if sizes:
        p = sizes[0].get("price", {})
        total = p.get("total", 0)
        price = total / 100 if total else 0

    if price <= 0:
        return None

    link = f"https://www.wildberries.ru/catalog/{art}/detail.aspx"
    return {"name": name, "sale_price": price, "link": link, "store": "wildberries"}


def search_wildberries(text):
    if text.isdigit():
        info = parse_wildberries(f"https://www.wildberries.ru/catalog/{text}/detail.aspx")
        return [info] if info else []

    try:
        r = requests.get(
            f"https://search.wb.ru/exactmatch/ns/common/wildberries?query={requests.utils.quote(text)}&resultset=catalog",
            headers=HEADERS, timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json()
    except:
        return []

    results = []
    seen = set()
    for item in data.get("data", {}).get("products", []):
        art = str(item.get("id", ""))
        if not art or art in seen:
            continue
        seen.add(art)
        price = item.get("salePriceU", 0) / 100
        name = item.get("name", f"WB #{art}")
        link = f"https://www.wildberries.ru/catalog/{art}/detail.aspx"
        results.append({
            "name": name[:80],
            "article": art,
            "sale_price": price,
            "link": link,
            "store": "wildberries",
        })
        if len(results) >= 5:
            break

    return results


def parse_product(url, store):
    if store == "yamarket":
        return parse_yamarket(url)
    if store == "ozon":
        return parse_ozon(url)
    if store == "wildberries":
        return parse_wildberries(url)
    return parse_senstroy(url)


def search_products(article, store):
    if store == "yamarket":
        return search_yamarket(article)
    if store == "ozon":
        return search_ozon(article)
    if store == "wildberries":
        return search_wildberries(article)
    return search_senstroy(article)


def store_emoji(store):
    return {"senstroy": "🟢", "yamarket": "🟡", "ozon": "🔵", "wildberries": "🟣"}.get(store, "🟣")


def store_name(store):
    return {"senstroy": "Senstroy", "yamarket": "Яндекс Маркет", "ozon": "Ozon", "wildberries": "Wildberries"}.get(store, store)


# ─── Keyboards ──────────────────────────────────────────────────

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Добавить товар", callback_data="add"),
            InlineKeyboardButton("📦 Мои товары", callback_data="list"),
        ],
        [
            InlineKeyboardButton("🔄 Проверить цены", callback_data="check"),
            InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
        ],
    ])


def settings_keyboard(chat_id):
    hours = get_interval(chat_id)
    options = [1, 2, 3, 4, 6, 8, 12, 24]
    buttons = []
    row = []
    for h in options:
        label = f"{'✅ ' if h == hours else ''}{h}ч"
        row.append(InlineKeyboardButton(label, callback_data=f"setinterval_{h}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔔 Тест уведомления", callback_data="test_notify")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(buttons)


def products_keyboard(rows):
    buttons = []
    for r in rows:
        price = f"{r['last_price']:.2f}₽" if r["last_price"] > 0 else "—"
        label = r["article"] if r["article"] else (r["name"][:25] if r["name"] else f"#{r['id']}")
        buttons.append([InlineKeyboardButton(
            f"❌ {store_emoji(r['store'])} {label} — {price}",
            callback_data=f"remove_{r['id']}"
        )])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(buttons)


# ─── Handlers ────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏷 <b>PRICEBOT</b>\n"
        "Просто отправь артикул товара\n"
        "Я сам найду его на Senstroy и Wildberries\n\n"
        "Или выбери действие:",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id

    if data == "back":
        await query.edit_message_text(
            "🏷 <b>PRICEBOT</b>\n"
            "Просто отправь артикул товара\n"
            "Я сам найду его на Senstroy и Wildberries\n\n"
            "Или выбери действие:",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

    elif data == "add":
        await query.edit_message_text(
            "📝 <b>Добавление товара</b>\n\n"
            "Просто отправь в чат <b>артикул</b> или <b>название</b>\n"
            "Я сам поищу на Senstroy и Wildberries\n\n"
            "<i>Например: HJS066B, 12345678, iPhone 15</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="back")],
            ]),
        )

    elif data == "list":
        conn = get_db()
        rows = conn.execute(
            "SELECT id, url, store, name, article, last_price FROM products WHERE chat_id=? ORDER BY store, id",
            (chat_id,),
        ).fetchall()
        conn.close()
        if not rows:
            await query.edit_message_text(
                "📭 <b>Мои товары</b>\n\nПока пусто.\nНажми «➕ Добавить товар»:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Добавить товар", callback_data="add")],
                ]),
            )
            return

        text = "📦 <b>Мои товары</b>\n\n"
        seen_stores = set()
        for r in rows:
            if r["store"] not in seen_stores:
                seen_stores.add(r["store"])
                text += f"\n{store_emoji(r['store'])} <b>{store_name(r['store'])}</b>\n"
            price = f"{r['last_price']:.2f}₽" if r["last_price"] > 0 else "—"
            label = r["article"] if r["article"] else r["name"][:30]
            text += f"  #{r['id']} {label} — {price}\n"

        text += "\nНажми на товар чтобы удалить:"
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=products_keyboard(rows)
        )

    elif data == "check":
        conn = get_db()
        rows = conn.execute(
            "SELECT id, url, store, name, last_price FROM products WHERE chat_id=?",
            (chat_id,),
        ).fetchall()
        conn.close()
        if not rows:
            await query.edit_message_text("📭 Нет товаров.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text("🔍 <b>Проверяю цены...</b>", parse_mode="HTML")

        for r in rows:
            pid, url, store, last_price = r["id"], r["url"], r["store"], r["last_price"]
            info = await asyncio.get_event_loop().run_in_executor(None, parse_product, url, store)
            if not info:
                await query.message.reply_text(
                    f"⚠️ <b>Ошибка</b> #{pid}\n{store_emoji(store)} <code>{url[:60]}</code>",
                    parse_mode="HTML",
                )
                continue
            new_price = info["sale_price"]
            if last_price > 0 and new_price != last_price:
                diff = new_price - last_price
                sym = "+" if diff > 0 else ""
                msg = (
                    f"{store_emoji(store)} <b>{info['name']}</b>\n"
                    f"💰 {last_price:.2f} → {new_price:.2f} ₽ (<b>{sym}{diff:.2f}</b>)\n"
                    f"🔗 {info['link']}"
                )
            else:
                msg = (
                    f"{store_emoji(store)} <b>{info['name']}</b>\n"
                    f"💰 {new_price:.2f} ₽ — без изменений\n"
                    f"🔗 {info['link']}"
                )
            conn = get_db()
            conn.execute("UPDATE products SET last_price=?, name=? WHERE id=?", (new_price, info["name"], pid))
            conn.commit()
            conn.close()
            await query.message.reply_text(msg, parse_mode="HTML")

    elif data == "settings":
        await query.edit_message_text(
            "⚙️ <b>Настройки</b>\n\nПроверка цены каждые:",
            parse_mode="HTML",
            reply_markup=settings_keyboard(chat_id),
        )

    elif data.startswith("setinterval_"):
        hours = int(data.split("_")[1])
        set_interval(chat_id, hours)
        reschedule_jobs(chat_id)
        await query.edit_message_text(
            f"⚙️ Настройки\n\nПроверка цены каждые: <b>{hours} ч.</b>",
            reply_markup=settings_keyboard(chat_id),
            parse_mode="HTML",
        )

    elif data == "test_notify":
        await query.answer("Отправляю тест через 5 минут...")
        await query.edit_message_text(
            "🔔 Тестовое уведомление будет отправлено через 5 минут.\n\nПродолжай пользоваться ботом.",
            reply_markup=main_menu_keyboard(),
        )

        async def send_test_later():
            await asyncio.sleep(300)
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="🔔 <b>Тест уведомлений!</b>\n\nЕсли ты это видишь — уведомления работают.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Test notify error: {e}")
        asyncio.get_event_loop().create_task(send_test_later())

    elif data.startswith("remove_"):
        pid = int(data.split("_")[1])
        conn = get_db()
        conn.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        rows = conn.execute(
            "SELECT id, url, store, name, article, last_price FROM products WHERE chat_id=? ORDER BY store, id",
            (chat_id,),
        ).fetchall()
        conn.close()
        if rows:
            await query.edit_message_text(
                "✅ Удалено.\n\nНажми чтобы удалить ещё:",
                parse_mode="HTML",
                reply_markup=products_keyboard(rows),
            )
        else:
            await query.edit_message_text(
                "✅ Все товары удалены.",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )


ALL_STORES = ["wildberries", "senstroy"]


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if not text or len(text) > 100:
        return

    await update.message.reply_text("🔍 <b>Ищу товар по всем магазинам...</b>", parse_mode="HTML")

    all_results = []
    for store in ALL_STORES:
        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None, search_products, text, store
            )
            all_results.extend(results)
        except:
            pass

    if not all_results:
        await update.message.reply_text(
            "😕 <b>Ничего не найдено</b>\n"
            "Проверь артикул или попробуй другой запрос.",
            parse_mode="HTML",
        )
        return

    conn = get_db()
    existing_urls = {
        row[0] for row in conn.execute(
            "SELECT url FROM products WHERE chat_id=?", (chat_id,)
        ).fetchall()
    }

    added = []
    skipped = []
    for r in all_results:
        if r["link"] in existing_urls:
            skipped.append(r)
            continue
        conn.execute(
            "INSERT INTO products(chat_id, url, store, name, article, last_price) VALUES(?, ?, ?, ?, ?, ?)",
            (chat_id, r["link"], r["store"], r["name"], r.get("article", ""), r["sale_price"]),
        )
        added.append(r)
    conn.commit()
    conn.close()

    if added:
        lines = []
        for r in added:
            price_str = f"{r['sale_price']:.2f} ₽" if r["sale_price"] > 0 else "—"
            lines.append(f"{store_emoji(r['store'])} <b>{r['name'][:50]}</b>\n💰 {price_str}  🔗 {r['link']}")
        summary = "\n\n".join(lines)
        msg = f"✅ <b>Добавлено {len(added)} товаров!</b>\n\n{summary}"
        if skipped:
            msg += f"\n\n⚠️ Уже отслеживается: <b>{len(skipped)}</b>"
    else:
        msg = "⚠️ <b>Все найденные товары уже добавлены!</b>\nПроверь «📦 Мои товары»."

    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=main_menu_keyboard())


# ─── Авто-проверка цен ──────────────────────────────────────────

async def check_prices(context):
    bot = context.bot
    conn = get_db()
    rows = conn.execute(
        "SELECT p.id, p.chat_id, p.url, p.store, p.name, p.last_price, s.interval_hours "
        "FROM products p LEFT JOIN settings s ON p.chat_id = s.chat_id"
    ).fetchall()
    if not rows:
        conn.close()
        return
    logger.info(f"Checking {len(rows)} products...")

    by_chat = {}
    for r in rows:
        cid = r["chat_id"]
        by_chat.setdefault(cid, []).append(r)

    for chat_id, products in by_chat.items():
        errors = []
        for r in products:
            pid, url, store, last_price = r["id"], r["url"], r["store"], r["last_price"]
            try:
                info = await asyncio.get_event_loop().run_in_executor(None, parse_product, url, store)
            except Exception as e:
                errors.append(f"❌ #{r['id']}: {e}")
                continue
            if not info:
                errors.append(f"❌ {store_emoji(store)} #{r['id']}: не удалось")
                continue
            new_price = info["sale_price"]
            if last_price == 0:
                conn.execute("UPDATE products SET last_price=?, name=? WHERE id=?", (new_price, info["name"], pid))
                conn.commit()
                continue
            if new_price != last_price:
                diff = new_price - last_price
                if diff > 0:
                    emoji, label = "🔴", f"Подорожал на {abs(diff):.2f} ₽"
                else:
                    emoji, label = "🟢", f"Подешевел на {abs(diff):.2f} ₽"
                msg = (
                    f"{emoji} <b>{label}</b>\n\n"
                    f"{store_emoji(store)} <b>{info['name']}</b>\n"
                    f"💰 {last_price:.2f} → {new_price:.2f} ₽\n"
                    f"🔗 {info['link']}"
                )
                try:
                    await bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Send error: {e}")
            conn.execute("UPDATE products SET last_price=?, name=? WHERE id=?", (new_price, info["name"], pid))
            conn.commit()

        summary_lines = ["📊 <b>Сводка:</b>\n"]
        refreshed = conn.execute(
            "SELECT store, name, last_price FROM products WHERE chat_id=?", (chat_id,)
        ).fetchall()
        for p in refreshed:
            price_str = f"{p['last_price']:.2f} ₽" if p["last_price"] > 0 else "—"
            summary_lines.append(f"• {store_emoji(p['store'])} <b>{p['name'][:35]}</b>  💰 {price_str}")
        try:
            await bot.send_message(chat_id=chat_id, text="\n".join(summary_lines), parse_mode="HTML")
            if errors:
                await bot.send_message(chat_id=chat_id, text="⚠️ <b>Проблемы:</b>\n" + "\n".join(errors), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Send error: {e}")

    conn.close()


# ─── Bot lifecycle ──────────────────────────────────────────────

app_ref = None


def reschedule_jobs(chat_id=None):
    if not app_ref:
        return

    async def _do():
        jobs = app_ref.job_queue.get_jobs_by_name("check_prices_dynamic")
        for job in jobs:
            job.schedule_removal()

        conn = get_db()
        if chat_id:
            rows = conn.execute(
                "SELECT DISTINCT interval_hours FROM settings WHERE chat_id=?", (chat_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT DISTINCT interval_hours FROM settings").fetchall()
        conn.close()

        intervals = set(r["interval_hours"] for r in rows) or {2}
        for h in intervals:
            app_ref.job_queue.run_repeating(
                check_prices, interval=h * 3600, first=5, name="check_prices_dynamic",
            )

    loop = asyncio.get_event_loop()
    loop.create_task(_do())


def run_bot():
    global app_ref

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set! Укажите переменную окружения BOT_TOKEN")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    init_db()
    logger.info("PriceBot starting...")

    app = Application.builder().token(BOT_TOKEN).build()
    app_ref = app

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.job_queue.run_repeating(
        check_prices, interval=2 * 3600, first=10, name="check_prices_dynamic",
    )

    logger.info("Bot running!")

    async def _run():
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

    loop.run_until_complete(_run())


def run_flask():
    from flask import Flask
    app = Flask(__name__)
    @app.route("/")
    @app.route("/health")
    def health():
        return "ok"
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    import threading
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
