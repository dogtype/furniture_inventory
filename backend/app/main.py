# app/main.py

import os
import uuid
import shutil
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import re
import httpx
import jwt
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app import scraper
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
    images_by_id, tags_by_id, colors_by_id = _fetch_related(cursor)
    conn.close()

    for item in items:
        item["images"] = images_by_id.get(item["id"], [])
        item["tags"] = tags_by_id.get(item["id"], [])
        item["colors"] = colors_by_id.get(item["id"], [])
        item["used"] = bool(item["used"])
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
