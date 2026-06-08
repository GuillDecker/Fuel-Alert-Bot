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
URL_BE = "https://www.energiafed.be/fr/prix-maximums"

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
        raise ValueError("Ligne Luxembourg introuvable dans luxPrices.php")

    cells = row.find_all("td")
    sp95   = cells[2].text.strip().replace(",", ".")
    sp98   = cells[3].text.strip().replace(",", ".")
    diesel = cells[4].text.strip().replace(",", ".")

    return {
        "sp95":   float(sp95),
        "sp98":   float(sp98),
        "diesel": float(diesel)
    }

# ─── Scraping Belgique ─────────────────────────────────────────────
def fetch_be_prices():
    r = requests.get(URL_BE, headers=HEADERS, timeout=15)
    r.raise_for_status()

    match = re.search(r'drupalSettings\s*=\s*({.*?});\s*</script>', r.text, re.DOTALL)
    if not match:
        soup = BeautifulSoup(r.text, "html.parser")
        prices = {}
        for section in soup.find_all("section", class_="samenstelling-chart"):
            title = section.find("h3", class_="samenstelling-chart__title")
            price = section.find("div",  class_="samenstelling-chart__price")
            if title and price:
                name = title.text.strip()
                val  = re.search(r"[\d.]+", price.text)
                if val:
                    if "95" in name and "E10" in name:
                        prices["sp95"]   = float(val.group())
                    elif "98" in name and "E5" in name and "E10" not in name:
                        prices["sp98"]   = float(val.group())
                    elif name == "Diesel":
                        prices["diesel"] = float(val.group())
        if len(prices) == 3:
            return prices
        raise ValueError(f"Prix BE incomplets via fallback HTML : {prices}")

    raw = r.text

    sp95_match   = re.search(r'"name":"Essence 95 RON - E10"[^}]*"prijs":"([\d.]+)"', raw)
    sp98_match   = re.search(r'"name":"Essence 98 RON - E5"[^}]*"prijs":"([\d.]+)"', raw)
    diesel_match = re.search(r'"name":"Diesel"[^}]*"prijs":"([\d.]+)"', raw)

    if not sp95_match:
        sp95_match = re.search(r'"prijs":"([\d.]+)"[^}]*"name":"Essence 95 RON - E10"', raw)
    if not sp98_match:
        sp98_match = re.search(r'"prijs":"([\d.]+)"[^}]*"name":"Essence 98 RON - E5"', raw)
    if not diesel_match:
        diesel_match = re.search(r'"prijs":"([\d.]+)"[^}]*"name":"Diesel"[^-]', raw)

    if not all([sp95_match, sp98_match, diesel_match]):
        raise ValueError("Impossible d'extraire les prix BE depuis le JSON")

    return {
        "sp95":   float(sp95_match.group(1)),
        "sp98":   float(sp98_match.group(1)),
        "diesel": float(diesel_match.group(1))
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

# ─── Comparaison & formatage ────────────────────────────────────────
def diff_label(old, new):
    if old is None:
        return "Nouveau"
    delta = round(new - old, 4)
    if abs(delta) < 0.0001:
        return "Stable"
    elif delta > 0:
        return f"Hausse +{delta:.2f}e"
    else:
        return f"Baisse -{abs(delta):.2f}e"

def build_notification(old_lu, new_lu, old_be, new_be):
    today = datetime.now().strftime("%d/%m")

    changed_lu = any(old_lu.get(k) != new_lu[k] for k in ["sp95", "sp98", "diesel"])
    changed_be = any(old_be.get(k) != new_be[k] for k in ["sp95", "sp98", "diesel"])

    if changed_lu and changed_be:
        subtitle = "LU+BE changent leurs prix !"
    elif changed_lu:
        subtitle = "Luxembourg change ses prix !"
    else:
        subtitle = "Belgique change ses prix !"

    title = f"Alerte Carburants ({today})"

    lines = [subtitle, ""]

    for fuel_key, label in [
        ("diesel", "DIESEL"),
        ("sp95",   "SP95"),
        ("sp98",   "SP98"),
    ]:
        lu_val = new_lu[fuel_key]
        be_val = new_be[fuel_key]

        if lu_val < be_val:
            trophy = "Go Luxembourg !"
        elif be_val < lu_val:
            trophy = "Go Belgique !"
        else:
            trophy = "Egalite !"

        lines.append(f"{label} | {trophy}")
        lines.append(f"  LU: {lu_val:.3f}e ({diff_label(old_lu.get(fuel_key), lu_val)})")
        lines.append(f"  BE: {be_val:.3f}e ({diff_label(old_be.get(fuel_key), be_val)})")
        lines.append("")

    return title, "\n".join(lines)

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
            data=message,
            headers={
                "Title":    title,
                "Priority": "high",
                "Tags":     "fuelpump,rotating_light"
            },
            timeout=10
        )
        response.raise_for_status()
        print(f"Notification envoyee : {title} (Status: {response.status_code})")
    except Exception as e:
        print(f"Erreur lors de l'envoi ntfy : {e}")

# ─── Main ───────────────────────────────────────────────────────────
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

    lu_changed = any(old_lu.get(k) != new_lu[k] for k in ["sp95", "sp98", "diesel"])
    be_changed = any(old_be.get(k) != new_be[k] for k in ["sp95", "sp98", "diesel"])

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
