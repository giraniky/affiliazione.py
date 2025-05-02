import requests
import time
from datetime import datetime
from collections import Counter
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# === CONFIG ===
USERNAME = "Sheet"
PASSWORD = "SyncSheet"
URL = "https://mn37hxjeciuzjxk.pannello.ovh/api/get_orders/"
PRODUCT_URL = "https://mn37hxjeciuzjxk.pannello.ovh/api/get_products/"
BOT_TOKEN = "8179229896:AAGLTqMJYsXjqNP2aiEU9PGbhVp9IRhB3jE"

# === FUNZIONI ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ciao! Inviami:\n"
        "- Solo ASIN (uno per riga) → userò la data di oggi e marketplace DE.\n"
        "- Oppure scrivi la prima riga come codice marketplace (es. DE, FR, IT) o come data (YYYY-MM-DD).\n"
        "- Puoi anche scrivere:\n"
        "  FR\n  2025-04-14\n  B08K8W6HXT\n  B08ABCDEF\n"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Default values
    selected_marketplace = "DE"
    selected_date = datetime.now().date()
    asin_lines = []

    # Analizza le righe iniziali
    for line in lines:
        if line.upper() in ["DE", "FR", "IT", "ES", "UK", "US"]:
            selected_marketplace = line.upper()
        elif len(line) == 10 and line.startswith("B0"):
            asin_lines.append(line)
        else:
            try:
                selected_date = datetime.strptime(line, "%Y-%m-%d").date()
            except ValueError:
                asin_lines.append(line)

    asin_counts = Counter(asin_lines)

    # Calcola timestamp
    start_of_day = int(time.mktime(datetime(selected_date.year, selected_date.month, selected_date.day).timetuple()))
    end_of_day = int(time.mktime(datetime(selected_date.year, selected_date.month, selected_date.day, 23, 59, 59).timetuple()))

    # Chiamata API ordini
    response = requests.post(URL, data={"username": USERNAME, "password": PASSWORD})
    orders_data = response.json()

    report = f"📅 Data: {selected_date}\n📦 Marketplace: {selected_marketplace}\n\n"
    check_results = []

    if orders_data.get("success"):
        filtered_orders = [
            order for order in orders_data["orders"]
            if start_of_day <= int(order["order_date"]) <= end_of_day and order["marketplace"] == selected_marketplace
        ]
        order_asins = [order["asin"] for order in filtered_orders]
        order_counts = Counter(order_asins)

        if not filtered_orders:
            report += "❌ Nessun ordine trovato per questa data.\n"
        else:
            # Analisi ASIN mancanti
            asin_missing_info = []
            for asin, required_count in order_counts.items():
                present = asin_counts.get(asin, 0)
                if present < required_count:
                    # Recupera info prodotto
                    try:
                        product_resp = requests.post(
                            PRODUCT_URL,
                            data={
                                "username": USERNAME,
                                "password": PASSWORD,
                                "asin": asin,
                                "marketplace": selected_marketplace
                            }
                        )
                        product_data = product_resp.json()
                        if product_data.get("success") and product_data.get("products"):
                            product = product_data["products"][0]
                            price_str = product.get("price", "0")
                            name = product.get("name", "Nome non disponibile")
                            price = float(price_str.replace(",", "."))
                        else:
                            name = "Nome non disponibile"
                            price = 0
                    except Exception as e:
                        print(f"Errore nel recupero info per {asin}: {e}")
                        name = "Errore nel recupero"
                        price = 0

                    asin_missing_info.append({
                        "asin": asin,
                        "required": required_count,
                        "present": present,
                        "price": price,
                        "name": name
                    })

            # Ordina per prezzo decrescente
            asin_missing_info.sort(key=lambda x: x["price"], reverse=True)

            # Costruzione messaggi
            check_results = [
                f"🔴 ASIN {x['asin']} ({x['name']}): richiesto {x['required']}, inserito {x['present']}, prezzo: {x['price']}€"
                for x in asin_missing_info
            ]

            if not check_results:
                report += "✅ Tutti gli ASIN negli ordini sono presenti almeno il numero di volte inserito.\n"
            else:
                report += "\n".join(check_results)
    else:
        report += "⚠️ Errore nella chiamata all'API ordini."

    await update.message.reply_text(report)

# === MAIN ===

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

if __name__ == '__main__':
    app.run_polling()
