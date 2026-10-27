# app/main.py

import hmac
import json
import logging
import os
import uuid
import shutil
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import re
import httpx
import jwt
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio

from app import linkcheck, scraper
from app.db import get_connection
from fastapi.middleware.cors import CORSMiddleware

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
APP_PASSWORD = os.getenv("APP_PASSWORD", "changeme")
# Key for the iPad shortcut (see docs/kurzbefehl-import.md). Without it the page import is switched off.
IMPORT_KEY = os.getenv("IMPORT_KEY", "")
MAX_IMPORT_IMAGES = 12
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()
log = logging.getLogger("main")


def create_token() -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = get_connection()
    cursor = conn.cursor()

    # Main table (created on a fresh database; later columns are added below)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS furniture (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            location TEXT,
            price REAL
        )
    """)
    conn.commit()

    # Ensure legacy image_path column exists
    try:
        cursor.execute("ALTER TABLE furniture ADD COLUMN image_path TEXT")
        conn.commit()
    except Exception:
        pass

    # Link check state (see linkcheck.py)
    for col_def in ("link_ok INTEGER", "link_status TEXT", "link_checked_at TEXT", "link_fails INTEGER NOT NULL DEFAULT 0"):
        try:
            cursor.execute(f"ALTER TABLE furniture ADD COLUMN {col_def}")
            conn.commit()
        except Exception:
            pass

    # Used flag (Verwendet)
    try:
        cursor.execute("ALTER TABLE furniture ADD COLUMN used INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except Exception:
        pass

    # Sub-category (Unterkategorie)
    try:
        cursor.execute("ALTER TABLE furniture ADD COLUMN subcategory TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    # Size columns (Größe), in cm
    for col in ("length", "width", "height"):
        try:
            cursor.execute(f"ALTER TABLE furniture ADD COLUMN {col} REAL")
            conn.commit()
        except Exception:
            pass

    # Images table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS furniture_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            furniture_id INTEGER NOT NULL REFERENCES furniture(id),
            filename TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Optional color of an image (one of the item's colors)
    try:
        cursor.execute("ALTER TABLE furniture_images ADD COLUMN color TEXT")
        conn.commit()
    except Exception:
        pass

    # Tags table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS furniture_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            furniture_id INTEGER NOT NULL REFERENCES furniture(id),
            tag TEXT NOT NULL
        )
    """)
    # Colors table (hex values like #aabbcc)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS furniture_colors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            furniture_id INTEGER NOT NULL REFERENCES furniture(id),
            color TEXT NOT NULL
        )
    """)
    conn.commit()

    # Migrate legacy image_path rows into furniture_images
    cursor.execute("SELECT id, image_path FROM furniture WHERE image_path IS NOT NULL")
    rows = cursor.fetchall()
    for row in rows:
        cursor.execute(
            "SELECT COUNT(*) FROM furniture_images WHERE furniture_id = ? AND filename = ?",
            (row["id"], row["image_path"])
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO furniture_images (furniture_id, filename, position) VALUES (?, ?, 0)",
                (row["id"], row["image_path"])
            )
    conn.commit()
    conn.close()
    checker = asyncio.create_task(linkcheck.scheduler())
    yield
    checker.cancel()


app = FastAPI(lifespan=lifespan)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# -------------------------
# Data Models
# -------------------------

class LoginRequest(BaseModel):
    password: str

class ScrapeRequest(BaseModel):
    url: str


class FurnitureItem(BaseModel):
    name: str
    category: str
    subcategory: str = ""
    location: str
    price: float
    used: bool = False
    length: float | None = None
    width: float | None = None
    height: float | None = None
    tags: list[str] = []
    colors: list[str] = []

class FurnitureUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    subcategory: str | None = None
    location: str | None = None
    price: float | None = None
    used: bool | None = None
    length: float | None = None
    width: float | None = None
    height: float | None = None
    tags: list[str] | None = None
    colors: list[str] | None = None


# -------------------------
# Helpers
# -------------------------

def _set_tags(cursor, furniture_id: int, tags: list[str]):
    cursor.execute("DELETE FROM furniture_tags WHERE furniture_id = ?", (furniture_id,))
    for tag in tags:
        tag = tag.strip()
        if tag:
            cursor.execute(
                "INSERT INTO furniture_tags (furniture_id, tag) VALUES (?, ?)",
                (furniture_id, tag)
            )


HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _set_colors(cursor, furniture_id: int, colors: list[str]):
    cursor.execute("DELETE FROM furniture_colors WHERE furniture_id = ?", (furniture_id,))
    seen = set()
    for color in colors:
        color = color.strip().lower()
        if HEX_COLOR.match(color) and color not in seen:
            seen.add(color)
            cursor.execute(
                "INSERT INTO furniture_colors (furniture_id, color) VALUES (?, ?)",
                (furniture_id, color)
            )
    # Images tagged with a color that was removed become uncolored
    cursor.execute(
        f"UPDATE furniture_images SET color = NULL WHERE furniture_id = ? AND color IS NOT NULL"
        f" AND color NOT IN ({','.join('?' * len(seen))})",
        (furniture_id, *seen)
    )


def _fetch_related(cursor):
    cursor.execute("SELECT * FROM furniture_images ORDER BY position, id")
    images_rows = cursor.fetchall()
    cursor.execute("SELECT * FROM furniture_tags ORDER BY id")
    tags_rows = cursor.fetchall()
    cursor.execute("SELECT * FROM furniture_colors ORDER BY id")
    colors_rows = cursor.fetchall()

    images_by_id = defaultdict(list)
    for img in images_rows:
        images_by_id[img["furniture_id"]].append({"id": img["id"], "filename": img["filename"], "color": img["color"]})

    tags_by_id = defaultdict(list)
    for t in tags_rows:
        tags_by_id[t["furniture_id"]].append(t["tag"])

    colors_by_id = defaultdict(list)
    for c in colors_rows:
        colors_by_id[c["furniture_id"]].append(c["color"])

    return images_by_id, tags_by_id, colors_by_id


# -------------------------
# Routes
# -------------------------

@app.get("/")
def root():
    return {"message": "Furniture API running"}


@app.post("/auth/login")
def login(body: LoginRequest):
    if body.password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Falsches Passwort")
    return {"token": create_token()}


@app.post("/scrape")
async def scrape(body: ScrapeRequest, _=Depends(verify_token)):
    url = body.url if body.url.startswith("http") else f"https://{body.url}"
    try:
        return await scraper.scrape(url)
    except scraper.ScrapeError as e:
        raise HTTPException(status_code=422, detail=str(e))


class ImageUrlRequest(BaseModel):
    url: str


async def _download_image(url: str, referer: str | None = None) -> tuple[bytes, str]:
    """Downloads an image and returns its bytes and file extension. Raises on errors or non-images."""
    headers = {**scraper.HEADERS, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    if referer:
        headers["Referer"] = referer
    async with httpx.AsyncClient(follow_redirects=True, timeout=15, headers=headers) as client:
        r = await client.get(url)
    r.raise_for_status()
    content_type = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        # e.g. an HTML page of a bot protection instead of the image
        raise ValueError(f"kein Bild ({content_type or 'unbekannter Typ'})")
    ext = "." + content_type.split("/")[-1]
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
        ext = ".jpg"
    return r.content, ext


def _store_image(item_id: int, content: bytes, ext: str) -> dict:
    filename = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        f.write(content)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM furniture_images WHERE furniture_id = ?", (item_id,)
    )
    next_position = cursor.fetchone()[0]
    cursor.execute(
        "INSERT INTO furniture_images (furniture_id, filename, position) VALUES (?, ?, ?)",
        (item_id, filename, next_position)
    )
    conn.commit()
    image_id = cursor.lastrowid
    conn.close()
    return {"id": image_id, "filename": filename}


@app.post("/furniture/{item_id}/image-url")
async def upload_image_from_url(item_id: int, body: ImageUrlRequest, _=Depends(verify_token)):
    conn = get_connection()
    found = conn.execute("SELECT id FROM furniture WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    if not found:
        raise HTTPException(status_code=404, detail="Item not found")
    try:
        content, ext = await _download_image(body.url)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Bild konnte nicht geladen werden: {e}")
    return _store_image(item_id, content, ext)


class PageImport(BaseModel):
    url: str
    html: str


def _import_reply(status: int, message: str, **extra):
    # The shortcut shows "message" in a notification, for success and errors alike
    return JSONResponse(status_code=status, content={"ok": status == 200, "message": message, **extra})


@app.post("/import/page")
async def import_page(request: Request, dry_run: bool = False, x_import_key: str | None = Header(default=None)):
    """Creates an item from a page that the iPad shortcut read in Safari, so the shop is never asked by the backend."""
    if not IMPORT_KEY:
        return _import_reply(503, "Der Import ist im Backend nicht eingerichtet (IMPORT_KEY fehlt in backend/.env).")
    if not x_import_key or not hmac.compare_digest(x_import_key.strip(), IMPORT_KEY):
        # Only in the server log (never in the reply), so a mistyped key can be diagnosed without showing it
        got = x_import_key or ""
        log.warning(
            "Import: wrong key. received %d chars (expected %d), differs only by case: %s, "
            "whitespace/invisible chars: %s, non-ASCII chars: %s, starts like expected: %s",
            len(got), len(IMPORT_KEY), got.strip().lower() == IMPORT_KEY.lower(),
            got != got.strip() or any(not c.isprintable() for c in got),
            any(ord(c) > 127 for c in got), got[:1] == IMPORT_KEY[:1],
        )
        return _import_reply(401, "Falscher Import-Schlüssel. Prüfe den Header X-Import-Key im Kurzbefehl.")
    # The shortcut may send the JSON as a quoted string (JSON inside a JSON string), so unpack up to twice
    try:
        payload = json.loads(await request.body())
        if isinstance(payload, str):
            payload = json.loads(payload)
        body = PageImport(**payload)
    except Exception:
        return _import_reply(422, "Die Anfrage enthält keine Seite (erwartet: JSON mit url und html). Prüfe den Anfragetext im Kurzbefehl.")
    if len(body.html) > 20_000_000:
        return _import_reply(413, "Die Seite ist zu groß.")
    url = body.url.strip()
    try:
        data = scraper.parse_product(body.html, url)
    except scraper.ScrapeError as e:
        return _import_reply(422, str(e))
    if not data["price"] and not data["images"]:
        return _import_reply(422, "Auf der Seite wurden keine Produktdaten gefunden. Ist das eine Produktseite?")
    if dry_run:
        # for testing: show what would be imported, without saving anything
        return _import_reply(200, f"Test: {data['name']}", data=data)

    item_id = create_furniture(FurnitureItem(
        name=data["name"], category=data["category"], subcategory=data["subcategory"],
        location=url, price=data["price"] or 0,
        length=data["length"], width=data["width"], height=data["height"],
        tags=data["tags"], colors=data["colors"],
    ))["id"]

    # download in parallel, store in the original order
    images = data["images"][:MAX_IMPORT_IMAGES]
    limit = asyncio.Semaphore(4)

    async def download(img):
        async with limit:
            try:
                return await _download_image(img["url"], referer=url)
            except Exception as e:
                log.warning("Bild %s nicht geladen: %s", img["url"], e)
                return None

    results = await asyncio.gather(*(download(img) for img in images))
    loaded = 0
    for img, result in zip(images, results):
        if result is None:
            continue
        saved = _store_image(item_id, *result)
        loaded += 1
        if img.get("color"):
            try:
                update_image_color(item_id, saved["id"], ImageColorUpdate(color=img["color"]))
            except HTTPException:
                pass

    message = f"Importiert: {data['name']} ({loaded} von {len(images)} Bildern)"
    if images and loaded == 0:
        message += ". Die Bilder konnten nicht geladen werden, der Bild-Server blockiert vermutlich."
    elif loaded < len(images):
        message += ". Einige Bilder fehlen."
    return _import_reply(200, message, id=item_id, name=data["name"])


@app.post("/links/check")
async def check_links(_=Depends(verify_token)):
    """Checks all links now instead of waiting for the daily run."""
    asyncio.create_task(linkcheck.run_checks(force=True))
    return {"started": True}


@app.get("/furniture")
def get_furniture(_=Depends(verify_token)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM furniture ORDER BY id DESC")  # newest first
    items = [dict(row) for row in cursor.fetchall()]
    images_by_id, tags_by_id, colors_by_id = _fetch_related(cursor)
    conn.close()

    for item in items:
        item["images"] = images_by_id.get(item["id"], [])
        item["tags"] = tags_by_id.get(item["id"], [])
        item["colors"] = colors_by_id.get(item["id"], [])
        item["used"] = bool(item["used"])
        item["link_ok"] = None if item["link_ok"] is None else bool(item["link_ok"])
        item.pop("link_fails", None)
        item.pop("image_path", None)

    return items


@app.post("/furniture")
def create_furniture(item: FurnitureItem, _=Depends(verify_token)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO furniture (name, category, subcategory, location, price, used, length, width, height)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (item.name, item.category, item.subcategory, item.location, item.price, int(item.used), item.length, item.width, item.height))
    item_id = cursor.lastrowid
    _set_tags(cursor, item_id, item.tags)
    _set_colors(cursor, item_id, item.colors)
    conn.commit()
    conn.close()
    return {"id": item_id, "message": "Furniture item created"}


@app.patch("/furniture/{item_id}")
def update_furniture(item_id: int, update: FurnitureUpdate, _=Depends(verify_token)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM furniture WHERE id = ?", (item_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    fields = {k: v for k, v in update.model_dump(exclude={"tags", "colors"}).items() if v is not None}
    if "used" in fields:
        fields["used"] = int(fields["used"])
    if "location" in fields:
        # a new link has not been checked yet
        fields.update(link_ok=None, link_status=None, link_checked_at=None, link_fails=0)
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        cursor.execute(
            f"UPDATE furniture SET {set_clause} WHERE id = ?",
            (*fields.values(), item_id)
        )

    if update.tags is not None:
        _set_tags(cursor, item_id, update.tags)

    if update.colors is not None:
        _set_colors(cursor, item_id, update.colors)

    conn.commit()
    cursor.execute("SELECT * FROM furniture WHERE id = ?", (item_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated


@app.post("/furniture/{item_id}/image")
async def upload_image(item_id: int, file: UploadFile = File(...), _=Depends(verify_token)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM furniture WHERE id = ?", (item_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    cursor.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM furniture_images WHERE furniture_id = ?",
        (item_id,)
    )
    next_position = cursor.fetchone()[0]

    ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        shutil.copyfileobj(file.file, f)

    cursor.execute(
        "INSERT INTO furniture_images (furniture_id, filename, position) VALUES (?, ?, ?)",
        (item_id, filename, next_position)
    )
    conn.commit()
    image_id = cursor.lastrowid
    conn.close()

    return {"id": image_id, "filename": filename}


class ImageColorUpdate(BaseModel):
    color: str | None = None


@app.patch("/furniture/{item_id}/image/{image_id}")
def update_image_color(item_id: int, image_id: int, body: ImageColorUpdate, _=Depends(verify_token)):
    color = body.color.strip().lower() if body.color else None
    if color is not None and not HEX_COLOR.match(color):
        raise HTTPException(status_code=422, detail="Invalid color")

    conn = get_connection()
    cursor = conn.cursor()
    if color is not None:
        cursor.execute(
            "SELECT 1 FROM furniture_colors WHERE furniture_id = ? AND color = ?", (item_id, color)
        )
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=422, detail="Color does not belong to this item")

    cursor.execute(
        "UPDATE furniture_images SET color = ? WHERE id = ? AND furniture_id = ?",
        (color, image_id, item_id)
    )
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Image not found")
    conn.commit()
    conn.close()
    return {"id": image_id, "color": color}


@app.delete("/furniture/{item_id}/image/{image_id}")
def delete_image(item_id: int, image_id: int, _=Depends(verify_token)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT filename FROM furniture_images WHERE id = ? AND furniture_id = ?",
        (image_id, item_id)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Image not found")

    filepath = os.path.join(UPLOAD_DIR, row["filename"])
    if os.path.exists(filepath):
        os.remove(filepath)

    cursor.execute("DELETE FROM furniture_images WHERE id = ?", (image_id,))
    conn.commit()
    conn.close()
    return {"message": "Image deleted"}


@app.delete("/furniture/{item_id}")
def delete_furniture(item_id: int, _=Depends(verify_token)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM furniture WHERE id = ?", (item_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    cursor.execute("SELECT filename FROM furniture_images WHERE furniture_id = ?", (item_id,))
    for img in cursor.fetchall():
        filepath = os.path.join(UPLOAD_DIR, img["filename"])
        if os.path.exists(filepath):
            os.remove(filepath)

    cursor.execute("DELETE FROM furniture_images WHERE furniture_id = ?", (item_id,))
    cursor.execute("DELETE FROM furniture_tags WHERE furniture_id = ?", (item_id,))
    cursor.execute("DELETE FROM furniture_colors WHERE furniture_id = ?", (item_id,))
    cursor.execute("DELETE FROM furniture WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return {"message": "Item deleted"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:1919",
        "https://dogtype.github.io",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
