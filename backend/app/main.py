# app/main.py

import os
import uuid
import shutil
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.db import get_connection
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/furniture")
def get_furniture():
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
def create_furniture(item: FurnitureItem):
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
def update_furniture(item_id: int, update: FurnitureUpdate):
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
async def upload_image(item_id: int, file: UploadFile = File(...)):
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
def delete_image(item_id: int, image_id: int):
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
def delete_furniture(item_id: int):
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
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
