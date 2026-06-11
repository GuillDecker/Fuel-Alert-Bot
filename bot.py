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
URL_BE = "https://carbu.com/belgique/prixmaximum"
URL_BE_MAZOUT = "https://carbu.com/belgique/prixOfficielMazout"

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
        "mazout": float(mazout),
        "date":   date
    }

# ─── Scraping Belgique - Mazout (carbu.com) ────────────────────────
def fetch_be_mazout():
    """Récupère le prix du mazout depuis la page dédiée"""
    try:
        r = requests.get(URL_BE_MAZOUT, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Chercher les cellules de prix
        price_cells = soup.find_all("td", class_="price")
        if price_cells:
            price_text = price_cells[0].text.strip().replace(",", ".").replace("€/l", "").strip()
            return float(price_text)
    except Exception as e:
        print(f"⚠️ Mazout non trouvé : {e}")
    
    return 1.0  # Valeur par défaut si erreur

# ─── Scraping Belgique - Carburants (carbu.com) ─────────────────────
def fetch_be_prices():
    r = requests.get(URL_BE, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    prices = {}

    # Chercher tous les TD avec class "price" et leurs labels
    price_cells = soup.find_all("td", class_="price")
    fuel_cells = soup.find_all("td", class_="officialPriceBe_col1")

    if not price_cells or not fuel_cells:
        raise ValueError("Tableau de prix introuvable sur carbu.com")

    # Parcourir les paires fuel/price
    for fuel_cell, price_cell in zip(fuel_cells, price_cells):
        fuel_name = fuel_cell.text.strip().lower()
        price_text = price_cell.text.strip().replace(",", ".").replace("€/l", "").strip()

        try:
            price = float(price_text)
        except ValueError:
            continue

        # Mapper les noms
        if "diesel" in fuel_name:
            prices["diesel"] = price
        elif "95" in fuel_name or "e10" in fuel_name:
            prices["sp95"] = price
        elif "98" in fuel_name:
            prices["sp98"] = price

    # Vérifier qu'on a au moins 3 carburants
    if len(prices) < 3:
        raise ValueError(f"Pas assez de carburants trouvés : {prices}")

    # Récupérer le mazout séparément
    prices["mazout"] = fetch_be_mazout()

    return {
        "sp95":   prices.get("sp95", 0),
        "sp98":   prices.get("sp98", 0),
        "diesel": prices.get("diesel", 0),
        "mazout": prices.get("mazout", 1.0),
        "date":   datetime.now().strftime("%Y-%m-%d")
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
    delta = new - old
    if abs(delta) < 0.0001:
        return "⚖️ Stable"
    elif delta > 0:
        return f"📈 Hausse +{delta:.4f}€"
    else:
        return f"📉 Baisse {delta:.4f}€"

def get_price_change_direction(old, new):
    """Retourne 'hausse', 'baisse' ou 'stable'"""
    if old is None:
        return None
    delta = new - old
    if abs(delta) < 0.0001:
        return "stable"
    elif delta > 0:
        return "hausse"
    else:
        return "baisse"

def build_dynamic_subtitle(old_lu, new_lu, old_be, new_be):
    """Construit le sous-titre en fonction des changements"""
    
    # Déterminer les changements pour chaque pays
    lu_changes = {}
    be_changes = {}
    
    for fuel in FUELS:
        lu_direction = get_price_change_direction(old_lu.get(fuel), new_lu[fuel])
        be_direction = get_price_change_direction(old_be.get(fuel), new_be[fuel])
        
        if lu_direction:
            lu_changes[fuel] = lu_direction
        if be_direction:
            be_changes[fuel] = be_direction
    
    # Si pas de changement détecté (cache vide au premier lancement)
    if not lu_changes and not be_changes:
        return "⛽️ Mise à jour des prix"
    
    # Analyser les tendances
    lu_hausse = sum(1 for v in lu_changes.values() if v == "hausse")
    lu_baisse = sum(1 for v in lu_changes.values() if v == "baisse")
    be_hausse = sum(1 for v in be_changes.values() if v == "hausse")
    be_baisse = sum(1 for v in be_changes.values() if v == "baisse")
    
    # Construire le titre dynamique
    lu_text = ""
    be_text = ""
    
    if lu_baisse > 0 and lu_hausse == 0:
        lu_text = "🇱🇺 Luxembourg baisse"
    elif lu_hausse > 0 and lu_baisse == 0:
        lu_text = "🇱🇺 Luxembourg hausse"
    elif lu_baisse > 0 and lu_hausse > 0:
        lu_text = "🇱🇺 Luxembourg mixte"
    
    if be_baisse > 0 and be_hausse == 0:
        be_text = "🇧🇪 Belgique baisse"
    elif be_hausse > 0 and be_baisse == 0:
        be_text = "🇧🇪 Belgique hausse"
    elif be_baisse > 0 and be_hausse > 0:
        be_text = "🇧🇪 Belgique mixte"
    
    # Combiner les textes
    if lu_text and be_text:
        return f"{lu_text} & {be_text}"
    elif lu_text:
        return f"{lu_text} !"
    elif be_text:
        return f"{be_text} !"
    else:
        return "⛽️ Mise à jour des prix"

def build_notification(old_lu, new_lu, old_be, new_be):
    today = datetime.now().strftime("%d/%m")

    subtitle = build_dynamic_subtitle(old_lu, new_lu, old_be, new_be)
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
        lines.append(f"🇱🇺 {lu_val:.4f}€ ({diff_label(old_lu.get(fuel_key), lu_val)})")
        lines.append(f"🇧🇪 {be_val:.4f}€ ({diff_label(old_be.get(fuel_key), be_val)})")
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
        print(f"  ✅ LU -> {new_lu}")
    except Exception as e:
        print(f"❌ Erreur scraping LU : {e}")
        return

    try:
        new_be = fetch_be_prices()
        print(f"  ✅ BE -> {new_be}")
    except Exception as e:
        print(f"❌ Erreur scraping BE : {e}")
        return

    cache  = load_cache()
    old_lu = cache.get("lu", {})
    old_be = cache.get("be", {})

    lu_changed = any(old_lu.get(k) != new_lu[k] for k in FUELS)
    be_changed = any(old_be.get(k) != new_be[k] for k in FUELS)

    if not lu_changed and not be_changed:
        print("  ℹ️ Aucun changement detecte.")
        return

    print(f"  🔔 Changement detecte ! LU={lu_changed} BE={be_changed}")

    title, message = build_notification(old_lu, new_lu, old_be, new_be)
    send_notification(title, message)

    cache["lu"] = new_lu
    cache["be"] = new_be
    save_cache(cache)
    print("  ✅ Cache mis a jour.")

if __name__ == "__main__":
    main()
