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

    # Analisi righe iniziali
    for line in lines:
        if line.upper() in ["DE", "FR", "IT", "ES", "UK", "US"]:
            selected_marketplace = line.upper()
        elif len(line) == 10 and line.startswith("B0"):  # probabilmente un ASIN
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

    # Chiamata API
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
            for asin, required_count in order_counts.items():
                present = asin_counts.get(asin, 0)
                if present < required_count:
                    check_results.append(f"🔴 ASIN {asin}: richiesto {required_count}, inserito {present}")
            if not check_results:
                report += "✅ Tutti gli ASIN negli ordini sono presenti almeno il numero di volte inserito.\n"
            else:
                report += "\n".join(check_results)
    else:
        report += "⚠️ Errore nella chiamata all'API."

    await update.message.reply_text(report)

# === MAIN ===

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

if __name__ == '__main__':
    app.run_polling()
