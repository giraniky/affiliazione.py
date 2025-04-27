import requests
import time
from datetime import datetime
from collections import Counter
import pandas as pd
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# === CONFIG ===
USERNAME = "Sheet"
PASSWORD = "SyncSheet"
URL = "https://mn37hxjeciuzjxk.pannello.ovh/api/get_orders/"
BOT_TOKEN = "8179229896:AAGLTqMJYsXjqNP2aiEU9PGbhVp9IRhB3jE"

# === FUNZIONI ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """Ciao! Puoi:
- Inviare una lista di ASIN (uno per riga) come testo → userò la data di oggi e marketplace DE.
- Inviare testo con prima riga marketplace (DE, FR, IT, ES, UK, US) e/o seconda riga data (YYYY-MM-DD).
- Oppure caricare un file Excel (.xls o .xlsx) con colonne 'ASIN', opzionali 'Marketplace' e 'Date'"""
    )

async def process_asin_list(asin_lines, selected_marketplace, selected_date):
    asin_counts = Counter(asin_lines)
    start_of_day = int(time.mktime(datetime(
        selected_date.year, selected_date.month, selected_date.day
    ).timetuple()))
    end_of_day = int(time.mktime(datetime(
        selected_date.year, selected_date.month, selected_date.day, 23, 59, 59
    ).timetuple()))

    # Chiamata API
    response = requests.post(URL, data={"username": USERNAME, "password": PASSWORD})
    orders_data = response.json()

    report = f"📅 Data: {selected_date}\n📦 Marketplace: {selected_marketplace}\n\n"
    if orders_data.get("success"):
        filtered = [o for o in orders_data.get("orders", [])
                    if start_of_day <= int(o.get("order_date", 0)) <= end_of_day
                    and o.get("marketplace") == selected_marketplace]
        if not filtered:
            report += "❌ Nessun ordine trovato per questa data."
            return report

        order_asins = [o.get("asin") for o in filtered]
        order_counts = Counter(order_asins)
        missing = []
        for asin, req in order_counts.items():
            present = asin_counts.get(asin, 0)
            if present < req:
                price = 0.0
                for o in filtered:
                    if o.get("asin") == asin:
                        try:
                            price = float(str(o.get("price", "0")).replace(",", "."))
                        except ValueError:
                            pass
                        break
                missing.append({"asin": asin, "required": req, "present": present, "price": price})
        missing.sort(key=lambda x: x["price"], reverse=True)
        if not missing:
            report += "✅ Tutti gli ASIN negli ordini sono presenti almeno il numero di volte inserito."  
        else:
            for m in missing:
                report += f"🔴 ASIN {m['asin']}: richiesto {m['required']}, inserito {m['present']}, prezzo: {m['price']}€\n"
    else:
        report += "⚠️ Errore nella chiamata all'API."
    return report

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    selected_marketplace = "DE"
    selected_date = datetime.now().date()
    asin_lines = []

    for line in lines:
        up = line.upper()
        if up in ["DE","FR","IT","ES","UK","US"]:
            selected_marketplace = up
        elif len(line) == 10 and line.startswith("B0"):
            asin_lines.append(line)
        else:
            try:
                selected_date = datetime.strptime(line, "%Y-%m-%d").date()
            except ValueError:
                if len(line) > 0:
                    asin_lines.append(line)
    report = await process_asin_list(asin_lines, selected_marketplace, selected_date)
    await update.message.reply_text(report)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(('.xls', '.xlsx')):
        return await update.message.reply_text("Per favore carica un file Excel (.xls o .xlsx).")
    file = await doc.get_file()
    path = f"/tmp/{doc.file_name}"
    await file.download_to_drive(path)

    try:
        # Salta la seconda riga di stile (index 1)
        df = pd.read_excel(path, skiprows=[1])
    except Exception as e:
        return await update.message.reply_text(f"Errore lettura Excel: {e}")

    asin_lines = df['ASIN'].dropna().astype(str).tolist() if 'ASIN' in df.columns else []
    selected_marketplace = df['Marketplace'].iloc[0].upper() if 'Marketplace' in df.columns and pd.notna(df['Marketplace'].iloc[0]) else 'DE'
    if 'Date' in df.columns and pd.notna(df['Date'].iloc[0]):
        try:
            selected_date = pd.to_datetime(df['Date'].iloc[0]).date()
        except Exception:
            selected_date = datetime.now().date()
    else:
        selected_date = datetime.now().date()

    if not asin_lines:
        return await update.message.reply_text("Il file non contiene la colonna 'ASIN' o è vuota.")

    report = await process_asin_list(asin_lines, selected_marketplace, selected_date)
    await update.message.reply_text(report)

# === MAIN ===
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, handle_document))

if __name__ == '__main__':
    app.run_polling()
