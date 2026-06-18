#!/usr/bin/env python3
"""
Bara Signal Q&A Bot
Telegram group bot: member tanya, AI jawab dengan analisis crypto real-time.
Stack: Flask + Groq (Llama 3.1 70B) + CoinGecko
"""

import os
import re
import requests
import threading
from flask import Flask, request, jsonify
from groq import Groq
from datetime import datetime, timezone

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")

groq_client = Groq(api_key=GROQ_API_KEY)

# ─── COIN MAP ─────────────────────────────────────────────────────────────────

COIN_MAP = {
    "btc": "bitcoin",       "bitcoin": "bitcoin",
    "eth": "ethereum",      "ethereum": "ethereum",
    "sol": "solana",        "solana": "solana",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "avax": "avalanche-2",
    "dot": "polkadot",
    "link": "chainlink",
    "matic": "matic-network", "pol": "matic-network",
    "uni": "uniswap",
    "atom": "cosmos",
    "ltc": "litecoin",
    "near": "near",
    "trx": "tron",
    "xlm": "stellar",
    "zec": "zcash",
    "sui": "sui",
    "apt": "aptos",
    "op": "optimism",
    "arb": "arbitrum",
    "pepe": "pepe",
    "shib": "shiba-inu",
    "ton": "the-open-network",
    "inj": "injective-protocol",
    "sei": "sei-network",
    "tia": "celestia",
    "wif": "dogwifcoin",
    "bonk": "bonk",
    "hype": "hyperliquid",
    "jup": "jupiter-exchange-solana",
    "fet": "fetch-ai",
    "rndr": "render-token",   "render": "render-token",
    "grt": "the-graph",
    "aave": "aave",
    "fil": "filecoin",
    "icp": "internet-computer",
    "algo": "algorand",
    "xtz": "tezos",
    "sand": "the-sandbox",
    "mana": "decentraland",
    "crv": "curve-dao-token",
    "mkr": "maker",
    "snx": "havven",
    "ldo": "lido-dao",
    "ape": "apecoin",
    "gmt": "stepn",
    "axs": "axie-infinity",
    "rune": "thorchain",
    "kas": "kaspa",
    "tao": "bittensor",
    "wld": "worldcoin-wld",
    "pyth": "pyth-network",
    "w": "wormhole",
    "strk": "starknet",
    "zk": "zksync",
    "not": "notcoin",
    "eigen": "eigenlayer",
}

TRIGGER_WORDS = [
    "analisis", "analisa", "setup", "gimana", "bagaimana", "signal",
    "entry", "target", "tp", "sl", "long", "short", "beli", "jual",
    "pump", "dump", "prediksi", "outlook", "review", "chart",
    "posisi", "rekomendasi", "rekomen", "masuk", "keluar", "hold",
    "momentum", "trend", "support", "resistance", "breakout", "breakdown",
]

# ─── UTILS ────────────────────────────────────────────────────────────────────

def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def detect_coin(text):
    """Deteksi coin yang disebutkan dalam pesan."""
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    for word in words:
        if word in COIN_MAP:
            return word, COIN_MAP[word]
    return None, None

def is_triggered(text):
    """Cek apakah pesan perlu direspon bot."""
    text_lower = text.lower()
    # Ada coin yang disebut + trigger word, atau ada pertanyaan langsung
    has_coin    = any(w in text_lower for w in COIN_MAP)
    has_trigger = any(w in text_lower for w in TRIGGER_WORDS)
    has_command = text_lower.startswith("/")
    return has_command or (has_coin and has_trigger) or has_coin

# ─── DATA FETCHER ─────────────────────────────────────────────────────────────

def fetch_coin_data(coin_id):
    """Ambil data lengkap dari CoinGecko."""
    url = (
        f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        f"?localization=false&tickers=false&community_data=false&developer_data=false"
    )
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        d = r.json()
        m = d.get("market_data", {})
        return {
            "name"       : d.get("name", coin_id),
            "symbol"     : d.get("symbol", "").upper(),
            "price"      : m.get("current_price", {}).get("usd", 0),
            "ath"        : m.get("ath", {}).get("usd", 0),
            "ath_change" : m.get("ath_change_percentage", {}).get("usd", 0),
            "atl"        : m.get("atl", {}).get("usd", 0),
            "h1"         : m.get("price_change_percentage_1h_in_currency", {}).get("usd", 0),
            "h24"        : m.get("price_change_percentage_24h", 0),
            "h7d"        : m.get("price_change_percentage_7d", 0),
            "h30d"       : m.get("price_change_percentage_30d", 0),
            "volume"     : m.get("total_volume", {}).get("usd", 0),
            "mcap"       : m.get("market_cap", {}).get("usd", 0),
            "high24"     : m.get("high_24h", {}).get("usd", 0),
            "low24"      : m.get("low_24h", {}).get("usd", 0),
            "rank"       : d.get("market_cap_rank", 0),
            "supply"     : m.get("circulating_supply", 0),
            "max_supply" : m.get("max_supply", 0),
            "fdv"        : m.get("fully_diluted_valuation", {}).get("usd", 0),
            "desc"       : d.get("description", {}).get("en", "")[:300],
        }
    except Exception as e:
        print(f"[CoinGecko ERR] {e}")
        return None

def fetch_global():
    """Kondisi global market."""
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        d = r.json().get("data", {})
        return {
            "mc_change_24h": d.get("market_cap_change_percentage_24h_usd", 0),
            "btc_dom"      : d.get("market_cap_percentage", {}).get("btc", 0),
            "total_mc"     : d.get("total_market_cap", {}).get("usd", 0),
        }
    except:
        return None

def fetch_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=8)
        d = r.json()
        return {"value": int(d["data"][0]["value"]), "label": d["data"][0]["value_classification"]}
    except:
        return None

# ─── AI ANALYST ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Kamu adalah Bara Signal AI, analis trading crypto profesional.

Saat menjawab pertanyaan tentang suatu coin:
1. Berikan ringkasan kondisi harga saat ini
2. Analisis teknikal: trend, momentum, level penting
3. Konteks market: apakah market sedang risk-on atau risk-off
4. Rekomendasi posisi: LONG / SHORT / WAIT / ACCUMULATE
5. Setup trading:
   - Entry Zone (spesifik dalam USD)
   - Stop Loss (dengan persentase, R/R minimum 1:2.5)
   - TP1, TP2, TP3 (dengan persentase)
   - Leverage yang disarankan (konservatif)
6. Confidence score (0-100)
7. Key risks yang perlu diwaspadai

Gaya bahasa: Bahasa Indonesia, casual tapi profesional.
Gunakan emoji untuk visual. Singkat tapi lengkap.
Selalu tutup dengan: "⚠️ BUKAN SARAN FINANSIAL — DYOR"

Format output yang rapi dan mudah dibaca di Telegram."""

def analyze_coin(coin_data, global_data, fg, user_question):
    """Generate AI analysis menggunakan Groq."""
    if not coin_data:
        return "Maaf, data coin tidak ditemukan. Coba ketik simbol yang benar (contoh: BTC, ETH, SOL)"

    def fmt(v):
        if v >= 1e9:  return f"${v/1e9:.2f}B"
        if v >= 1e6:  return f"${v/1e6:.1f}M"
        if v >= 1:    return f"${v:,.2f}"
        return f"${v:.6f}"

    def pct(v): return f"{'+'if v>=0 else''}{v:.2f}%"

    ctx = f"""
DATA REAL-TIME {coin_data['name']} ({coin_data['symbol']}) — {ts()}

HARGA & PERGERAKAN:
- Harga saat ini : {fmt(coin_data['price'])}
- 1 Jam          : {pct(coin_data['h1'])}
- 24 Jam         : {pct(coin_data['h24'])}
- 7 Hari         : {pct(coin_data['h7d'])}
- 30 Hari        : {pct(coin_data['h30d'])}
- High 24h       : {fmt(coin_data['high24'])}
- Low 24h        : {fmt(coin_data['low24'])}

MARKET INFO:
- Volume 24h     : {fmt(coin_data['volume'])}
- Market Cap     : {fmt(coin_data['mcap'])}
- Rank           : #{coin_data['rank']}
- ATH            : {fmt(coin_data['ath'])} ({pct(coin_data['ath_change'])} dari ATH)

KONDISI MARKET GLOBAL:
- Total Market Cap Change 24h : {pct(global_data['mc_change_24h']) if global_data else 'N/A'}
- BTC Dominance              : {global_data['btc_dom']:.1f}% if global_data else 'N/A'
- Fear & Greed Index         : {fg['value']}/100 — {fg['label'] if fg else 'N/A'}

PERTANYAAN USER: {user_question}

Berikan analisis lengkap berdasarkan data di atas.
"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": ctx},
            ],
            temperature=0.7,
            max_tokens=800,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[Groq ERR] {e}")
        return f"Error AI: {e}"

# ─── TELEGRAM SENDER ──────────────────────────────────────────────────────────

def send_message(chat_id, text, reply_to=None):
    payload = {
        "chat_id": chat_id,
        "text"   : text[:4000],  # Telegram max 4096 chars
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json=payload, timeout=15,
        )
    except Exception as e:
        print(f"[TG ERR] {e}")

def send_typing(chat_id):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=5,
        )
    except:
        pass

# ─── WEBHOOK HANDLER ──────────────────────────────────────────────────────────

def process_message(chat_id, msg_id, text, username):
    """Proses pesan di background thread."""
    try:
        # Handle /start
        if text.startswith("/start"):
            send_message(chat_id,
                "Halo! Saya Bara Signal AI\n\n"
                "Tanya apa saja tentang crypto:\n"
                "- analisis BTC\n"
                "- setup untuk ETH sekarang\n"
                "- gimana kondisi SOL\n"
                "- rekomendasi DOGE\n\n"
                "Saya berikan analisis real-time + trade setup lengkap!",
                reply_to=msg_id
            )
            return

        # Handle /help
        if text.startswith("/help"):
            send_message(chat_id,
                "Cara Pakai Bara Signal AI:\n\n"
                "Sebut nama coin + pertanyaan:\n"
                "- analisis BTC\n"
                "- setup long ETH\n"
                "- gimana SOL hari ini\n"
                "- BTC mau pump atau dump?\n"
                "- entry point DOGE\n\n"
                "Coin: BTC ETH SOL BNB XRP ADA DOGE AVAX DOT LINK MATIC UNI ATOM LTC NEAR TRX XLM ZEC SUI APT dan banyak lagi!\n\n"
                "BUKAN SARAN FINANSIAL - DYOR",
                reply_to=msg_id
            )
            return

        if not is_triggered(text):
            return

        sym, coin_id = detect_coin(text)
        if not coin_id:
            send_message(chat_id,
                "Coin tidak dikenali.\nContoh: analisis BTC, setup ETH, gimana SOL",
                reply_to=msg_id
            )
            return

        send_typing(chat_id)

        # Fetch semua data parallel
        results = {}
        def do_coin():   results["coin"]   = fetch_coin_data(coin_id)
        def do_global(): results["global"] = fetch_global()
        def do_fg():     results["fg"]     = fetch_fear_greed()

        threads = [threading.Thread(target=f) for f in [do_coin, do_global, do_fg]]
        for t in threads: t.start()
        for t in threads: t.join(timeout=8)

        coin_data   = results.get("coin")
        global_data = results.get("global")
        fg          = results.get("fg")

        if not coin_data:
            send_message(chat_id, f"Gagal fetch data {sym.upper()}. Coba lagi.", reply_to=msg_id)
            return

        send_typing(chat_id)
        analysis = analyze_coin(coin_data, global_data, fg, text)
        send_message(chat_id, analysis, reply_to=msg_id)
        print(f"[DONE] {username} -> {sym.upper()}")

    except Exception as e:
        print(f"[PROCESS ERR] {e}")
        try:
            send_message(chat_id, "Terjadi error, coba lagi.", reply_to=msg_id)
        except:
            pass

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"ok": True})

    msg = data.get("message") or data.get("edited_message")
    if not msg:
        return jsonify({"ok": True})

    chat_id  = msg["chat"]["id"]
    msg_id   = msg["message_id"]
    text     = msg.get("text", "")
    username = msg.get("from", {}).get("first_name", "User")

    if not text:
        return jsonify({"ok": True})

    print(f"[MSG] {username}: {text[:80]}")

    # Proses synchronous — selesaikan dulu baru return 200
    process_message(chat_id, msg_id, text, username)

    return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def index():
    return "Bara Signal Q&A Bot is running! 🚀"

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "bot": "Bara Signal AI"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
