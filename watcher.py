"""
Deal Watcher
============
Skontroluje nakonfigurované výpredajové stránky, vyfiltruje produkty podľa
značky a minimálnej zľavy, a o nových nálezoch pošle Telegram správu.

Navrhnuté na spúšťanie cez GitHub Actions (pozri .github/workflows/watch.yml),
ale dá sa spustiť aj lokálne: python watcher.py
"""

import os
import re
import sys
import time
import json
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup

STATE_FILE = "state.json"
CONFIG_FILE = "config.yaml"


def build_session():
    """Session, ktorá sa hlavičkami podobá na bežný Chrome prehliadač.
    Niektoré eshopy (napr. 8a.sk) vracajú 403 Forbidden pre požiadavky
    s príliš jednoduchým/podozrivým User-Agentom."""
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sk-SK,sk;q=0.9,cs;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return s


SESSION = build_session()
_visited_homepages = set()


def fetch(url):
    """Stiahne stránku. Pred prvou požiadavkou na danú doménu si najprv
    'prejde' cez domovskú stránku (ako reálny návštevník) - niektoré
    ochrany proti botom to kontrolujú."""
    parsed = urlparse(url)
    homepage = f"{parsed.scheme}://{parsed.netloc}/"
    if homepage not in _visited_homepages:
        try:
            SESSION.get(homepage, timeout=20)
        except Exception:
            pass
        _visited_homepages.add(homepage)
        time.sleep(1)
    resp = SESSION.get(url, timeout=20, headers={"Referer": homepage})
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Pomocné funkcie: config / stav / Telegram
# ---------------------------------------------------------------------------

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"seen": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"Telegram error: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Telegram exception: {e}")


# ---------------------------------------------------------------------------
# Parsery pre jednotlivé eshopy
#
# Každý parser dostane surové HTML a musí vrátiť zoznam produktov v tvare:
#   {"name": str, "url": str, "price": float|None, "rrp": float|None,
#    "discount": int}
#
# Ak chceš pridať nový eshop, over si (cez "zobraziť zdroj stránky" v
# prehliadači), ako sa opakuje blok jedného produktu, a napíš vlastný parser
# podľa vzoru nižšie. Potom ho zaregistruj do slovníka PARSERS.
# ---------------------------------------------------------------------------

# 8a.sk / 8a.cz / 8a.pl bežia na rovnakej Magento platforme (Advox téma) a
# na stránke sa pri každom zľavnenom produkte opakuje text v tvare:
#   "... vrátane DPH 117,99 €  ...  Cena odporúčaná výrobcom 139,99 € (-15%)"
_PRICE_RE = re.compile(r"Cena odporúčaná výrobcom\s+([\d.,]+)\s*€\s*\(-(\d+)%\)")
_SALE_PRICE_RE = re.compile(r"vrátane DPH\s+([\d.,]+)\s*€")


def _to_float(txt):
    try:
        return float(txt.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def parse_8a_style(html, base_url):
    soup = BeautifulSoup(html, "html.parser")

    # Primárny selektor pre Magento product grid. Ak sa štruktúra stránky
    # zmení a toto prestane fungovať, over si aktuálne CSS triedy cez
    # Inspect Element a uprav zoznam nižšie.
    items = soup.select("li.product-item, div.product-item-info")
    if not items:
        items = soup.find_all("li")

    products = []
    for item in items:
        link_tag = item.find("a", href=True)
        if not link_tag:
            continue

        text_block = item.get_text(" ", strip=True)
        m = _PRICE_RE.search(text_block)
        if not m:
            continue

        name = link_tag.get("title") or link_tag.get_text(strip=True)
        if not name:
            continue

        href = link_tag["href"]
        if not href.startswith("http"):
            href = base_url.rstrip("/") + "/" + href.lstrip("/")

        rrp = _to_float(m.group(1))
        discount = int(m.group(2))

        price_m = _SALE_PRICE_RE.search(text_block)
        sale_price = _to_float(price_m.group(1)) if price_m else None

        products.append(
            {
                "name": name,
                "url": href,
                "price": sale_price,
                "rrp": rrp,
                "discount": discount,
            }
        )
    return products


PARSERS = {
    "8a_style": parse_8a_style,
}


# ---------------------------------------------------------------------------
# Filtrovanie a hlavný beh
# ---------------------------------------------------------------------------

def matches_brand(name, brands):
    if not brands:
        return True
    low = name.lower()
    return any(b.lower() in low for b in brands)


def main():
    cfg = load_config()
    state = load_state()
    seen = set(state.get("seen", []))

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Chýbajú premenné prostredia TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.")
        sys.exit(1)

    min_discount = cfg.get("min_discount_percent", 50)
    brands = cfg.get("brands", [])

    new_hits = []

    for site in cfg.get("sites", []):
        if not site.get("enabled", True):
            continue

        parser = PARSERS.get(site.get("parser"))
        if not parser:
            print(f"Preskakujem '{site['name']}': neznámy parser '{site.get('parser')}'.")
            continue

        try:
            html = fetch(site["url"])
        except Exception as e:
            print(f"Chyba pri sťahovaní '{site['name']}': {e}")
            continue

        try:
            products = parser(html, site["url"])
        except Exception as e:
            print(f"Chyba pri parsovaní '{site['name']}': {e}")
            continue

        print(f"{site['name']}: nájdených {len(products)} zľavnených produktov na stránke.")

        for p in products:
            if p["discount"] < min_discount:
                continue
            if not matches_brand(p["name"], brands):
                continue
            if p["url"] in seen:
                continue
            seen.add(p["url"])
            new_hits.append((site["name"], p))

    if new_hits:
        for site_name, p in new_hits:
            price_txt = f"{p['price']:.2f} €" if p["price"] else "?"
            rrp_txt = f"{p['rrp']:.2f} €" if p["rrp"] else "?"
            msg = (
                f"🔥 <b>-{p['discount']}%</b> {p['name']}\n"
                f"{price_txt} (namiesto {rrp_txt})\n"
                f"{site_name}\n"
                f"{p['url']}"
            )
            send_telegram(token, chat_id, msg)
            time.sleep(1)  # neposielať Telegramu správy priveľmi rýchlo za sebou

    # Obmedzenie veľkosti state.json, aby súbor časom nenarástol donekonečna
    state["seen"] = list(seen)[-5000:]
    save_state(state)

    print(f"Hotovo. Nových nálezov: {len(new_hits)}. Celkovo sledovaných URL v stave: {len(seen)}.")


if __name__ == "__main__":
    main()
