"""Các hàm lọc sản phẩm cho TechZone AI.

Nguyên tắc:
- Python chịu trách nhiệm lọc dữ liệu thật từ Firestore.
- HARD là điều kiện bắt buộc.
- SOFT chỉ đưa sản phẩm khớp sở thích lên trước; không loại sản phẩm khác.
- Không dùng điểm số hoặc trọng số.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from backend.firebase_config import db


CATEGORY_FIELDS = {
    "laptop": {
        "budget_max", "brand", "ram_min", "storage_min",
        "cpu", "screen", "usage_purpose",
    },
    "phone": {
        "budget_max", "brand", "ram_min", "storage_min",
        "screen", "battery", "usage_purpose",
    },
    "headphone": {
        "budget_max", "brand", "connection", "battery",
        "feature", "usage_purpose",
    },
    "keyboard": {
        "budget_max", "brand", "connection", "layout",
        "switch", "usage_purpose",
    },
    "mouse": {
        "budget_max", "brand", "connection", "dpi_min",
        "feature", "usage_purpose",
    },
}

SHARED_FIELDS = {"budget_max", "brand"}


def _normal_text(value: Any) -> str:
    """Chuẩn hóa văn bản để so khớp không phân biệt hoa/thường và dấu."""
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _criterion(profile: dict, field: str) -> dict:
    value = profile.get(field)
    if isinstance(value, dict):
        return value
    return {"status": "UNKNOWN", "value": None, "strength": "NONE", "excluded_values": []}


def lay_ho_so_hieu_luc(customer_profile: dict | None, category: str) -> dict:
    """Gộp hồ sơ chung và hồ sơ danh mục.

    Giá trị riêng của danh mục ghi đè giá trị chung. Chỉ khi tiêu chí riêng
    còn UNKNOWN thì mới kế thừa tiêu chí chung.
    """
    if not isinstance(customer_profile, dict):
        return {}

    shared = customer_profile.get("shared_profile") or {}
    categories = customer_profile.get("category_profiles") or {}
    specific = categories.get(category) or {}

    effective = {}
    allowed_fields = CATEGORY_FIELDS.get(category, set())

    for field in allowed_fields:
        local = _criterion(specific, field)
        inherited = _criterion(shared, field) if field in SHARED_FIELDS else _criterion({}, field)

        if str(local.get("status", "UNKNOWN")).upper() == "UNKNOWN":
            effective[field] = inherited
            continue

        # Giá trị riêng ghi đè ưu tiên chung. Tuy nhiên, danh sách loại trừ
        # đã được khách xác định là áp dụng chung vẫn tiếp tục được tôn trọng.
        if field == "brand":
            shared_excluded = inherited.get("excluded_values") or []
            local_excluded = local.get("excluded_values") or []
            combined_excluded = []
            seen = set()
            for value in [*shared_excluded, *local_excluded]:
                key = _normal_text(value)
                if key and key not in seen:
                    seen.add(key)
                    combined_excluded.append(value)
            local = {**local, "excluded_values": combined_excluded}

        effective[field] = local

    return effective


def _number(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", str(value).replace(",", "."))
    if not match:
        return None
    try:
        return float(match.group().replace(",", "."))
    except ValueError:
        return None


def _capacity_gb(value: Any) -> float | None:
    """Đổi dung lượng dạng 512GB / 1TB sang GB để so sánh."""
    if value is None:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(tb|gb)", str(value), re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    return amount * 1024 if unit == "tb" else amount


def _matches_text(actual: Any, expected: Any) -> bool:
    actual_text = _normal_text(actual)
    expected_text = _normal_text(expected)
    if not actual_text or not expected_text:
        return False
    return expected_text in actual_text


def _matches_value(product: dict, field: str, expected: Any) -> bool:
    """Kiểm tra một điều kiện SET trên dữ liệu sản phẩm."""
    if field == "budget_max":
        price = _number(product.get("price"))
        budget = _number(expected)
        return price is not None and budget is not None and price <= budget

    if field == "ram_min":
        actual = _number(product.get("ram"))
        minimum = _number(expected)
        return actual is not None and minimum is not None and actual >= minimum

    if field == "storage_min":
        actual = _capacity_gb(product.get("storage"))
        minimum = _capacity_gb(expected)
        return actual is not None and minimum is not None and actual >= minimum

    if field == "dpi_min":
        actual = _number(product.get("dpi"))
        minimum = _number(expected)
        return actual is not None and minimum is not None and actual >= minimum

    product_field = "brand" if field == "brand" else field
    actual = product.get(product_field)

    if field == "brand":
        return _normal_text(actual) == _normal_text(expected)

    return _matches_text(actual, expected)


def _excluded(product: dict, field: str, criterion: dict) -> bool:
    """True nếu sản phẩm có giá trị nằm trong danh sách khách loại trừ."""
    if field == "usage_purpose":
        return False

    values = criterion.get("excluded_values") or []
    if isinstance(values, str):
        values = [values]
    if str(criterion.get("status", "")).upper() == "EXCLUDED":
        value = criterion.get("value")
        if value not in (None, ""):
            values = [*values, value]

    for excluded_value in values:
        if field == "brand":
            if _normal_text(product.get("brand")) == _normal_text(excluded_value):
                return True
        elif _matches_text(product.get(field), excluded_value):
            return True
    return False


def _passes_hard_filters(product: dict, effective_profile: dict) -> bool:
    for field in sorted(effective_profile):
        criterion = effective_profile[field]
        if not isinstance(criterion, dict):
            continue

        status = str(criterion.get("status", "UNKNOWN")).upper()
        strength = str(criterion.get("strength", "NONE")).upper()

        if _excluded(product, field, criterion):
            return False

        if status != "SET" or strength != "HARD":
            continue

        # Mục đích sử dụng được lưu để giữ ngữ cảnh tư vấn, không phải trường
        # dữ liệu sản phẩm nên không dùng làm điều kiện lọc.
        if field == "usage_purpose":
            continue

        if not _matches_value(product, field, criterion.get("value")):
            return False

    return True


def _soft_preference_key(product: dict, effective_profile: dict) -> tuple:
    """Khóa sắp xếp theo thứ tự ưu tiên, không tính điểm.

    Sản phẩm khớp sở thích SOFT được xếp trước; sau đó vẫn sắp xếp theo giá.
    """
    preference_matches = []
    for field in sorted(effective_profile):
        criterion = effective_profile[field]
        if not isinstance(criterion, dict):
            continue
        if (
            str(criterion.get("status", "UNKNOWN")).upper() == "SET"
            and str(criterion.get("strength", "NONE")).upper() == "SOFT"
            and field != "usage_purpose"
        ):
            preference_matches.append(
                0 if _matches_value(product, field, criterion.get("value")) else 1
            )

    price = _number(product.get("price"))
    return (*preference_matches, price if price is not None else float("inf"))


def tim_san_pham(
    danh_muc=None,
    gia_toi_da=None,
    thuong_hieu=None,
    ram_toi_thieu=None,
    customer_profile=None,
    limit=3,
):
    """Lấy sản phẩm còn hàng, lọc HARD, ưu tiên SOFT rồi sắp giá tăng dần.

    Các tham số gia_toi_da / thuong_hieu / ram_toi_thieu được giữ để tương
    thích với cách gọi cũ. Khi dùng Customer Profile, không cần truyền chúng.
    """
    ket_qua = []
    category = str(danh_muc or "").strip().lower()
    effective_profile = lay_ho_so_hieu_luc(customer_profile, category)

    # Tương thích với những nơi còn gọi hàm bằng tham số cũ.
    if gia_toi_da is not None:
        effective_profile["budget_max"] = {
            "status": "SET", "value": gia_toi_da,
            "strength": "HARD", "excluded_values": [],
        }
    if thuong_hieu:
        effective_profile["brand"] = {
            "status": "SET", "value": thuong_hieu,
            "strength": "HARD", "excluded_values": [],
        }
    if ram_toi_thieu is not None:
        effective_profile["ram_min"] = {
            "status": "SET", "value": ram_toi_thieu,
            "strength": "HARD", "excluded_values": [],
        }

    san_pham_ref = db.collection("products").stream()

    for san_pham in san_pham_ref:
        du_lieu = san_pham.to_dict() or {}
        du_lieu["id"] = san_pham.id

        if category and str(du_lieu.get("category", "")).lower() != category:
            continue

        # Luôn bỏ qua sản phẩm hết hàng.
        try:
            if float(du_lieu.get("stock", 0) or 0) <= 0:
                continue
        except (TypeError, ValueError):
            continue

        if not _passes_hard_filters(du_lieu, effective_profile):
            continue

        ket_qua.append(du_lieu)

    ket_qua.sort(key=lambda product: _soft_preference_key(product, effective_profile))

    try:
        result_limit = max(1, min(int(limit), 3))
    except (TypeError, ValueError):
        result_limit = 3

    return ket_qua[:result_limit]


def tim_san_pham_thay_the(
    danh_muc: str,
    customer_profile: dict | None = None,
    limit: int = 3,
) -> list[dict]:
    """Tìm lựa chọn gần nhất khi không có kết quả khớp đủ HARD.

    Không bao giờ bỏ qua các giá trị khách đã loại trừ. Các điều kiện HARD
    được dùng để ghi rõ điểm chưa khớp, không giả vờ rằng sản phẩm đáp ứng
    đầy đủ yêu cầu. Ưu tiên sản phẩm vi phạm ít điều kiện bắt buộc nhất.
    """
    category = str(danh_muc or "").strip().lower()
    effective_profile = lay_ho_so_hieu_luc(customer_profile, category)
    candidates = []

    for snapshot in db.collection("products").stream():
        product = snapshot.to_dict() or {}
        product["id"] = snapshot.id

        if category and str(product.get("category", "")).lower() != category:
            continue
        try:
            if float(product.get("stock", 0) or 0) <= 0:
                continue
        except (TypeError, ValueError):
            continue

        # Điều kiện loại trừ là tuyệt đối, không được nới lỏng khi tìm thay thế.
        if any(_excluded(product, field, criterion)
               for field, criterion in effective_profile.items()
               if isinstance(criterion, dict)):
            continue

        mismatches = []
        for field in sorted(effective_profile):
            criterion = effective_profile[field]
            if not isinstance(criterion, dict):
                continue
            if (str(criterion.get("status", "UNKNOWN")).upper() != "SET"
                    or str(criterion.get("strength", "NONE")).upper() != "HARD"
                    or field == "usage_purpose"):
                continue
            expected = criterion.get("value")
            if not _matches_value(product, field, expected):
                actual_field = "price" if field == "budget_max" else field
                actual = product.get(actual_field)
                mismatches.append({
                    "field": field,
                    "expected": expected,
                    "actual": actual,
                })

        product["is_alternative"] = bool(mismatches)
        product["alternative_mismatches"] = mismatches
        candidates.append((len(mismatches), _soft_preference_key(product, effective_profile), product))

    # Ưu tiên ít điều kiện HARD chưa khớp nhất, sau đó theo SOFT và giá.
    candidates.sort(key=lambda item: (item[0], item[1]))
    try:
        result_limit = max(1, min(int(limit), 3))
    except (TypeError, ValueError):
        result_limit = 3
    return [item[2] for item in candidates[:result_limit]]
