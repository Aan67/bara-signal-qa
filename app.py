#!/usr/bin/env python3
"""
Bara Signal Q&A Bot
Telegram group bot: member tanya, AI jawab dengan analisis crypto real-time.
Stack: Flask + Groq (Llama 3.1 70B) + CoinGecko
"""

import os
import re
import json
import time
import urllib.request
import urllib.parse
import requests
import threading
from flask import Flask, request, jsonify
from groq import Groq
from datetime import datetime, timezone

# ─── CACHE (hindari rate limit CoinGecko) ────────────────────────────────────
COIN_CACHE  = {}  # {coin_id: {"data": {...}, "expires": float}}
GLOBAL_CACHE = {"data": None, "expires": 0}
FG_CACHE     = {"data": None, "expires": 0}
CACHE_TTL   = 180  # 3 menit

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")

groq_client = Groq(api_key=GROQ_API_KEY)

# ─── CONVERSATION HISTORY ─────────────────────────────────────────────────────
# Format: {chat_id: {"coin_id": str, "coin_data": dict, "history": [...]}}
CONV = {}
MAX_HISTORY = 8  # maksimal 4 tanya-jawab tersimpan

# ─── COIN MAP ─────────────────────────────────────────────────────────────────

COIN_MAP = {
    # Major
    "btc": "bitcoin",           "bitcoin": "bitcoin",
    "eth": "ethereum",          "ethereum": "ethereum",
    "sol": "solana",            "solana": "solana",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "avax": "avalanche-2",
    "dot": "polkadot",
    "link": "chainlink",
    "matic": "matic-network",   "pol": "matic-network",
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
    "ton": "the-open-network",
    "inj": "injective-protocol",
    "sei": "sei-network",
    "tia": "celestia",
    "kas": "kaspa",
    "tao": "bittensor",
    # DeFi
    "aave": "aave",
    "crv": "curve-dao-token",
    "mkr": "maker",
    "snx": "havven",
    "ldo": "lido-dao",
    "grt": "the-graph",
    "rune": "thorchain",
    "jup": "jupiter-exchange-solana",
    "ray": "raydium",
    "gmx": "gmx",
    "dydx": "dydx",
    "pendle": "pendle",
    "ethfi": "ether-fi",
    "ena": "ethena",
    "mnt": "mantle",            "mantle": "mantle",
    "lista": "lista-dao",
    # AI / Tech
    "fet": "fetch-ai",
    "rndr": "render-token",     "render": "render-token",
    "wld": "worldcoin-wld",     "worldcoin": "worldcoin-wld",
    "play": "playsout",
    "virtual": "virtual-protocol",
    "ai16z": "ai16z",
    "aixbt": "aixbt-by-virtuals",
    "arc": "arc-agi",
    # Gaming / Metaverse
    "sand": "the-sandbox",
    "mana": "decentraland",
    "axs": "axie-infinity",
    "gmt": "stepn",
    "ape": "apecoin",
    "pixel": "pixels",
    "ygg": "yield-guild-games",
    # Layer 2 / Infrastructure
    "pyth": "pyth-network",
    "w": "wormhole",
    "strk": "starknet",
    "zk": "zksync",
    "eigen": "eigenlayer",
    "alt": "altlayer",
    "dym": "dymension",
    "zro": "layerzero",
    "io": "io-net",
    "saga": "saga-2",
    # Meme coins
    "pepe": "pepe",
    "shib": "shiba-inu",
    "wif": "dogwifcoin",
    "bonk": "bonk",
    "floki": "floki",
    "not": "notcoin",
    "popcat": "popcat",
    "brett": "based-brett",
    "mog": "mog-coin",
    "turbo": "turbo",
    "pnut": "peanut-the-squirrel",
    "trump": "official-trump",
    "bome": "book-of-meme",
    "mew": "cat-in-a-dogs-world",
    "fartcoin": "fartcoin",
    "pengu": "pudgy-penguins",
    "griffain": "griffain",
    # Other popular
    "hype": "hyperliquid",
    "fil": "filecoin",
    "icp": "internet-computer",
    "algo": "algorand",
    "xtz": "tezos",
    "ftm": "fantom",            "sonic": "sonic-3",
    "zil": "zilliqa",
    "vet": "vechain",
    "theta": "theta-token",
    "hbar": "hedera-hashgraph",
    "egld": "elrond-erd-2",
    "flow": "flow",
    "iota": "iota",
    "xmr": "monero",
    "gala": "gala",
    "imx": "immutable-x",
    "blur": "blur",
    "magma": "magma-finance",  "magma finance": "magma-finance",
    "zeta": "zetachain",
    "omni": "omni-network",
    "taiko": "taiko",
    "mode": "mode",
    "merlin": "merlin-chain",
    "banana": "banana-gun",
    "cookie": "cookie",
    "griffain": "griffain",
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

def search_coin_dynamic(query):
    """Cari coin di CoinGecko kalau tidak ada di COIN_MAP."""
    try:
        url = f"https://api.coingecko.com/api/v3/search?query={query}"
        d = get(url, timeout=6)
        if d and d.get("coins") and len(d["coins"]) > 0:
            coin = d["coins"][0]
            return coin["id"], coin["symbol"].lower()
    except:
        pass
    return None, None

SKIP_WORDS = {
    "yang","dan","atau","ini","itu","mau","bisa","ada","tidak","gimana",
    "setup","analisis","analisa","bagaimana","kapan","kenapa","berapa",
    "apa","siapa","dimana","lebih","kurang","sangat","sudah","belum",
    "akan","sedang","punya","buat","dari","untuk","dengan","pada","di",
    "ke","kamu","aku","saya","bot","harga","pasar","market","coin","token",
    "crypto","trading","trader","invest","the","and","or","is","are","was",
    "how","what","when","why","where","price","buy","sell","good","bad",
}

def detect_coin(text, last_coin_id=None):
    """Deteksi coin. Kalau tidak ada di pesan, pakai coin terakhir dari history."""
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)

    # Cek static map dulu
    for word in words:
        if word in COIN_MAP:
            return word, COIN_MAP[word]

    # Dynamic search CoinGecko untuk kata yang berpotensi jadi coin
    for word in words:
        if len(word) >= 2 and word not in SKIP_WORDS and word not in TRIGGER_WORDS:
            coin_id, sym = search_coin_dynamic(word)
            if coin_id:
                COIN_MAP[word] = coin_id
                return word, coin_id

    # Tidak ada coin di pesan → pakai coin terakhir dari conversation
    if last_coin_id:
        return None, last_coin_id

    return None, None

def is_triggered(text, has_history=False):
    """Cek apakah pesan perlu direspon bot."""
    text_lower = text.lower()
    has_coin    = any(w in text_lower for w in COIN_MAP)
    has_trigger = any(w in text_lower for w in TRIGGER_WORDS)
    has_command = text_lower.startswith("/")
    # Jika ada conversation history, respon semua pertanyaan lanjutan
    return has_command or has_coin or has_trigger or has_history

# ─── DATA FETCHER ─────────────────────────────────────────────────────────────

def fetch_coin_data(coin_id):
    """Ambil data dari CoinGecko dengan caching 3 menit."""
    now = time.time()

    # Cek cache dulu
    if coin_id in COIN_CACHE and COIN_CACHE[coin_id]["expires"] > now:
        print(f"[CACHE] {coin_id}")
        return COIN_CACHE[coin_id]["data"]

    url = (
        f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        f"?localization=false&tickers=false&community_data=false&developer_data=false"
    )
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        d = r.json()
        m = d.get("market_data", {})
        result = {
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
        COIN_CACHE[coin_id] = {"data": result, "expires": now + CACHE_TTL}
        return result
    except Exception as e:
        print(f"[CoinGecko ERR] {coin_id}: {e}")
        # Kalau ada cache lama, pakai itu daripada error
        if coin_id in COIN_CACHE:
            print(f"[CACHE STALE] Using old cache for {coin_id}")
            return COIN_CACHE[coin_id]["data"]
        # Fallback search
        try:
            sr = requests.get(
                f"https://api.coingecko.com/api/v3/search?query={coin_id}",
                timeout=8, headers={"User-Agent": "Mozilla/5.0"}
            )
            coins = sr.json().get("coins", [])
            if coins:
                new_id = coins[0]["id"]
                if new_id != coin_id:
                    return fetch_coin_data(new_id)
        except:
            pass
        return None

def fetch_global():
    now = time.time()
    if GLOBAL_CACHE["expires"] > now and GLOBAL_CACHE["data"]:
        return GLOBAL_CACHE["data"]
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        d = r.json().get("data", {})
        result = {
            "mc_change_24h": d.get("market_cap_change_percentage_24h_usd", 0),
            "btc_dom"      : d.get("market_cap_percentage", {}).get("btc", 0),
            "total_mc"     : d.get("total_market_cap", {}).get("usd", 0),
        }
        GLOBAL_CACHE["data"]    = result
        GLOBAL_CACHE["expires"] = now + CACHE_TTL
        return result
    except:
        return GLOBAL_CACHE.get("data")

def fetch_fear_greed():
    now = time.time()
    if FG_CACHE["expires"] > now and FG_CACHE["data"]:
        return FG_CACHE["data"]
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=8)
        d = r.json()
        result = {"value": int(d["data"][0]["value"]), "label": d["data"][0]["value_classification"]}
        FG_CACHE["data"]    = result
        FG_CACHE["expires"] = now + CACHE_TTL
        return result
    except:
        return FG_CACHE.get("data")

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

def analyze_coin(coin_data, global_data, fg, user_question, history=None):
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
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Tambah history percakapan jika ada
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": ctx})

        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.7,
            max_tokens=800,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[Groq ERR] {e}")
        return f"Error AI: {e}"

# ─── TELEGRAM SENDER ──────────────────────────────────────────────────────────

def tg_post(method, payload):
    """Kirim request ke Telegram API pakai urllib (bypass SSL issue Vercel)."""
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode())
            print(f"[TG {method}] ok={result.get('ok')}")
            return result
    except Exception as e:
        print(f"[TG ERR {method}] {e}")
        return None

def send_message(chat_id, text, reply_to=None):
    payload = {"chat_id": chat_id, "text": text[:4000]}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    return tg_post("sendMessage", payload)

def send_typing(chat_id):
    pass  # disabled - proxy hanya izin 1 TG call per request

# ─── WEBHOOK HANDLER ──────────────────────────────────────────────────────────

def process_message(chat_id, msg_id, text, username):
    """Proses pesan dengan conversation history."""
    try:
        # Commands
        if text.startswith("/test"):
            send_message(chat_id, "Bot aktif!")
            return

        if text.startswith("/start"):
            CONV.pop(chat_id, None)  # reset history
            send_message(chat_id,
                "Halo! Saya Bara Signal AI\n\n"
                "Tanya tentang coin apapun:\n"
                "- analisis BTC\n"
                "- setup ETH sekarang\n"
                "- gimana SOL?\n"
                "- entry DOGE?\n\n"
                "Saya support SEMUA coin di CoinGecko!\n"
                "Bisa tanya lanjutan juga (bot ingat konteks).\n\n"
                "BUKAN SARAN FINANSIAL - DYOR"
            )
            return

        if text.startswith("/reset"):
            CONV.pop(chat_id, None)
            send_message(chat_id, "Percakapan direset. Mulai topik baru!")
            return

        if text.startswith("/help"):
            send_message(chat_id,
                "Cara pakai:\n\n"
                "1. Sebut nama coin: analisis BTC\n"
                "2. Tanya lanjutan: kapan entry? target TP?\n"
                "3. Ganti coin: sekarang analisis ETH\n"
                "4. Reset: /reset\n\n"
                "Support SEMUA coin — kalau tidak dikenal, bot cari otomatis.\n"
                "BUKAN SARAN FINANSIAL - DYOR"
            )
            return

        # Ambil conversation state
        conv = CONV.get(chat_id, {"coin_id": None, "coin_name": None, "history": []})
        has_history = len(conv["history"]) > 0

        if not is_triggered(text, has_history):
            return

        # Deteksi coin (dengan fallback ke coin terakhir)
        sym, coin_id = detect_coin(text, last_coin_id=conv["coin_id"])

        if not coin_id:
            send_message(chat_id,
                "Coin tidak dikenali. Contoh: analisis BTC, setup ETH, gimana SOL"
            )
            return

        # Fetch data
        coin_data   = fetch_coin_data(coin_id)
        global_data = fetch_global()
        fg          = fetch_fear_greed()

        if not coin_data:
            # Coba dynamic search sebagai last resort
            new_id, _ = search_coin_dynamic(sym or text.split()[-1])
            if new_id and new_id != coin_id:
                coin_data = fetch_coin_data(new_id)
                if coin_data:
                    coin_id = new_id

        if not coin_data:
            send_message(chat_id,
                f"Data tidak ditemukan untuk '{sym or text}'.\n"
                "Coba ketik nama/simbol lengkapnya."
            )
            return

        # Generate AI response dengan history
        analysis = analyze_coin(coin_data, global_data, fg, text, conv["history"])

        # Update conversation history
        conv["coin_id"]   = coin_id
        conv["coin_name"] = coin_data["name"]
        conv["history"].append({"role": "user",      "content": text})
        conv["history"].append({"role": "assistant",  "content": analysis})

        # Batasi history
        if len(conv["history"]) > MAX_HISTORY:
            conv["history"] = conv["history"][-MAX_HISTORY:]

        CONV[chat_id] = conv

        send_message(chat_id, analysis)
        print(f"[DONE] {username} -> {coin_data['name']}")

    except Exception as e:
        print(f"[PROCESS ERR] {e}")
        try:
            send_message(chat_id, "Terjadi error, coba lagi.")
        except:
            pass

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True, silent=True)
        print(f"[WEBHOOK] Received: {str(data)[:200]}")

        if not data:
            print("[WEBHOOK] No data received")
            return jsonify({"ok": True})

        msg = data.get("message") or data.get("edited_message")
        if not msg:
            return jsonify({"ok": True})

        chat_id  = msg["chat"]["id"]
        msg_id   = msg["message_id"]
        text     = msg.get("text", "")
        username = msg.get("from", {}).get("first_name", "User")

        print(f"[MSG] chat={chat_id} user={username} text={text[:80]}")

        if not text:
            return jsonify({"ok": True})

        process_message(chat_id, msg_id, text, username)

    except Exception as e:
        print(f"[WEBHOOK ERR] {e}")

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
