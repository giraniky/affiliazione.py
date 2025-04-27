import re
import requests
import logging
import random
import asyncio
import json
import os
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ForceReply
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# =========================================
# =           CONFIGURAZIONI             =
# =========================================

TELEGRAM_TOKEN = "7388711061:AAFJhBJKsiAubMn1Kp-iqBv-_N-2eK5j7kc"

# Credenziali API
API_URL = "https://login.arateam.cloud/api/get_products/"
USERNAME = "Sheet"
PASSWORD = "SyncSheet"

# Blacklist parole e categorie (lista base “statica” usata come esempio)
BLACKLIST_WORDS = []
BLACKLIST_CATEGORIES = [
    "NO", "sex toys", "salute",
    "cura della persona", "erotismo",
    "contraccezione"
]

# File di configurazione
CONFIG_FILE = "config.json"

# Config di default
default_config = {
    "channel_ids": {
        "IT": None,
        "ES": None,
        "DE": None,
        "FR": None
    },
    "tags": {
        "IT": [],
        "ES": [],
        "DE": [],
        "FR": []
    },
    "tag_indices": {
        "IT": 0,
        "ES": 0,
        "DE": 0,
        "FR": 0
    },
    "publish_delay": 3,
    # Blacklist dinamica da salvare su file (inizialmente vuota)
    "blacklist_words": []
}

# Variabile globale per conservare la configurazione
user_config = {}


# =========================================
# =           FUNZIONI UTILI             =
# =========================================

def load_config() -> dict:
    """
    Carica la configurazione da file JSON, 
    se non esiste il file, ritorna la config di default.
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config_data = json.load(f)
                merged_config = {**default_config, **config_data}
                for key, value in default_config.items():
                    if isinstance(value, dict) and key in merged_config:
                        merged_config[key] = {**value, **merged_config[key]}
                return merged_config
        except Exception as e:
            logging.error(f"Errore nel caricamento di {CONFIG_FILE}: {e}")
            return default_config
    else:
        return default_config

def save_config(config: dict):
    """
    Salva la configurazione su file JSON.
    """
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        logging.info("Configurazione salvata correttamente.")
    except Exception as e:
        logging.error(f"Errore nel salvataggio di {CONFIG_FILE}: {e}")

def normalize_string(input_string: str) -> str:
    """
    Rimuove i caratteri non alfanumerici e converte in minuscolo.
    """
    if input_string is None:
        return ""
    return re.sub(r"[^a-zA-Z0-9]+", "", input_string.lower())

def contains_illegal_category(category: str) -> bool:
    category_normalized = normalize_string(category)
    for cat in BLACKLIST_CATEGORIES:
        if normalize_string(cat) in category_normalized:
            return True
    return False

def contains_blacklisted_word(text: str) -> bool:
    """
    Verifica se `text` contiene una o più parole vietate.
    Unisce la blacklist “statica” con quella dinamica contenuta in user_config.
    """
    text_normalized = normalize_string(text)
    combined_blacklist = set(BLACKLIST_WORDS + user_config.get("blacklist_words", []))
    for word in combined_blacklist:
        if re.search(normalize_string(word), text_normalized):
            return True
    return False

def is_blacklisted(product_name: str, product_category: str) -> bool:
    return (
        contains_illegal_category(product_category) 
        or contains_blacklisted_word(product_name)
    )

def get_next_tag(country: str) -> str:
    """
    Restituisce il tag affiliato successivo per un determinato Paese, 
    ruotandolo automaticamente. Se non ci sono tag, restituisce fallback.
    """
    tags_list = user_config["tags"].get(country, [])
    if not tags_list:
        return "fallbacktag-21"
    idx = user_config["tag_indices"][country]
    tag = tags_list[idx]
    user_config["tag_indices"][country] = (idx + 1) % len(tags_list)
    return tag

def build_amazon_link(asin: str, country: str) -> str:
    domain_map = {
        "IT": "amazon.it",
        "ES": "amazon.es",
        "DE": "amazon.de",
        "FR": "amazon.fr"
    }
    domain = domain_map.get(country, "amazon.it")
    tag = get_next_tag(country)
    return f"https://{domain}/dp/{asin}?tag={tag}"

def fetch_products(marketplace: str) -> list:
    params = {
        "username": USERNAME,
        "password": PASSWORD,
        "marketplace": marketplace
    }
    try:
        response = requests.get(API_URL, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("products"):
                return data["products"]
            else:
                logging.info(f"Nessun prodotto trovato per {marketplace}.")
                return []
        else:
            logging.error(f"Errore nell'API: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logging.error(f"Errore durante il recupero dei prodotti per {marketplace}: {e}")
        return []


# =========================================
# =  FUNZIONI DI PUBBLICAZIONE            =
# =========================================

async def post_to_telegram(bot, chat_id, product, country):
    name = product.get("name", "Prodotto senza nome")
    asin = product.get("asin")
    if not asin:
        logging.error(f"Prodotto senza ASIN: {name}")
        return False

    price = product.get("price", "Non disponibile")
    category = product.get("category", "Sconosciuta") or "Sconosciuta"
    image_url = product.get("image", "")

    link = build_amazon_link(asin, country)

    # Verifica blacklist
    if is_blacklisted(name, category):
        logging.info(f"Prodotto blacklistato: {name}")
        return False

    # Prefisso #adv prima del nome
    caption = (
        f"📦 #adv <b>{name}</b>\n\n"
        f"💰 Prezzo: {price} €\n"
        f"📂 Categoria: {category}\n\n"
        f"🔗 {link}"
    )

    try:
        if image_url:
            await bot.send_photo(chat_id=chat_id, photo=image_url, caption=caption, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")
        logging.info(f"Pubblicato su {country}: {name}")
        return True
    except Exception as e:
        logging.error(f"Errore durante la pubblicazione su {country}: {e}")
        return False

async def publish_continuously(application: ApplicationBuilder, country: str):
    while True:
        chat_id = user_config["channel_ids"][country]
        delay = user_config["publish_delay"]

        if not chat_id:
            logging.info(f"Channel ID per {country} non impostato. Riprovo tra 10 secondi.")
            await asyncio.sleep(10)
            continue

        products = fetch_products(country)
        if not products:
            logging.info(f"Nessun prodotto da pubblicare per {country}.")
            try:
                await application.bot.send_message(chat_id=chat_id, text="Nessun prodotto disponibile al momento.")
            except Exception as e:
                logging.error(f"Errore nell'invio del messaggio di default a {country}: {e}")
            await asyncio.sleep(10)
            continue

        product = random.choice(products)
        name = product.get("name", "Prodotto senza nome")

        if not is_blacklisted(name, product.get("category", "")):
            await post_to_telegram(application.bot, chat_id, product, country)
        else:
            logging.info(f"Prodotto blacklistato per {country}: {name}")

        await asyncio.sleep(delay)


# =========================================
# =          COMANDI TELEGRAM BOT         =
# =========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ciao! Questo bot pubblica prodotti nei rispettivi canali Amazon.\n"
        "Comandi disponibili:\n"
        "- /config per configurare canali, tag e delay.\n"
        "- /pubblica per avviare la pubblicazione continua.\n"
        "- /ferma per fermare la pubblicazione.\n"
        "- /listblacklist per vedere la blacklist.\n"
        "- /addblacklist <parola> per aggiungere una parola alla blacklist.\n"
        "- /removeblacklist <parola> per rimuovere una parola dalla blacklist.\n"
    )

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Imposta Canali", callback_data="SET_CHANNELS")],
        [InlineKeyboardButton("Imposta Tag", callback_data="SET_TAGS")],
        [InlineKeyboardButton("Imposta Delay", callback_data="SET_DELAY")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Scegli cosa configurare:", reply_markup=reply_markup)

async def config_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "SET_CHANNELS":
        keyboard = [
            [InlineKeyboardButton("Canale IT", callback_data="SET_CHANNEL_IT")],
            [InlineKeyboardButton("Canale ES", callback_data="SET_CHANNEL_ES")],
            [InlineKeyboardButton("Canale DE", callback_data="SET_CHANNEL_DE")],
            [InlineKeyboardButton("Canale FR", callback_data="SET_CHANNEL_FR")]
        ]
        await query.message.reply_text("Seleziona il canale che vuoi impostare:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "SET_TAGS":
        keyboard = [
            [InlineKeyboardButton("Tag IT", callback_data="SET_TAG_IT")],
            [InlineKeyboardButton("Tag ES", callback_data="SET_TAG_ES")],
            [InlineKeyboardButton("Tag DE", callback_data="SET_TAG_DE")],
            [InlineKeyboardButton("Tag FR", callback_data="SET_TAG_FR")]
        ]
        await query.message.reply_text("Seleziona per quale Paese vuoi impostare i tag:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "SET_DELAY":
        await query.message.reply_text("Inserisci il delay di pubblicazione in secondi:", reply_markup=ForceReply(selective=True))
        context.user_data["waiting_for_delay"] = True

    elif query.data.startswith("SET_CHANNEL_"):
        country = query.data.split("_")[-1]
        context.user_data["waiting_for_channel"] = country
        await query.message.reply_text(f"Inserisci il Channel ID per {country} (es: -1001234567890):", reply_markup=ForceReply(selective=True))

    elif query.data.startswith("SET_TAG_"):
        country = query.data.split("_")[-1]
        context.user_data["waiting_for_tag"] = country
        await query.message.reply_text(f"Inserisci i tag per {country}, separati da virgola (es: tag01-21, tag02-21):", reply_markup=ForceReply(selective=True))

async def reply_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if context.user_data.get("waiting_for_delay"):
        try:
            new_delay = int(text)
            user_config["publish_delay"] = new_delay
            save_config(user_config)
            await update.message.reply_text(f"Delay di pubblicazione impostato a {new_delay} secondi.")
        except ValueError:
            await update.message.reply_text("Formato non valido. Riprova usando un numero intero.")
        finally:
            context.user_data["waiting_for_delay"] = False

    elif context.user_data.get("waiting_for_channel"):
        country = context.user_data["waiting_for_channel"]
        user_config["channel_ids"][country] = text
        save_config(user_config)
        await update.message.reply_text(f"Channel ID per {country} impostato a: {text}")
        context.user_data["waiting_for_channel"] = None

    elif context.user_data.get("waiting_for_tag"):
        country = context.user_data["waiting_for_tag"]
        tags_list = [t.strip() for t in text.split(",") if t.strip()]
        user_config["tags"][country] = tags_list
        user_config["tag_indices"][country] = 0
        save_config(user_config)
        await update.message.reply_text(f"Tag per {country} impostati a: {tags_list}")
        context.user_data["waiting_for_tag"] = None

async def pubblica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Avvio della pubblicazione continua per tutti i paesi...")
    application = context.application

    if hasattr(application, 'publishing_tasks') and application.publishing_tasks:
        await update.message.reply_text("La pubblicazione continua è già in esecuzione.")
        return

    tasks = [
        asyncio.create_task(publish_continuously(application, "IT")),
        asyncio.create_task(publish_continuously(application, "ES")),
        asyncio.create_task(publish_continuously(application, "DE")),
        asyncio.create_task(publish_continuously(application, "FR"))
    ]
    application.publishing_tasks = tasks

async def ferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    application = context.application
    if hasattr(application, 'publishing_tasks') and application.publishing_tasks:
        for task in application.publishing_tasks:
            task.cancel()
        application.publishing_tasks = []
        await update.message.reply_text("Pubblicazione fermata.")
    else:
        await update.message.reply_text("Non ci sono pubblicazioni in corso.")

async def listblacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_blacklist = user_config.get("blacklist_words", [])
    if not current_blacklist:
        msg = "La blacklist è vuota."
    else:
        msg = "Parole nella blacklist:\n" + "\n".join(f"- {w}" for w in current_blacklist)
    await update.message.reply_text(msg)

async def addblacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Devi specificare una parola o frase da blacklistare.\nEsempio: /addblacklist iphone")
        return

    new_word = " ".join(context.args).strip()
    if not new_word:
        await update.message.reply_text("Parola/frase non valida.")
        return

    current_blacklist = user_config.get("blacklist_words", [])
    if new_word.lower() in [bw.lower() for bw in current_blacklist]:
        await update.message.reply_text(f'La parola/frase "{new_word}" è già in blacklist.')
        return

    current_blacklist.append(new_word)
    user_config["blacklist_words"] = current_blacklist
    save_config(user_config)
    await update.message.reply_text(f'La parola/frase "{new_word}" è stata aggiunta alla blacklist.')

async def removeblacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Devi specificare la parola o frase da rimuovere.\nEsempio: /removeblacklist iphone")
        return

    word_to_remove = " ".join(context.args).strip()
    current_blacklist = user_config.get("blacklist_words", [])
    lowered = [bw.lower() for bw in current_blacklist]

    if word_to_remove.lower() not in lowered:
        await update.message.reply_text(f'La parola/frase "{word_to_remove}" non è presente in blacklist.')
        return

    idx = lowered.index(word_to_remove.lower())
    removed = current_blacklist.pop(idx)
    user_config["blacklist_words"] = current_blacklist
    save_config(user_config)
    await update.message.reply_text(f'La parola/frase "{removed}" è stata rimossa dalla blacklist.')

def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    logging.info("Avvio del bot Telegram...")

    global user_config
    user_config = load_config()

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("config", config_command))
    application.add_handler(CommandHandler("pubblica", pubblica))
    application.add_handler(CommandHandler("ferma", ferma))
    application.add_handler(CommandHandler("listblacklist", listblacklist_command))
    application.add_handler(CommandHandler("addblacklist", addblacklist_command))
    application.add_handler(CommandHandler("removeblacklist", removeblacklist_command))
    application.add_handler(CallbackQueryHandler(config_callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_message_handler))

    application.run_polling()

if __name__ == "__main__":
    main()
