
"""Cấu hình kết nối Firebase Firestore."""

from pathlib import Path
import json
import os

import firebase_admin
from firebase_admin import credentials, firestore


def khoi_tao_firebase():
    if firebase_admin._apps:
        return firestore.client()

    # Ưu tiên thông tin xác thực từ biến môi trường trên Render.
    firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

    if firebase_json:
        try:
            thong_tin_key = json.loads(firebase_json)
        except json.JSONDecodeError as error:
            raise ValueError(
                "FIREBASE_SERVICE_ACCOUNT_JSON không phải JSON hợp lệ."
            ) from error

        cred = credentials.Certificate(thong_tin_key)

    else:
        # Nếu chạy local, tiếp tục sử dụng file JSON như trước.
        duong_dan_key = (
            Path(__file__).resolve().parent / "serviceAccountKey.json"
        )

        if not duong_dan_key.exists():
            raise FileNotFoundError(
                "Không tìm thấy cấu hình Firebase. "
                "Hãy kiểm tra serviceAccountKey.json hoặc "
                "FIREBASE_SERVICE_ACCOUNT_JSON."
            )

        cred = credentials.Certificate(str(duong_dan_key))

    firebase_admin.initialize_app(cred)
    print("Ket noi Firebase thanh cong!")

    return firestore.client()


db = khoi_tao_firebase()
