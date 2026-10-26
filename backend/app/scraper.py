# app/scraper.py
#
# Extracts product data from a shop page. The main source is schema.org JSON-LD
# (Product / ProductGroup), with Open Graph tags and simple heuristics as fallback.

import json
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# Signs of a bot-protection page instead of the real product page
BLOCK_MARKERS = [
    "just a moment", "kpsdk", "security checkpoint", "bm-verify", "captcha",
    "api-services-support", "access denied", "px-captcha", "_incapsula_",
]


class ScrapeError(Exception):
    pass


# -------------------------
# Category mapping
# -------------------------

# (keyword, Kategorie, Unterkategorie). First match wins, so specific keywords come first.
CATEGORY_KEYWORDS = [
    ("ecksofa", "Sofas & Sessel", "Ecksofas"),
    ("schlafsofa", "Sofas & Sessel", "Schlafsofas"),
    ("sofatisch", "Sofas & Sessel", "Sofatische"),
    ("sofa", "Sofas & Sessel", "Sofas"),
    ("couch", "Sofas & Sessel", "Sofas"),
    ("sessel", "Sofas & Sessel", "Sessel"),
    ("pouf", "Sofas & Sessel", "Hocker & Poufs"),
    ("bettgestell", "Betten & Matratzen", "Bettgestelle"),
    ("lattenrost", "Betten & Matratzen", "Lattenroste"),
    ("matratze", "Betten & Matratzen", "Matratzen"),
    ("nachttisch", "Betten & Matratzen", "Nachttische"),
    ("bettwäsche", "Betten & Matratzen", "Bettwäsche"),
    ("kopfteil", "Betten & Matratzen", "Kopfteile"),
    ("bett", "Betten & Matratzen", "Betten"),
    ("schreibtisch", "Tische & Schreibtische", "Schreibtische"),
    ("esstisch", "Tische & Schreibtische", "Esstische"),
    ("couchtisch", "Tische & Schreibtische", "Couchtische"),
    ("beistelltisch", "Tische & Schreibtische", "Beistelltische"),
    ("konsolentisch", "Tische & Schreibtische", "Konsolentische"),
    ("bürostuhl", "Stühle & Hocker", "Bürostühle"),
    ("barhocker", "Stühle & Hocker", "Barhocker"),
    ("hocker", "Stühle & Hocker", "Hocker"),
    ("sitzbank", "Stühle & Hocker", "Bänke"),
    ("stuhl", "Stühle & Hocker", "Esszimmerstühle"),
    ("kleiderschrank", "Schränke & Kommoden", "Kleiderschränke"),
    ("kommode", "Schränke & Kommoden", "Kommoden"),
    ("sideboard", "Schränke & Kommoden", "Sideboards"),
    ("vitrine", "Schränke & Kommoden", "Vitrinen"),
    ("tv-", "Schränke & Kommoden", "TV-Möbel"),
    ("schuhschrank", "Schränke & Kommoden", "Schuhschränke"),
    ("schrank", "Schränke & Kommoden", ""),
    ("bücherregal", "Regale & Aufbewahrung", "Bücherregale"),
    ("wandregal", "Regale & Aufbewahrung", "Wandregale"),
    ("regal", "Regale & Aufbewahrung", "Regale"),
    ("garderobe", "Regale & Aufbewahrung", "Garderoben"),
    ("aufbewahrungsbox", "Regale & Aufbewahrung", "Aufbewahrungsboxen"),
    ("korb", "Regale & Aufbewahrung", "Körbe"),
    ("deckenleuchte", "Beleuchtung", "Deckenleuchten"),
    ("deckenlampe", "Beleuchtung", "Deckenleuchten"),
    ("stehleuchte", "Beleuchtung", "Stehlampen"),
    ("stehlampe", "Beleuchtung", "Stehlampen"),
    ("tischleuchte", "Beleuchtung", "Tischlampen"),
    ("tischlampe", "Beleuchtung", "Tischlampen"),
    ("wandleuchte", "Beleuchtung", "Wandleuchten"),
    ("wandlampe", "Beleuchtung", "Wandleuchten"),
    ("hängeleuchte", "Beleuchtung", "Hängeleuchten"),
    ("pendelleuchte", "Beleuchtung", "Hängeleuchten"),
    ("leuchtmittel", "Beleuchtung", "Leuchtmittel"),
    ("leuchte", "Beleuchtung", ""),
    ("lampe", "Beleuchtung", ""),
    ("teppich", "Textilien & Teppiche", "Teppiche"),
    ("vorhang", "Textilien & Teppiche", "Vorhänge"),
    ("gardine", "Textilien & Teppiche", "Vorhänge"),
    ("kissenbezug", "Textilien & Teppiche", "Kissenbezüge"),
    ("kissen", "Textilien & Teppiche", "Kissen"),
    ("plaid", "Textilien & Teppiche", "Decken"),
    ("wolldecke", "Textilien & Teppiche", "Decken"),
    ("handtuch", "Textilien & Teppiche", "Handtücher"),
    ("spiegel", "Dekoration", "Spiegel"),
    ("bilderrahmen", "Dekoration", "Bilderrahmen"),
    ("poster", "Dekoration", "Bilder & Poster"),
    ("kunstdruck", "Dekoration", "Bilder & Poster"),
    ("wandbild", "Dekoration", "Bilder & Poster"),
    ("vase", "Dekoration", "Vasen"),
    ("kerze", "Dekoration", "Kerzen & Kerzenhalter"),
    ("übertopf", "Dekoration", "Pflanzen & Töpfe"),
    ("pflanze", "Dekoration", "Pflanzen & Töpfe"),
    ("geschirr", "Küche & Essen", "Geschirr"),
    ("besteck", "Küche & Essen", "Besteck"),
    ("badezimmer", "Bad", "Badmöbel"),
    ("waschbecken", "Bad", "Waschbeckenschränke"),
    ("gartenstuhl", "Outdoor", "Gartenstühle"),
    ("gartentisch", "Outdoor", "Gartentische"),
    ("sonnenschirm", "Outdoor", "Sonnenschirme"),
    ("garten", "Outdoor", "Gartenmöbel"),
    ("balkon", "Outdoor", "Balkonmöbel"),
    ("kinder", "Kinder", ""),
]


def map_category(*texts: str) -> tuple[str, str] | None:
    """Maps scraped category / name / breadcrumb texts to (Kategorie, Unterkategorie). Earlier texts win."""
    for text in texts:
        low = text.lower()
        for keyword, category, sub in CATEGORY_KEYWORDS:
            if keyword in low:
                return category, sub
    return None


# -------------------------
# Colors
# -------------------------

COLOR_NAMES = {
    "weiß": "#ffffff", "weiss": "#ffffff", "white": "#ffffff", "creme": "#f5f0dc", "cremeweiß": "#f5f0dc",
    "elfenbein": "#fffff0", "schwarz": "#111111", "black": "#111111", "anthrazit": "#383e42",
    "dunkelgrau": "#555555", "hellgrau": "#d3d3d3", "grau": "#888888", "grey": "#888888", "gray": "#888888",
    "silber": "#c0c0c0", "silver": "#c0c0c0", "taupe": "#8b7d6b", "beige": "#d9c7a3", "sand": "#d8c29d",
    "natur": "#d2b48c", "natural": "#d2b48c", "eiche": "#b98c5a", "oak": "#b98c5a", "buche": "#c9a26b",
    "birke": "#e3cfa4", "kiefer": "#d9b36c", "nussbaum": "#5c4033", "walnuss": "#5c4033", "walnut": "#5c4033",
    "holz": "#a47c4f", "karamell": "#c68e4a", "cognac": "#9a4a1c", "braun": "#8b5a2b", "brown": "#8b5a2b",
    "kupfer": "#b87333", "messing": "#b5a642", "gold": "#d4af37", "terrakotta": "#c1633f",
    "rot": "#cc2222", "red": "#cc2222", "bordeaux": "#722f37", "rosa": "#f4a6c0", "pink": "#f4a6c0",
    "altrosa": "#d8a7b1", "rose": "#d8a7b1", "orange": "#f08a24", "gelb": "#f2cc2c", "yellow": "#f2cc2c",
    "senf": "#d9a521", "grün": "#2e8b57", "gruen": "#2e8b57", "green": "#2e8b57", "olive": "#6b7032",
    "salbei": "#9caf88", "mint": "#a8dcc1", "türkis": "#2ab7b0", "petrol": "#1f5f6b", "blau": "#2f5fb3",
    "blue": "#2f5fb3", "hellblau": "#9ec5e8", "dunkelblau": "#1f2f5f", "marine": "#1f2f5f", "navy": "#1f2f5f",
    "lila": "#8e4fb3", "violett": "#7a3fa0", "purple": "#8e4fb3", "flieder": "#c8a2d6",
}
_COLOR_KEYS = sorted(COLOR_NAMES, key=len, reverse=True)


def color_to_hex(text: str) -> list[str]:
    """Finds color names in free text ("Samt Karamell", "weiß/beige") and returns their hex values."""
    found: list[str] = []
    for part in re.split(r"[/,;&]|\bund\b|\band\b", text.lower()):
        for key in _COLOR_KEYS:
            if key in part:
                hex_ = COLOR_NAMES[key]
                if hex_ not in found:
                    found.append(hex_)
                break
    return found


def colors_from_title(name: str) -> list[str]:
    """Some shops only put the color at the end of the title ("Kommode TANGE weiß")."""
    return color_to_hex(" ".join(name.split()[-2:]))


# -------------------------
# JSON-LD helpers
# -------------------------

def _norm_url(u: str) -> str:
    return (u or "").split("#")[0].split("?")[0].rstrip("/").lower()


def _json_ld_nodes(soup: BeautifulSoup) -> list[dict]:
    nodes: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, list):
                stack.extend(cur)
            elif isinstance(cur, dict):
                nodes.append(cur)
                if "@graph" in cur:
                    stack.append(cur["@graph"])
    return nodes


def _types(node: dict) -> list[str]:
    t = node.get("@type", [])
    return t if isinstance(t, list) else [t]


def _offers(node: dict) -> list[dict]:
    o = node.get("offers", [])
    if isinstance(o, dict):
        o = [o]
    return [x for x in o if isinstance(x, dict)]


def _price(node: dict) -> float:
    for offer in _offers(node):
        candidates = []
        if offer.get("price") not in (None, ""):
            candidates.append(offer["price"])
        specs = offer.get("priceSpecification", [])
        if isinstance(specs, dict):
            specs = [specs]
        for spec in specs:
            if "strikethrough" in str(spec.get("priceType", "")).lower():
                continue
            if spec.get("price") not in (None, ""):
                candidates.append(spec["price"])
        if offer.get("lowPrice") not in (None, ""):
            candidates.append(offer["lowPrice"])
        for c in candidates:
            try:
                return float(str(c).replace(",", "."))
            except ValueError:
                continue
    return 0.0


def _images(node: dict) -> list[str]:
    raw = node.get("image", [])
    if not isinstance(raw, list):
        raw = [raw]
    urls = []
    for img in raw:
        if isinstance(img, dict):
            img = img.get("contentUrl") or img.get("url") or ""
        if isinstance(img, str) and img.startswith("http") and img not in urls:
            urls.append(img)
    return urls


def _cm(value) -> float | None:
    """Reads a length like 146.5, "146.5 cm", "B77", {"value": 100, "unitCode": "CMT"} and returns cm."""
    unit = ""
    if isinstance(value, dict):
        unit = str(value.get("unitCode") or value.get("unitText") or "").lower()
        value = value.get("value")
    if value is None:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mm|cm|m)?\b", str(value).lower())
    if not m:
        return None
    number = float(m.group(1).replace(",", "."))
    unit = m.group(2) or unit
    if unit in ("mm", "mmt"):
        return round(number / 10, 1)
    if unit in ("m", "mtr"):
        return round(number * 100, 1)
    return round(number, 1)


def _dimensions(node: dict) -> tuple[float | None, float | None, float | None]:
    """Returns (length, width, height) in cm. The longer horizontal side is the length."""
    width = _cm(node.get("width"))
    depth = _cm(node.get("depth"))
    height = _cm(node.get("height"))

    # Fallback: "B77 x H94 x T40 cm" in the description (JYSK)
    desc = str(node.get("description", ""))
    for var, pattern in (("w", r"\bB(\d+(?:[.,]\d+)?)"), ("h", r"\bH(\d+(?:[.,]\d+)?)"), ("d", r"\bT(\d+(?:[.,]\d+)?)")):
        m = re.search(pattern, desc)
        if not m:
            continue
        v = float(m.group(1).replace(",", "."))
        if var == "w" and width is None:
            width = v
        elif var == "h" and height is None:
            height = v
        elif var == "d" and depth is None:
            depth = v

    horizontal = sorted([d for d in (width, depth) if d is not None], reverse=True)
    length = horizontal[0] if horizontal else None
    breadth = horizontal[1] if len(horizontal) > 1 else None
    return length, breadth, height


def _color_values(node: dict) -> list[str]:
    c = node.get("color")
    if isinstance(c, list):
        c = " / ".join(str(x) for x in c)
    return color_to_hex(str(c)) if c else []


# -------------------------
# Main entry
# -------------------------

async def fetch_html(url: str) -> str:
    host = urlparse(url).netloc
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20, headers=HEADERS) as client:
            response = await client.get(url)
    except Exception as e:
        raise ScrapeError(f"Seite konnte nicht geladen werden: {e}")

    text = response.text
    low = text[:6000].lower()
    blocked = response.status_code in (202, 401, 403, 429) or (
        any(m in low for m in BLOCK_MARKERS) and "application/ld+json" not in text
    )
    if blocked:
        raise ScrapeError(
            f"{host} blockiert automatische Abrufe (Bot-Schutz, HTTP {response.status_code}). "
            "Das Item muss hier von Hand angelegt werden."
        )
    if response.status_code >= 400:
        raise ScrapeError(f"Seite konnte nicht geladen werden (HTTP {response.status_code})")
    return text


def parse_product(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    nodes = _json_ld_nodes(soup)

    product = next((n for n in nodes if "Product" in _types(n)), None)
    group = next((n for n in nodes if "ProductGroup" in _types(n)), None)
    crumbs: list[str] = []
    for n in nodes:
        if "BreadcrumbList" in _types(n):
            crumbs = [str(i.get("name", "")).strip() for i in n.get("itemListElement", []) if i.get("name")]
            break

    def meta(prop):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return tag.get("content", "").strip() if tag else ""

    variants: list[dict] = []
    base = product
    if group and not product:
        # ProductGroup (JYSK): the variant whose URL is this page is the product
        variants = [v for v in group.get("hasVariant", []) if isinstance(v, dict)]
        wanted = _norm_url(url)
        chosen = next((v for v in variants if any(_norm_url(o.get("url", "")) == wanted for o in _offers(v))), None)
        base = {**group, **(chosen or (variants[0] if variants else {}))}
        base.pop("hasVariant", None)

    name = category = ""
    price = 0.0
    images: list[str] = []
    colors: list[str] = []
    image_colors: dict[str, str] = {}
    length = width = height = None
    tags: list[str] = []

    if base:
        name = str(base.get("name", "")).strip()
        category = str(base.get("category", "")).strip()
        price = _price(base)
        images = _images(base)
        colors = _color_values(base)
        length, width, height = _dimensions(base)
        kw = base.get("keywords", "")
        if isinstance(kw, str) and kw:
            tags = [k.strip() for k in kw.split(",") if k.strip()]
        elif isinstance(kw, list):
            tags = [str(k).strip() for k in kw if k]

        # Variants in other colors that carry their own images
        base_colors = list(colors)
        base_images = list(images)
        for v in variants:
            v_colors = _color_values(v)
            if v_colors and v_colors != colors:
                for c in v_colors:
                    if c not in colors:
                        colors.append(c)
                for img in _images(v):
                    if img not in images:
                        images.append(img)
                    image_colors[img] = v_colors[0]
        if base_colors and image_colors:
            for img in base_images:
                image_colors.setdefault(img, base_colors[0])

    if not name:
        name = meta("og:title") or meta("twitter:title")
    if not name:
        h1 = soup.find("h1")
        name = h1.get_text(strip=True) if h1 else ""
    if not name:
        title = soup.find("title")
        name = title.get_text(strip=True).split("|")[0].strip() if title else ""
    if not images and meta("og:image"):
        images = [meta("og:image")]
    if not price:
        m = re.search(r"(\d{1,5}[.,]\d{2})\s*€|€\s*(\d{1,5}[.,]\d{2})", soup.get_text())
        if m:
            price = float((m.group(1) or m.group(2)).replace(",", "."))
    if not colors and name:
        colors = colors_from_title(name)
    if not tags:
        tags = crumbs[1:-1] if len(crumbs) > 2 else []
    if not tags:
        kw = meta("keywords")
        tags = [k.strip() for k in kw.split(",") if k.strip()]

    if not name:
        raise ScrapeError("Keine Produktdaten gefunden. Die Seite ist möglicherweise JavaScript-gerendert.")

    mapped = map_category(f"{name} {category}", " ".join(crumbs[1:]))
    if mapped:
        category, subcategory = mapped
    else:
        category, subcategory = "Sonstiges", category or (crumbs[-2] if len(crumbs) > 2 else "")

    # Images without an own color belong to the product's color if there is only one
    image_list = []
    for img in images:
        color = image_colors.get(img)
        if color is None and len(colors) == 1:
            color = colors[0]
        image_list.append({"url": img, "color": color})

    return {
        "name": name,
        "category": category,
        "subcategory": subcategory,
        "price": price,
        "location": url,
        "image_url": images[0] if images else "",
        "images": image_list,
        "colors": colors,
        "length": length,
        "width": width,
        "height": height,
        "tags": tags,
    }


async def scrape(url: str) -> dict:
    html = await fetch_html(url)
    return parse_product(html, url)
