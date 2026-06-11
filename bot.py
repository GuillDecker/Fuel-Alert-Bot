import requests
import json
import os
import re
from bs4 import BeautifulSoup
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────
NTFY_URL   = os.environ.get("NTFY_URL")
CACHE_FILE = "prices_cache.json"

URL_LU = "https://www.petrol.lu/prix-officiels/"
URL_BE = "https://www.energiafed.be/fr/prix-maximums"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36"
}

# ─── Scraping Luxembourg (petrol.lu) ───────────────────────────────
def fetch_lu_prices():
    r = requests.get(URL_LU, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    table = soup.find("div", class_="prices-table")
    if not table:
        raise ValueError("Tableau prices-table introuvable sur petrol.lu")

    rows = table.find("tbody").find_all("tr")
    tvac_row = None
    for row in rows:
        cells = row.find_all("td")
        if cells and cells[-1].text.strip() == "TVAC":
            tvac_row = cells
            break

    if not tvac_row:
        raise ValueError("Ligne TVAC introuvable sur petrol.lu")

    # Colonnes : Date | Super98 | Super95 | Diesel | Gasoil chauff | Gasoil BTS | TVA
    date   = tvac_row[0].text.strip()
    sp98   = tvac_row[1].text.strip().replace(",", ".")
    sp95   = tvac_row[2].text.strip().replace(",", ".")
    diesel = tvac_row[3].text.strip().replace(",", ".")
    mazout = tvac_row[5].text.strip().replace(",", ".")  # Gasoil chauff. BTS (> 1500L)

    return {
        "sp95":   float(sp95),
        "sp98":   float(sp98),
        "diesel": float(diesel),
        "mazout": float(mazout),   # > 1500L
        "date":   date
    }

# ─── Scraping Belgique (energiafed.be / JSON) ──────────────────────
def fetch_be_prices():
    r = requests.get(URL_BE, headers=HEADERS, timeout=15)
    r.raise_for_status()
    raw = r.text

    def extract(name):
        block = re.search(
            r'(\{[^{}]*?"name":"' + re.escape(name) + r'"[^{}]*?\})',
            raw
        )
        if block:
            prijs = re.search(r'"prijs":"([\d.]+)"', block.group(1))
            datum = re.search(r'"datum":"([\d-]+)"', block.group(1))
            if prijs:
                return (
                    float(prijs.group(1)),
                    datum.group(1) if datum else ""
                )
        raise ValueError(f"Prix BE introuvable pour : {name}")

    sp95,   d95   = extract("Essence 95 RON - E5")
    sp98,   d98   = extract("Essence 98 RON - E5")
    diesel, ddie  = extract("Diesel")
    mazout, dmaz  = extract("Gasoil Diesel (application chauffage) (≥ 2000 L)")

    return {
        "sp95":   sp95,
        "sp98":   sp98,
        "diesel": diesel,
        "mazout": mazout,   # ≥ 2000L
        "date":   dmaz
    }

# ─── Cache ─────────────────────────────────────────────────────────
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {"lu": {}, "be": {}}

def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ─── Comparaison & formatage ───────────────────────────────────────
FUELS = ["sp95", "sp98", "diesel", "mazout"]

def diff_label(old, new):
    if old is None:
        return "Nouveau"
    delta = round(new - old, 4)
    if abs(delta) < 0.0001:
        return "⚖️ Stable"
    elif delta > 0:
        return f"📈 Hausse +{delta:.3f}€"
    else:
        return f"📉 Baisse -{abs(delta):.3f}€"

def build_notification(old_lu, new_lu, old_be, new_be):
    today = datetime.now().strftime("%d/%m")

    changed_lu = any(old_lu.get(k) != new_lu[k] for k in FUELS)
    changed_be = any(old_be.get(k) != new_be[k] for k in FUELS)

    if changed_lu and changed_be:
        subtitle = "🇱🇺🇧🇪 Le LU et la BE changent leurs prix !"
    elif changed_lu:
        subtitle = "🇱🇺 Le Luxembourg change ses prix !"
    else:
        subtitle = "🇧🇪 La Belgique change ses prix !"

    title = f"⛽️ Alerte Carburants ({today})"

    lines = [subtitle, ""]

    fuel_display = [
        ("diesel", "🟡 DIESEL"),
        ("sp95",   "🟢 SP95"),
        ("sp98",   "🔵 SP98"),
        ("mazout", "🔥 MAZOUT CHAUFFAGE"),
    ]

    for fuel_key, label in fuel_display:
        lu_val = new_lu[fuel_key]
        be_val = new_be[fuel_key]

        if lu_val < be_val:
            trophy = "🏆 Go Lux. !"
        elif be_val < lu_val:
            trophy = "🏆 Go Belgique !"
        else:
            trophy = "🤝 Égalité !"

        lines.append(f"{label} | {trophy}")
        lines.append(f"🇱🇺 {lu_val:.3f}€ ({diff_label(old_lu.get(fuel_key), lu_val)})")
        lines.append(f"🇧🇪 {be_val:.3f}€ ({diff_label(old_be.get(fuel_key), be_val)})")
        lines.append("")

    return title, "\n".join(lines).strip()

# ─── Envoi ntfy ────────────────────────────────────────────────────
def send_notification(title, message):
    if not NTFY_URL:
        print("NTFY_URL non defini — notif non envoyee.")
        print(f"TITRE   : {title}")
        print(f"MESSAGE :\n{message}")
        return

    try:
        response = requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title":    title.encode("utf-8"),
                "Priority": "high",
                "Tags":     "fuelpump,rotating_light"
            },
            timeout=10
        )
        response.raise_for_status()
        print(f"Notification envoyee : {title} (Status: {response.status_code})")
    except Exception as e:
        print(f"Erreur lors de l'envoi ntfy : {e}")

# ─── Main ──────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Verification des prix...")

    try:
        new_lu = fetch_lu_prices()
        print(f"  LU -> {new_lu}")
    except Exception as e:
        print(f"Erreur scraping LU : {e}")
        return

    try:
        new_be = fetch_be_prices()
        print(f"  BE -> {new_be}")
    except Exception as e:
        print(f"Erreur scraping BE : {e}")
        return

    cache  = load_cache()
    old_lu = cache.get("lu", {})
    old_be = cache.get("be", {})

    lu_changed = any(old_lu.get(k) != new_lu[k] for k in FUELS)
    be_changed = any(old_be.get(k) != new_be[k] for k in FUELS)

    if not lu_changed and not be_changed:
        print("  Aucun changement detecte.")
        return

    print(f"  Changement detecte ! LU={lu_changed} BE={be_changed}")

    title, message = build_notification(old_lu, new_lu, old_be, new_be)
    send_notification(title, message)

    cache["lu"] = new_lu
    cache["be"] = new_be
    save_cache(cache)
    print("  Cache mis a jour.")

if __name__ == "__main__":
    main()
