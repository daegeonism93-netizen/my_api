import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# 로컬에선 .env를 읽고, Railway에선 Variables가 이미 들어 있음
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

# 허용할 프론트 주소 (쉼표로 구분). 비어 있으면 로컬 개발 주소만 허용
_default_origins = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500,http://127.0.0.1:5500"
FRONT_ORIGINS = [
    o.strip()
    for o in (os.getenv("FRONT_ORIGINS") or _default_origins).split(",")
    if o.strip()
]

sb = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

app = FastAPI(title="my-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONT_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TABLE = "todos"


class TodoIn(BaseModel):
    title: str


class TodoUpdate(BaseModel):
    title: str | None = None
    done: bool | None = None


@app.get("/")
def root():
    """주소 맨 끝이 비어 있을 때(127.0.0.1:8000) 보여주는 안내"""
    return {
        "message": "my-api 서버가 켜져 있어요",
        "docs": "/docs",
        "health": "/health",
        "todos": "/todos",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    """Supabase 연결 + todos 테이블 존재 여부 확인"""
    try:
        sb.table(TABLE).select("id").limit(1).execute()
        return {"status": "ok", "supabase": "connected", "table": TABLE}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Supabase 오류: {e}")


@app.get("/todos")
def list_todos():
    res = sb.table(TABLE).select("*").order("id", desc=True).execute()
    return res.data


@app.post("/todos", status_code=201)
def create_todo(body: TodoIn):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title이 비어 있습니다")
    res = sb.table(TABLE).insert({"title": title}).execute()
    return res.data[0]


@app.patch("/todos/{todo_id}")
def update_todo(todo_id: int, body: TodoUpdate):
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="수정할 값이 없습니다")
    res = sb.table(TABLE).update(patch).eq("id", todo_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="없는 todo입니다")
    return res.data[0]


@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int):
    sb.table(TABLE).delete().eq("id", todo_id).execute()
