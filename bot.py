import requests
import json
import os
import re
from bs4 import BeautifulSoup
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────
NTFY_URL   = os.environ.get("NTFY_URL")
CACHE_FILE = "prices_cache.json"

URL_LU = "https://www.lesfrontaliers.lu/wp-content/themes/les-frontaliers/carbprices/luxPrices.php"
URL_BE = "https://energiafed.be/fr/prix-maximums"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36"
}

# ─── Scraping Luxembourg ───────────────────────────────────────────
def fetch_lu_prices():
    r = requests.get(URL_LU, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    row = soup.find("tr", class_="Luxembourg")
    if not row:
        raise ValueError("Ligne Luxembourg introuvable")
    cells = row.find_all("td")
    # cells: 0=flag, 1=pays, 2=SP95, 3=SP98, 4=Diesel, 5=date
    return {
        "sp95":   cells[2].text.strip().replace(",", "."),
        "sp98":   cells[3].text.strip().replace(",", "."),
        "diesel": cells[4].text.strip().replace(",", "."),
        "date":   cells[5].text.strip()
    }

# ─── Scraping Belgique ─────────────────────────────────────────────
def fetch_be_prices():
    r = requests.get(URL_BE, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    prices = {}

    # Chercher toutes les tables ou sections contenant les prix
    text = soup.get_text()

    # Patterns pour extraire les prix
    patterns = {
        "sp95":   r"(?:95|E10|euro\s*95)[^\d]*(\d[,\.]\d{3})",
        "sp98":   r"(?:98|E5|euro\s*98)[^\d]*(\d[,\.]\d{3})",
        "diesel": r"(?:diesel|gasoil|go)[^\d]*(\d[,\.]\d{3})",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            prices[key] = match.group(1).replace(",", ".")
        else:
            prices[key] = None

    return prices

# ─── Chargement / Sauvegarde cache ────────────────────────────────
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {"lu": {}, "be": {}}

def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ─── Calcul variation ─────────────────────────────────────────────
def format_variation(old_val, new_val):
    if old_val is None:
        return "🆕 Nouveau"
    try:
        diff = float(new_val) - float(old_val)
        if abs(diff) < 0.001:
            return "⚖️ Stable"
        elif diff < 0:
            return f"📉 Baisse de {abs(diff):.3f}€"
        else:
            return f"📈 Hausse de {abs(diff):.3f}€"
    except:
        return "⚖️ Stable"

def format_price(val):
    try:
        return f"{float(val):.3f}€".replace(".", ",")
    except:
        return str(val)

# ─── Construction du message ──────────────────────────────────────
def build_message(lu_new, be_new, lu_old, be_old, changed_country):
    today = datetime.now().strftime("%d/%m")

    if changed_country == "LU":
        subtitle = "🇱🇺 Le Luxembourg change ses prix !"
    elif changed_country == "BE":
        subtitle = "🇧🇪 La Belgique change ses prix !"
    else:
        subtitle = "🇱🇺🇧🇪 Les deux pays changent leurs prix !"

    fuels = [
        ("🟡", "DIESEL", "diesel"),
        ("🟢", "SP95",   "sp95"),
        ("🔵", "SP98",   "sp98"),
    ]

    lines = [subtitle, ""]

    for emoji, label, key in fuels:
        lu_val = lu_new.get(key)
        be_val = be_new.get(key)

        if lu_val and be_val:
            try:
                if float(lu_val) < float(be_val):
                    trophy = "🏆 Go Lux. !"
                elif float(be_val) < float(lu_val):
                    trophy = "🏆 Go Belgique !"
                else:
                    trophy = "🤝 Égalité !"
            except:
                trophy = ""
        else:
            trophy = ""

        lu_var = format_variation(lu_old.get(key), lu_val)
        be_var = format_variation(be_old.get(key), be_val)

        lines.append(f"{emoji} {label} | {trophy}")
        lines.append(f"🇱🇺 {format_price(lu_val)} ({lu_var})")
        lines.append(f"🇧🇪 {format_price(be_val)} ({be_var})")
        lines.append("")

    return f"⛽️ Alerte Carburants ({today})", "\n".join(lines)

# ─── Envoi notification ntfy ──────────────────────────────────────
def send_notification(title, message):
    if not NTFY_URL:
        print("⚠️  NTFY_URL non défini, pas de notification envoyée")
        print(f"TITRE: {title}")
        print(f"MESSAGE:\n{message}")
        return

    r = requests.post(
        NTFY_URL,
        data=message.encode("utf-8"),
        headers={
            "Title": title.encode("utf-8"),
            "Priority": "high",
            "Tags": "fuelpump",
        },
        timeout=10
    )
    r.raise_for_status()
    print(f"✅ Notification envoyée : {title}")

# ─── Main ──────────────────────────────────────────────────────────
def main():
    print(f"🔍 Vérification des prix - {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    cache = load_cache()
    lu_old = cache.get("lu", {})
    be_old = cache.get("be", {})

    # Fetch nouveaux prix
    try:
        lu_new = fetch_lu_prices()
        print(f"🇱🇺 LU - SP95: {lu_new['sp95']} | SP98: {lu_new['sp98']} | Diesel: {lu_new['diesel']}")
    except Exception as e:
        print(f"❌ Erreur scraping Luxembourg: {e}")
        lu_new = lu_old.copy()

    try:
        be_new = fetch_be_prices()
        print(f"🇧🇪 BE - SP95: {be_new.get('sp95')} | SP98: {be_new.get('sp98')} | Diesel: {be_new.get('diesel')}")
    except Exception as e:
        print(f"❌ Erreur scraping Belgique: {e}")
        be_new = be_old.copy()

    # Détecter changements
    lu_changed = any(lu
