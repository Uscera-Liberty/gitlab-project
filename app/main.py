import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status

from app.db import get_conn, init_db
from app.models import User, UserCreate, UserUpdate


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Users CRUD API", version="1.0.0", lifespan=lifespan)


def fetch_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {user_id} not found")
    return row


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/users", response_model=list[User])
def list_users(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_conn),
):
    rows = conn.execute(
        "SELECT * FROM users ORDER BY id LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    return dict(fetch_user(conn, user_id))


@app.post("/users", response_model=User, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, conn: sqlite3.Connection = Depends(get_conn)):
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, role) VALUES (?, ?, ?)",
            (data.name, data.email, data.role),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")
    return dict(fetch_user(conn, cur.lastrowid))


@app.put("/users/{user_id}", response_model=User)
def update_user(user_id: int, data: UserUpdate, conn: sqlite3.Connection = Depends(get_conn)):
    fetch_user(conn, user_id)
    changes = data.model_dump(exclude_none=True)
    if changes:
        # Имена колонок берутся из модели UserUpdate, а не из ввода пользователя
        assignments = ", ".join(f"{col} = ?" for col in changes)
        try:
            conn.execute(
                f"UPDATE users SET {assignments} WHERE id = ?",
                (*changes.values(), user_id),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")
    return dict(fetch_user(conn, user_id))


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    fetch_user(conn, user_id)
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
