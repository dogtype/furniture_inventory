# app/main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.db import get_connection
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# -------------------------
# Data Model
# -------------------------

class FurnitureItem(BaseModel):
    name: str
    category: str
    location: str
    price: float


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
    rows = cursor.fetchall()

    conn.close()

    return [dict(row) for row in rows]


# POST new furniture item
@app.post("/furniture")
def create_furniture(item: FurnitureItem):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO furniture (name, category, location, price)
        VALUES (?, ?, ?, ?)
    """, (
        item.name,
        item.category,
        item.location,
        item.price
    ))

    conn.commit()

    item_id = cursor.lastrowid

    conn.close()

    return {
        "id": item_id,
        "message": "Furniture item created"
    }


# DELETE furniture item
@app.delete("/furniture/{item_id}")
def delete_furniture(item_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM furniture WHERE id = ?",
        (item_id,)
    )

    conn.commit()

    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="Item not found"
        )

    conn.close()

    return {"message": "Item deleted"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)