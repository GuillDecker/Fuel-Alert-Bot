import requests
import json
import os
import time
from bs4 import BeautifulSoup
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────
NTFY_URL   = os.environ.get("NTFY_URL")
CACHE_FILE = "prices_cache.json"

URL_LU        = "https://www.petrol.lu/prix-officiels/"
URL_BE        = "https://carbu.com/belgique/prixmaximum"
URL_BE_MAZOUT = "https://petrolprices.economie.fgov.be/petrolprices?locale=fr"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36"
}

FUELS = ["sp95", "sp98", "diesel", "mazout"]

# ─── Fourchettes de prix valides (garde-fou anti-aberration) ───────
PRICE_BOUNDS = {
    "sp95":   (1.0, 2.5),
    "sp98":   (1.0, 2.5),
    "diesel": (1.0, 2.5),
    "mazout": (0.5, 2.0),
}

def validate_price(fuel_key, price, source):
    """Lève une ValueError si le prix est hors fourchette réaliste."""
    low, high = PRICE_BOUNDS[fuel_key]
    if not (low <= price <= high):
        raise ValueError(
            f"Prix {fuel_key} suspect sur {source} : {price}€ "
            f"(attendu entre {low}€ et {high}€)"
        )
    return price

# ─── Requête robuste avec retries ──────────────────────────────────
def fetch_with_retry(url, headers, timeout=30, retries=3, delay=10):
    """GET avec plusieurs tentatives en cas d'échec."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            last_err = e
            print(f"  ⏳ Tentative {attempt}/{retries} échouée sur {url} : {e}")
            if attempt < retries:
                print(f"     ↻ Nouvelle tentative dans {delay}s...")
                time.sleep(delay)
    raise last_err

# ─── Scraping Luxembourg (petrol.lu) ───────────────────────────────
def fetch_lu_prices():
    r = fetch_with_retry(URL_LU, HEADERS, timeout=30, retries=3, delay=10)
    soup = BeautifulSoup(r.text, "html.parser")

    table = soup.find("div", class_="prices-table")
    if not table:
        raise ValueError("Tableau prices-table introuvable sur petrol.lu")

    tvac_row = None
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if cells and cells[-1].text.strip() == "TVAC":
            tvac_row = cells
            break

    if not tvac_row:
        raise ValueError("Ligne TVAC introuvable sur petrol.lu")

    # Colonnes : Date | Super98 | Super95 | Diesel | Gasoil chauff | Gasoil chauff BTS (>1500) | TVA
    sp98   = round(float(tvac_row[1].text.strip().replace(",", ".")), 3)
    sp95   = round(float(tvac_row[2].text.strip().replace(",", ".")), 3)
    diesel = round(float(tvac_row[3].text.strip().replace(",", ".")), 3)
    mazout = round(float(tvac_row[5].text.strip().replace(",", ".")), 3)

    return {
        "sp95":   validate_price("sp95",   sp95,   "petrol.lu"),
        "sp98":   validate_price("sp98",   sp98,   "petrol.lu"),
        "diesel": validate_price("diesel", diesel, "petrol.lu"),
        "mazout": validate_price("mazout", mazout, "petrol.lu"),
    }

# ─── Scraping Belgique - Mazout >2000L (SPF Economie - officiel) ──
def fetch_be_mazout():
    """Récupère le prix officiel du gasoil de chauffage BE >2000L."""
    r = fetch_with_retry(URL_BE_MAZOUT, HEADERS, timeout=30, retries=3, delay=10)
    soup = BeautifulSoup(r.text, "html.parser")

    for row in soup.select("tbody#petrolTable_data tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        label = cells[0].get_text(strip=True).lower()
        if "chauffage" in label and "partir de 2000" in label:
            prix_txt = cells[1].get_text(strip=True)
            prix = prix_txt.split("euro")[0].strip()
            price = round(float(prix.replace(",", ".")), 3)
            return validate_price("mazout", price, "petrolprices.economie.fgov.be")

    raise ValueError("Mazout BE >2000L introuvable sur petrolprices.economie.fgov.be")

# ─── Scraping Belgique - Carburants ───────────────────────────────
def fetch_be_prices():
    r = fetch_with_retry(URL_BE, HEADERS, timeout=30, retries=3, delay=10)
    soup = BeautifulSoup(r.text, "html.parser")

    prices = {}

    # On parcourt LIGNE PAR LIGNE pour garder nom + prix alignés
    rows = soup.find_all("tr")
    if not rows:
        raise ValueError("Aucune ligne de tableau trouvée sur carbu.com")

    for row in rows:
        fuel_cell = row.find("td", class_="officialPriceBe_col1")
        if not fuel_cell:
            continue

        fuel_name = fuel_cell.text.strip().lower()

        # Toutes les cellules "price" de CETTE ligne uniquement
        price_cells = row.find_all("td", class_="price")

        # On cherche le 1er prix RÉALISTE (1.0–2.5€) dans la ligne
        valid_price = None
        for pc in price_cells:
            txt = (pc.text.strip()
                     .replace(",", ".")
                     .replace("€/l", "")
                     .replace("€", "")
                     .strip())
            try:
                p = round(float(txt), 3)
            except ValueError:
                continue
            if 1.0 <= p <= 2.5:        # on ignore les €/100km et autres aberrations
                valid_price = p
                break

        if valid_price is None:
            print(f"  [DEBUG] Aucun prix valide pour '{fuel_name}' — ligne ignorée")
            continue

        print(f"  [DEBUG] fuel='{fuel_name}' → {valid_price}€")

        if "diesel" in fuel_name and "diesel" not in prices:
            prices["diesel"] = validate_price("diesel", valid_price, "carbu.com")
        elif ("95" in fuel_name or "e10" in fuel_name) and "98" not in fuel_name and "sp95" not in prices:
            prices["sp95"] = validate_price("sp95", valid_price, "carbu.com")
        elif "98" in fuel_name and "e5" in fuel_name and "sp98" not in prices:
            prices["sp98"] = validate_price("sp98", valid_price, "carbu.com")

    if not all(k in prices for k in ["sp95", "sp98", "diesel"]):
        raise ValueError(f"Prix BE incomplets après validation : {prices}")

    prices["mazout"] = fetch_be_mazout()
    return prices

# ─── Cache ─────────────────────────────────────────────────────────
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {"lu": {}, "be": {}}

def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ─── Comparaison & formatage ────────────────────────────────────────
def diff_label(old, new):
    if old is None:
        return "🆕 Nouveau"
    delta = round(new - old, 3)
    if abs(delta) < 0.001:
        return "⚖️ Stable"
    elif delta > 0:
        return f"📈 Hausse de +{delta:.3f}€"
    else:
        return f"📉 Baisse de {delta:.3f}€"

def build_notification(old_lu, new_lu, old_be, new_be):
    today = datetime.now().strftime("%d/%m")

    changed_lu = any(old_lu.get(k) != new_lu[k] for k in FUELS)
    changed_be = any(old_be.get(k) != new_be[k] for k in FUELS)

    if changed_lu and changed_be:
        subtitle = "🇱🇺🇧🇪 Les deux pays changent leurs prix !"
    elif changed_lu:
        subtitle = "🇱🇺 Luxembourg change ses prix !"
    else:
        subtitle = "🇧🇪 Belgique change ses prix !"

    title = f"⛽️ Alerte Carburants ({today})"
    lines = [subtitle, ""]

    for fuel_key, emoji, label in [
        ("diesel", "🟡", "DIESEL"),
        ("sp95",   "🟢", "SP95"),
        ("sp98",   "🔵", "SP98"),
        ("mazout", "🔥", "MAZOUT CHAUFFAGE"),
    ]:
        lu_val = new_lu[fuel_key]
        be_val = new_be[fuel_key]

        if lu_val < be_val:
            trophy = "🏆 Go Lux. !"
        elif be_val < lu_val:
            trophy = "🏆 Go Belgique !"
        else:
            trophy = "🤝 Égalité !"

        lines.append(f"{emoji} {label} | {trophy}")
        lines.append(f"🇱🇺 {lu_val:.3f}€ ({diff_label(old_lu.get(fuel_key), lu_val)})")
        lines.append(f"🇧🇪 {be_val:.3f}€ ({diff_label(old_be.get(fuel_key), be_val)})")
        lines.append("")

    return title, "\n".join(lines).strip()

# ─── Envoi ntfy ────────────────────────────────────────────────────
def send_notification(title, message):
    if not NTFY_URL:
        print("⚠️ NTFY_URL non défini — notif non envoyée.")
        print(f"TITRE   : {title}")
        print(f"MESSAGE :\n{message}")
        return

    requests.post(
        NTFY_URL,
        data=message.encode("utf-8"),
        headers={
            "Title":    title.encode("utf-8"),
            "Priority": "high",
            "Tags":     "fuelpump,rotating_light"
        },
        timeout=10
    )
    print(f"✅ Notification envoyée : {title}")

# ─── Main ───────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Vérification des prix...")

    try:
        new_lu = fetch_lu_prices()
        print(f"  LU → {new_lu}")
    except Exception as e:
        print(f"❌ Erreur scraping LU : {e}")
        return

    try:
        new_be = fetch_be_prices()
        print(f"  BE → {new_be}")
    except Exception as e:
        print(f"❌ Erreur scraping BE : {e}")
        return

    cache  = load_cache()
    old_lu = cache.get("lu", {})
    old_be = cache.get("be", {})

    lu_changed = any(old_lu.get(k) != new_lu[k] for k in FUELS)
    be_changed = any(old_be.get(k) != new_be[k] for k in FUELS)

    if not lu_changed and not be_changed:
        print("  Aucun changement détecté.")
        return

    print(f"  🚨 Changement détecté ! LU={lu_changed} BE={be_changed}")

    title, message = build_notification(old_lu, new_lu, old_be, new_be)
    send_notification(title, message)

    cache["lu"] = new_lu
    cache["be"] = new_be
    save_cache(cache)
    print("  Cache mis à jour.")

if __name__ == "__main__":
    main()
