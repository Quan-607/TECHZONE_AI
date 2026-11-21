"""main.py"""

from backend.firebase_config import db
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from uuid import uuid4

from backend.chatbot import tao_phien_chat, gui_tin_nhan

app = FastAPI(title="TechZone AI API")

# Cho phép frontend gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:5501",
        "http://localhost:5501"
        "https://quan-607.github.io"
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"]
)

# Lưu các phiên chat trong bộ nhớ
cac_phien_chat = {}

# Cấu trúc dữ liệu gửi từ website
class TinNhan(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


@app.get("/")
def home():
    return {"message": "TechZone AI Backend is running!"}



@app.post("/chat")
def chat_api(du_lieu: TinNhan):

    # Tạo phiên chat mới nếu chưa có
    if du_lieu.session_id is None:
        session_id = str(uuid4())
        cac_phien_chat[session_id] = tao_phien_chat()

    else:
        session_id = du_lieu.session_id

        if session_id not in cac_phien_chat:
            raise HTTPException(
                status_code=404,
                detail="Phien chat khong ton tai."
            )

    # Lấy phiên hội thoại
    phien_chat = cac_phien_chat[session_id]

    try:
        tra_loi = gui_tin_nhan(
            phien_chat,
            du_lieu.message
        )

    except Exception:
        import traceback

        print("\n===== LOI CHATBOT =====", flush=True)
        traceback.print_exc()
        print("======================\n", flush=True)

        raise HTTPException(
            status_code=503,
            detail="Chatbot gap loi. Kiem tra Terminal FastAPI."
        )

    return {
        "session_id": session_id,
        "reply": tra_loi["reply"],
        "products": tra_loi["products"],
        "cart_action": tra_loi["cart_action"]
    }

# API lấy danh sách sản phẩm từ Firebase
@app.get("/products")
def lay_danh_sach_san_pham():
    danh_sach = []

    # Lấy tất cả sản phẩm từ Firestore
    san_pham_ref = db.collection("products").stream()

    for san_pham in san_pham_ref:
        du_lieu = san_pham.to_dict()
        du_lieu["id"] = san_pham.id

        danh_sach.append(du_lieu)

    return {
        "total": len(danh_sach),
        "products": danh_sach
    }


@app.get("/products/{product_id}")
def lay_chi_tiet_san_pham(product_id: str):
    san_pham = (
        db.collection("products")
        .document(product_id)
        .get()
    )

    if not san_pham.exists:
        raise HTTPException(
            status_code=404,
            detail="San pham khong ton tai."
        )

    du_lieu = san_pham.to_dict()
    du_lieu["id"] = san_pham.id

    return du_lieu
