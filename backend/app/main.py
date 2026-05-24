# app/main.py

import os
import uuid
import shutil
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import json
import re
import httpx
import jwt
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.db import get_connection
from fastapi.middleware.cors import CORSMiddleware

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
APP_PASSWORD = os.getenv("APP_PASSWORD", "changeme")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()


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

    # Ensure legacy image_path column exists
    try:
        cursor.execute("ALTER TABLE furniture ADD COLUMN image_path TEXT")
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

    # Tags table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS furniture_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            furniture_id INTEGER NOT NULL REFERENCES furniture(id),
            tag TEXT NOT NULL
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
    yield


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
    location: str
    price: float
    tags: list[str] = []

class FurnitureUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    location: str | None = None
    price: float | None = None
    tags: list[str] | None = None


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


def _fetch_related(cursor):
    cursor.execute("SELECT * FROM furniture_images ORDER BY position, id")
    images_rows = cursor.fetchall()
    cursor.execute("SELECT * FROM furniture_tags ORDER BY id")
    tags_rows = cursor.fetchall()

    images_by_id = defaultdict(list)
    for img in images_rows:
        images_by_id[img["furniture_id"]].append({"id": img["id"], "filename": img["filename"]})

    tags_by_id = defaultdict(list)
    for t in tags_rows:
        tags_by_id[t["furniture_id"]].append(t["tag"])

    return images_by_id, tags_by_id


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
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
        response.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Seite konnte nicht geladen werden: {e}")

    soup = BeautifulSoup(response.text, "html.parser")
    name = category = location = image_url = ""
    price = 0.0
    tags: list[str] = []

    # 1. JSON-LD structured data (schema.org Product + BreadcrumbList)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")

            # collect all nodes (handle @graph, list, or single object)
            nodes = []
            if isinstance(data, dict) and "@graph" in data:
                nodes = data["@graph"]
            elif isinstance(data, list):
                nodes = data
            else:
                nodes = [data]

            for node in nodes:
                t = node.get("@type", "")

                if t == "Product":
                    name = name or str(node.get("name", ""))
                    category = category or str(node.get("category", ""))
                    brand = node.get("brand", {})
                    location = location or (brand.get("name", "") if isinstance(brand, dict) else str(brand))
                    offers = node.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    if not price and offers.get("price"):
                        try:
                            price = float(str(offers["price"]).replace(",", "."))
                        except (ValueError, TypeError):
                            pass
                    # image
                    img = node.get("image", "")
                    if isinstance(img, list): img = img[0] if img else ""
                    if isinstance(img, dict): img = img.get("url", "")
                    image_url = image_url or str(img)
                    # keywords → tags
                    kw = node.get("keywords", "")
                    if isinstance(kw, str) and kw:
                        tags = tags or [k.strip() for k in kw.split(",") if k.strip()]
                    elif isinstance(kw, list):
                        tags = tags or [str(k).strip() for k in kw if k]

                elif t == "BreadcrumbList" and not tags:
                    items = node.get("itemListElement", [])
                    # skip first (home) and last (product itself)
                    crumbs = [i.get("name", "").strip() for i in items[1:-1] if i.get("name")]
                    tags = tags or crumbs

        except Exception:
            continue

    # 2. Open Graph meta tags
    def meta(prop):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return tag.get("content", "").strip() if tag else ""

    name = name or meta("og:title") or meta("twitter:title")
    location = location or meta("og:site_name")
    image_url = image_url or meta("og:image")

    # meta keywords fallback for tags
    if not tags:
        kw = meta("keywords")
        if kw:
            tags = [k.strip() for k in kw.split(",") if k.strip()]

    # 3. Plain HTML fallbacks
    if not name:
        h1 = soup.find("h1")
        name = h1.get_text(strip=True) if h1 else ""
    if not name:
        title = soup.find("title")
        name = title.get_text(strip=True).split("|")[0].split("-")[0].strip() if title else ""

    # 4. Price heuristic
    if not price:
        match = re.search(r'(\d{1,5}[.,]\d{2})\s*€|€\s*(\d{1,5}[.,]\d{2})', soup.get_text())
        if match:
            raw = (match.group(1) or match.group(2)).replace(",", ".")
            try:
                price = float(raw)
            except ValueError:
                pass

    if not name:
        raise HTTPException(status_code=422, detail="Keine Produktdaten gefunden – die Seite ist möglicherweise JavaScript-gerendert")

    return {"name": name, "category": category, "price": price, "location": url, "image_url": image_url, "tags": tags}


class ImageUrlRequest(BaseModel):
    url: str


@app.post("/furniture/{item_id}/image-url")
async def upload_image_from_url(item_id: int, body: ImageUrlRequest, _=Depends(verify_token)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM furniture WHERE id = ?", (item_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            r = await client.get(body.url, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=422, detail=f"Bild konnte nicht geladen werden: {e}")

    content_type = r.headers.get("content-type", "image/jpeg")
    ext = "." + content_type.split("/")[-1].split(";")[0].strip() if "/" in content_type else ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"

    filename = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        f.write(r.content)

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


@app.get("/furniture")
def get_furniture(_=Depends(verify_token)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM furniture")
    items = [dict(row) for row in cursor.fetchall()]
    images_by_id, tags_by_id = _fetch_related(cursor)
    conn.close()

    for item in items:
        item["images"] = images_by_id.get(item["id"], [])
        item["tags"] = tags_by_id.get(item["id"], [])
        item.pop("image_path", None)

    return items


@app.post("/furniture")
def create_furniture(item: FurnitureItem, _=Depends(verify_token)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO furniture (name, category, location, price)
        VALUES (?, ?, ?, ?)
    """, (item.name, item.category, item.location, item.price))
    item_id = cursor.lastrowid
    _set_tags(cursor, item_id, item.tags)
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

    fields = {k: v for k, v in update.model_dump(exclude={"tags"}).items() if v is not None}
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        cursor.execute(
            f"UPDATE furniture SET {set_clause} WHERE id = ?",
            (*fields.values(), item_id)
        )

    if update.tags is not None:
        _set_tags(cursor, item_id, update.tags)

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
    cursor.execute("DELETE FROM furniture WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return {"message": "Item deleted"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://dogtype.github.io",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
