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

    # Ensure image_path column exists (legacy)
    try:
        cursor.execute("ALTER TABLE furniture ADD COLUMN image_path TEXT")
        conn.commit()
    except Exception:
        pass

    # Create images table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS furniture_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            furniture_id INTEGER NOT NULL REFERENCES furniture(id),
            filename TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0
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

class FurnitureUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    location: str | None = None
    price: float | None = None


# -------------------------
# Routes
# -------------------------

@app.get("/")
def root():
    return {"message": "Furniture API running"}


# GET all furniture
@app.get("/furniture")
def get_furniture():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM furniture")
    items = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM furniture_images ORDER BY position, id")
    images = cursor.fetchall()
    conn.close()

    images_by_furniture = defaultdict(list)
    for img in images:
        images_by_furniture[img["furniture_id"]].append({
            "id": img["id"],
            "filename": img["filename"],
        })

    for item in items:
        item["images"] = images_by_furniture.get(item["id"], [])
        item.pop("image_path", None)

    return items


# POST new furniture item
@app.post("/furniture")
def create_furniture(item: FurnitureItem):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO furniture (name, category, location, price)
        VALUES (?, ?, ?, ?)
    """, (item.name, item.category, item.location, item.price))
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return {"id": item_id, "message": "Furniture item created"}


# PATCH update a furniture item
@app.patch("/furniture/{item_id}")
def update_furniture(item_id: int, update: FurnitureUpdate):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM furniture WHERE id = ?", (item_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    fields = {k: v for k, v in update.model_dump().items() if v is not None}
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        cursor.execute(
            f"UPDATE furniture SET {set_clause} WHERE id = ?",
            (*fields.values(), item_id)
        )
        conn.commit()

    cursor.execute("SELECT * FROM furniture WHERE id = ?", (item_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated


# POST image for a furniture item (appends, does not replace)
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


# DELETE a single image
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


# DELETE furniture item and all its images
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
