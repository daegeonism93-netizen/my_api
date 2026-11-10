import os

import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from postgrest.exceptions import APIError
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
    allow_origin_regex=os.getenv("FRONT_ORIGIN_REGEX") or None,  # 예: https://.*\.vercel\.app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(APIError)
async def supabase_error_handler(request: Request, exc: APIError):
    """Supabase(DB) 쪽 오류를 읽기 쉬운 503 응답으로 바꿔 줍니다."""
    detail = str(exc)
    if "PGRST205" in detail or "Could not find the table" in detail:
        detail = "DB 표가 없어요. Supabase SQL Editor에서 supabase_shop.sql 을 먼저 실행하세요."
    return JSONResponse(status_code=503, content={"detail": detail})

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


# ───────────────────────── 두리샵: 상품 + 장바구니 ─────────────────────────
# 로그인 없이 쓰는 데모라서, 브라우저가 만든 랜덤 cart_id(장바구니 번호)로 장바구니를 구분해요.
FREE_SHIPPING_FROM = 30000  # 이 금액 이상이면 배송비 무료
SHIPPING_FEE = 3000
MAX_QTY = 99
CART_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
CART_SELECT = "id, quantity, product_id, products(id, name, price, emoji, category)"


class CartAdd(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=MAX_QTY)


class CartQty(BaseModel):
    quantity: int = Field(ge=0, le=MAX_QTY)  # 0 이면 삭제


def check_cart_id(cart_id: str) -> str:
    if not CART_ID_RE.match(cart_id):
        raise HTTPException(status_code=400, detail="cart_id 형식이 올바르지 않습니다")
    return cart_id


def load_cart(cart_id: str) -> dict:
    """장바구니 내용 + 금액 계산(서버가 계산해서 화면과 DB 값이 어긋나지 않게)"""
    rows = (
        sb.table("cart_items").select(CART_SELECT).eq("cart_id", cart_id).order("id").execute().data
    )
    items = []
    for r in rows:
        p = r.get("products")
        if not p:
            continue
        items.append(
            {
                "id": r["id"],
                "product_id": r["product_id"],
                "name": p["name"],
                "emoji": p["emoji"],
                "category": p["category"],
                "price": p["price"],
                "quantity": r["quantity"],
                "line_total": p["price"] * r["quantity"],
            }
        )
    subtotal = sum(i["line_total"] for i in items)
    shipping = 0 if (subtotal == 0 or subtotal >= FREE_SHIPPING_FROM) else SHIPPING_FEE
    return {
        "items": items,
        "total_qty": sum(i["quantity"] for i in items),
        "subtotal": subtotal,
        "shipping": shipping,
        "total": subtotal + shipping,
        "free_shipping_from": FREE_SHIPPING_FROM,
    }


@app.get("/products")
def list_products(category: str | None = None):
    q = sb.table("products").select("*").order("id")
    if category:
        q = q.eq("category", category)
    return q.execute().data


@app.get("/cart/{cart_id}")
def get_cart(cart_id: str):
    return load_cart(check_cart_id(cart_id))


@app.post("/cart/{cart_id}/items", status_code=201)
def add_to_cart(cart_id: str, body: CartAdd):
    check_cart_id(cart_id)
    if not sb.table("products").select("id").eq("id", body.product_id).execute().data:
        raise HTTPException(status_code=404, detail="없는 상품입니다")
    found = (
        sb.table("cart_items")
        .select("id, quantity")
        .eq("cart_id", cart_id)
        .eq("product_id", body.product_id)
        .execute()
        .data
    )
    if found:  # 이미 담겨 있으면 수량만 늘려요
        qty = min(found[0]["quantity"] + body.quantity, MAX_QTY)
        sb.table("cart_items").update({"quantity": qty}).eq("id", found[0]["id"]).execute()
    else:
        sb.table("cart_items").insert(
            {"cart_id": cart_id, "product_id": body.product_id, "quantity": body.quantity}
        ).execute()
    return load_cart(cart_id)


@app.patch("/cart/{cart_id}/items/{item_id}")
def set_quantity(cart_id: str, item_id: int, body: CartQty):
    check_cart_id(cart_id)
    q = sb.table("cart_items")
    if body.quantity == 0:
        q.delete().eq("id", item_id).eq("cart_id", cart_id).execute()
    else:
        res = q.update({"quantity": body.quantity}).eq("id", item_id).eq("cart_id", cart_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="장바구니에 없는 상품입니다")
    return load_cart(cart_id)


@app.delete("/cart/{cart_id}/items/{item_id}")
def remove_item(cart_id: str, item_id: int):
    check_cart_id(cart_id)
    sb.table("cart_items").delete().eq("id", item_id).eq("cart_id", cart_id).execute()
    return load_cart(cart_id)


@app.delete("/cart/{cart_id}")
def clear_cart(cart_id: str):
    check_cart_id(cart_id)
    sb.table("cart_items").delete().eq("cart_id", cart_id).execute()
    return load_cart(cart_id)
