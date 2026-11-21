"""Bộ não hội thoại TechZone AI.

Gemini hiểu ý định và trích xuất thông tin khách nói.
Python xác thực, cập nhật Customer Profile, lọc sản phẩm và kiểm tra giỏ hàng.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from backend.product_service import (
    CATEGORY_FIELDS, SHARED_FIELDS, tim_san_pham, tim_san_pham_thay_the,
)


# Đọc cấu hình Gemini từ backend/.env.
duong_dan_env = Path(__file__).resolve().parent / ".env"
load_dotenv(duong_dan_env)

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("Khong tim thay GEMINI_API_KEY trong backend/.env")

client = genai.Client(api_key=api_key)
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

CATEGORIES = {"laptop", "phone", "headphone", "keyboard", "mouse"}
CATEGORY_ALIASES = {
    "laptop": "laptop",
    "máy tính xách tay": "laptop",
    "may tinh xach tay": "laptop",
    "điện thoại": "phone",
    "dien thoai": "phone",
    "phone": "phone",
    "smartphone": "phone",
    "tai nghe": "headphone",
    "headphone": "headphone",
    "bàn phím": "keyboard",
    "ban phim": "keyboard",
    "keyboard": "keyboard",
    "chuột": "mouse",
    "chuot": "mouse",
    "mouse": "mouse",
}

FIELD_ALIASES = {
    "budget": "budget_max",
    "ngan_sach": "budget_max",
    "gia_toi_da": "budget_max",
    "thuong_hieu": "brand",
    "hang": "brand",
    "ram": "ram_min",
    "ram_toi_thieu": "ram_min",
    "dung_luong": "storage_min",
    "bo_nho": "storage_min",
    "muc_dich": "usage_purpose",
    "purpose": "usage_purpose",
    "dpi": "dpi_min",
    "switch_type": "switch",
}
VALID_STATUSES = {"UNKNOWN", "ANY", "SET", "EXCLUDED"}


SYSTEM_INSTRUCTION = """
Bạn là TechZone AI, trợ lý tư vấn mua sắm công nghệ của cửa hàng TechZone.
Trả lời bằng tiếng Việt, thân thiện, tự nhiên, ngắn gọn và không hỏi dồn dập.

CÁCH HOẠT ĐỘNG
- Python đã trích xuất và cập nhật Customer Profile, đồng thời trực tiếp chạy tìm kiếm khi cần.
- Bạn KHÔNG tự tuyên bố đã tìm sản phẩm nếu phần KẾT QUẢ XỬ LÝ TỪ PYTHON không ghi search_performed=true.
- Khi search_performed=true và có sản phẩm, hãy giới thiệu ngay trong tin nhắn tối đa 3 sản phẩm tiêu biểu.
- Mỗi sản phẩm trình bày: tên, giá, một vài thông số có dữ liệu và lý do phù hợp với nhu cầu khách.
- Không nhắc website hiển thị thẻ sản phẩm; giao diện chat chỉ hiển thị nội dung tin nhắn AI.
- Khi so sánh, chỉ dùng các sản phẩm trong kết quả gần nhất Python cung cấp. Nếu khách gọi tên sản phẩm không có trong danh sách, nói rõ chưa có dữ liệu để đối chiếu và đề nghị tìm sản phẩm đó trước.
- Chỉ tư vấn sản phẩm trong dữ liệu được Python cung cấp. Không bịa tên, giá, thông số hoặc tồn kho.
- Nếu Python báo không tìm thấy sản phẩm, nói rõ và hỏi khách có muốn nới điều kiện nào không. Không tự ý bỏ điều kiện bắt buộc.
- Nếu Python yêu cầu hỏi thêm, chỉ hỏi một câu quan trọng nhất.

CUSTOMER PROFILE
- Hồ sơ gồm shared_profile và category_profiles cho laptop, phone, headphone, keyboard, mouse.
- Trạng thái tiêu chí: UNKNOWN, ANY, SET, EXCLUDED.
- SET có strength HARD (bắt buộc) hoặc SOFT (ưu tiên). EXCLUDED luôn là điều kiện loại trừ.
- Tiêu chí riêng theo danh mục không tự chuyển sang danh mục khác. Python đã xử lý phạm vi và kế thừa hồ sơ chung.
- Không nói rằng đã cập nhật tiêu chí nếu Python không xác nhận cập nhật thành công.

GIỎ HÀNG
- Nếu khách muốn thêm sản phẩm vào giỏ, chỉ dùng công cụ suggest_add_to_cart với product_id có trong dữ liệu sản phẩm được cung cấp.
- Công cụ chỉ tạo đề xuất chờ khách xác nhận trên website. Không nói đã thêm vào giỏ trước khi khách xác nhận.

SO SÁNH
- Nếu khách yêu cầu so sánh, chỉ sử dụng dữ liệu sản phẩm được Python cung cấp trong phần ngữ cảnh.
- Không suy diễn thông số còn thiếu; có thể nói rõ dữ liệu hiện không có thông tin đó.
""".strip()

EXTRACTION_INSTRUCTION = """
Bạn là bộ phân tích ý định và nhu cầu cho TECHZONE-AI. Nhiệm vụ duy nhất: đọc tin nhắn mới cùng ngữ cảnh và trả về MỘT JSON hợp lệ, không markdown, không giải thích bên ngoài JSON.

Schema:
{
  "category": "laptop|phone|headphone|keyboard|mouse|null",
  "intent": "SEARCH|ASK|UPDATE|COMPARE|CART|GENERAL",
  "should_search": true,
  "updates": [
    {
      "scope": "category|shared",
      "field": "tên_trường_hợp_lệ",
      "status": "SET|ANY|EXCLUDED",
      "value": "giá trị hoặc null",
      "strength": "HARD|SOFT|NONE",
      "excluded_values": []
    }
  ],
  "question": "một câu hỏi ngắn nếu cần hỏi thêm"
}

Quy tắc nhận diện:
1. Dùng category đã có trong ngữ cảnh nếu tin nhắn mới tiếp tục nhu cầu hiện tại. Nếu khách chuyển danh mục, trả category mới.
2. laptop: budget_max, brand, ram_min, storage_min, cpu, screen, usage_purpose.
   phone: budget_max, brand, ram_min, storage_min, screen, battery, usage_purpose.
   headphone: budget_max, brand, connection, battery, feature, usage_purpose.
   keyboard: budget_max, brand, connection, layout, switch, usage_purpose.
   mouse: budget_max, brand, connection, dpi_min, feature, usage_purpose.
   shared chỉ dùng budget_max và brand, và CHỈ khi khách nói rõ áp dụng chung cho nhiều danh mục/tất cả sản phẩm.
3. Chỉ trích xuất điều khách thực sự nói. Không tự đặt ngân sách, thương hiệu hay cấu hình.
4. Ngân sách trả về dạng số VND (ví dụ "20 triệu" => 20000000). ram_min và dpi_min trả về số ("16GB" => 16).
5. Với SET: điều kiện bắt buộc/chỉ lấy => HARD; từ "ưu tiên", "thích", "mong muốn" => SOFT. Thương hiệu nói "ưu tiên ASUS" phải là SOFT.
6. "không cần/không quan tâm/cái nào cũng được" đối với một tiêu chí => ANY.
   "không lấy/loại/tránh ASUS" => EXCLUDED, value là ASUS.
7. Giá trị connection phải chuẩn hóa theo dữ liệu sản phẩm:
   - mouse: "Wireless" hoặc "Wired".
   - headphone: "Bluetooth" hoặc "Wired".
   - keyboard: "Bluetooth" hoặc "USB-C".
   Ví dụ "chuột không dây" => connection SET "Wireless" HARD; "tai nghe không dây" => "Bluetooth"; "bàn phím không dây" => "Bluetooth".
8. "gaming" ở chuột có thể là feature="Gaming"; ở các danh mục khác nếu không có trường tương ứng thì dùng usage_purpose="gaming", không tự tạo thông số.
9. Nếu khách chỉ nêu tên danh mục, chưa nêu điều kiện/nhu cầu cụ thể: intent=ASK, should_search=false, hỏi một câu hữu ích nhất (ngân sách hoặc mục đích).
10. Nếu khách yêu cầu tư vấn/tìm/đề xuất sản phẩm và đã nêu ít nhất một điều kiện hoặc nhu cầu cụ thể (ví dụ chuột không dây, laptop dưới 20 triệu, tai nghe gaming), đặt intent=SEARCH, should_search=true. Không hỏi thêm chỉ để thu thập đủ mọi trường.
11. Nếu bot vừa hỏi khách bổ sung thông tin và khách trả lời bằng ngân sách/tiêu chí, cập nhật trường đó; đặt intent=SEARCH, should_search=true khi hồ sơ đã có tiêu chí phù hợp.
12. Nếu khách chỉ thay đổi tiêu chí mà không yêu cầu tìm lại và không phải đang trả lời câu hỏi làm rõ, dùng intent=UPDATE, should_search=false.
13. Nếu khách yêu cầu so sánh kết quả gần nhất: intent=COMPARE. Nếu muốn thêm vào giỏ: intent=CART.
14. Nếu không liên quan tư vấn sản phẩm, intent=GENERAL.
15. Không được ghi updates rỗng cho một tiêu chí chưa được nhắc tới. Không tự chuyển thông tin riêng danh mục sang shared.
""".strip()


def _parse_json_response(raw_text: str) -> dict:
    """Đọc JSON từ phản hồi trích xuất của Gemini, kể cả khi có code fence."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("Gemini không trả về JSON hợp lệ khi phân tích yêu cầu.")
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("Kết quả phân tích ý định không phải object JSON.")
    return data


def _plain_text(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def _canonicalize_extracted_value(category: str | None, field: str, value: Any) -> Any:
    """Đưa một số cách nói tự nhiên về đúng giá trị đang có trong products.json."""
    if value is None:
        return None
    if field != "connection":
        return value

    text = _plain_text(value)
    if any(token in text for token in ("khong day", "wireless", "bluetooth")):
        if category == "mouse":
            return "Wireless"
        return "Bluetooth"
    if any(token in text for token in ("co day", "wired", "usb")):
        if category == "keyboard":
            return "USB-C"
        return "Wired"
    return str(value).strip()


def _extract_customer_intent(phien_chat: dict, tin_nhan: str) -> dict:
    """Dùng Gemini để trích xuất JSON; không cho Gemini tự điều phối tìm kiếm."""
    state = phien_chat["state"]
    history = state.get("conversation_history", [])[-8:]
    history_text = "\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')}"
        for item in history
    ) or "(Chưa có hội thoại trước đó)"
    profile_text = json.dumps(state.get("customer_profile", {}), ensure_ascii=False)
    active_category = state.get("customer_profile", {}).get("active_category")

    prompt = f"""HỒ SƠ HIỆN TẠI (JSON):
{profile_text}

DANH MỤC ĐANG HOẠT ĐỘNG: {active_category or 'chưa có'}

HỘI THOẠI GẦN ĐÂY:
{history_text}

TIN NHẮN MỚI CỦA KHÁCH:
{tin_nhan}

Hãy phân tích riêng tin nhắn mới theo schema và quy tắc trong system instruction. Trả về duy nhất JSON hợp lệ."""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=EXTRACTION_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    return _parse_json_response(getattr(response, "text", "") or "")


def _contains_search_language(message: str) -> bool:
    """Nhận diện các cách yêu cầu tư vấn/tìm hàng phổ biến để tránh bỏ lỡ search."""
    text = _plain_text(message)
    phrases = (
        "tu van", "tim giup", "tim cho toi", "tim cho minh", "tim san pham",
        "goi y", "de xuat", "muon mua", "can mua", "co mau nao", "cho xem",
        "liet ke", "san pham nao", "tim lai",
    )
    return any(phrase in text for phrase in phrases)


def _has_meaningful_criteria(customer_profile: dict, category: str) -> bool:
    """True nếu hồ sơ hiệu lực có ít nhất một lựa chọn SET hoặc EXCLUDED."""
    shared = customer_profile.get("shared_profile", {})
    specific = customer_profile.get("category_profiles", {}).get(category, {})
    fields = CATEGORY_FIELDS.get(category, set())
    for field in fields:
        criterion = specific.get(field, _new_criterion())
        if str(criterion.get("status", "UNKNOWN")).upper() == "UNKNOWN" and field in SHARED_FIELDS:
            criterion = shared.get(field, _new_criterion())
        if str(criterion.get("status", "UNKNOWN")).upper() in {"SET", "EXCLUDED"}:
            return True
    return False


def _product_context(products: list[dict]) -> list[dict]:
    """Giữ lại các trường cần thiết để Gemini so sánh/nhận diện sản phẩm."""
    fields = (
        "id", "name", "category", "brand", "price", "stock", "description",
        "ram", "storage", "cpu", "screen", "battery", "connection",
        "feature", "layout", "switch", "dpi",
        "is_alternative", "alternative_mismatches",
    )
    return [
        {field: product.get(field) for field in fields if product.get(field) is not None}
        for product in products
    ]

def _chon_san_pham_gio_hang(tin_nhan: str, products: list[dict]):
    """Xác định sản phẩm khách muốn thêm từ kết quả tìm kiếm gần nhất."""

    if not products:
        return None, 1, "Chưa có danh sách sản phẩm để chọn."

    text = _plain_text(tin_nhan)

    # Nhận diện số lượng khách muốn thêm.
    quantity_match = re.search(
        r"\b(\d+)\s*(?:cai|chiec|san pham|sp)\b",
        text
    )
    quantity = int(quantity_match.group(1)) if quantity_match else 1

    # Nhận diện thứ tự sản phẩm.
    ordinal_map = {
        "dau tien": 1,
        "thu nhat": 1,
        "so mot": 1,
        "thu hai": 2,
        "thu ba": 3,
        "thu tu": 4,
        "thu nam": 5,
    }

    selected_index = None

    for phrase, number in ordinal_map.items():
        if phrase in text:
            selected_index = number
            break

    if selected_index is None:
        match = re.search(r"\b(?:thu|so|mau)\s*(\d+)\b", text)
        if match:
            selected_index = int(match.group(1))

    if selected_index is not None:
        if 1 <= selected_index <= len(products):
            return products[selected_index - 1], quantity, None

        return None, quantity, (
            f"Danh sách hiện chỉ có {len(products)} sản phẩm. "
            "Bạn hãy chọn lại thứ tự sản phẩm."
        )

    # Nếu khách gọi đúng tên sản phẩm.
    for product in products:
        name = _plain_text(product.get("name", ""))
        if name and name in text:
            return product, quantity, None

    # Chỉ tự chọn khi danh sách có đúng một sản phẩm.
    if len(products) == 1:
        return products[0], quantity, None

    return None, quantity, (
        "Bạn muốn thêm sản phẩm nào vào giỏ hàng? "
        "Hãy cho mình biết tên hoặc thứ tự sản phẩm nhé."
    )

def _normalize_category(category: str | None) -> str | None:
    if not category:
        return None
    text = str(category).strip().lower()
    return CATEGORY_ALIASES.get(text, text if text in CATEGORIES else None)


def _new_criterion() -> dict:
    return {
        "status": "UNKNOWN",
        "value": None,
        "strength": "NONE",
        "excluded_values": [],
    }


def _create_customer_profile() -> dict:
    shared = {field: _new_criterion() for field in SHARED_FIELDS}
    category_profiles = {
        category: {
            field: _new_criterion()
            for field in sorted(fields)
        }
        for category, fields in CATEGORY_FIELDS.items()
    }
    return {
        "version": 1,
        "active_category": None,
        "shared_profile": shared,
        "category_profiles": category_profiles,
    }


def _parse_list_values(raw: str | list | None) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        values = raw
    else:
        values = re.split(r"[|;,]", str(raw))
    result = []
    seen = set()
    for item in values:
        value = str(item).strip()
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    return result


def _parse_money(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip().lower().replace("đ", "").replace("vnd", "")
    match = re.search(r"(\d[\d.,]*)\s*(triệu|tr|million|k|nghìn)?", text)
    if not match:
        return None

    number_text = match.group(1)
    unit = match.group(2) or ""
    if "." in number_text or "," in number_text:
        # Các nhóm có đúng 3 chữ số phía sau dấu phân cách là dạng hàng nghìn
        # (20.000.000); nếu không thì coi dấu cuối là dấu thập phân (20,5).
        parts = re.split(r"[.,]", number_text)
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            number = float("".join(parts))
        else:
            last_separator = max(number_text.rfind("."), number_text.rfind(","))
            integer_part = re.sub(r"[.,]", "", number_text[:last_separator])
            decimal_part = number_text[last_separator + 1:]
            number = float(f"{integer_part}.{decimal_part}")
    else:
        number = float(number_text)

    if unit in {"triệu", "tr", "million"}:
        number *= 1_000_000
    elif unit in {"k", "nghìn"}:
        number *= 1_000
    return int(number)


def _coerce_field_value(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field == "budget_max":
        parsed = _parse_money(value)
        if parsed is None or parsed <= 0:
            raise ValueError("Ngân sách phải là số tiền VND lớn hơn 0.")
        return parsed
    if field in {"ram_min", "dpi_min"}:
        match = re.search(r"\d+", str(value))
        if not match:
            raise ValueError(f"Giá trị của {field} phải là số.")
        parsed = int(match.group())
        if parsed <= 0:
            raise ValueError(f"Giá trị của {field} phải lớn hơn 0.")
        return parsed
    text = str(value).strip()
    if not text:
        raise ValueError("Giá trị tiêu chí không được để trống.")
    return text


def tao_phien_chat():
    """Tạo Gemini chat cùng trạng thái riêng cho một phiên người dùng."""
    trang_thai = {
        "products": [],
        "last_search": None,
        "cart_action": None,
        "customer_profile": _create_customer_profile(),
        "conversation_history": [],
        "awaiting_criteria": False,
    }

    def set_active_category(category: str) -> dict:
        """Chọn danh mục hiện tại: laptop, phone, headphone, keyboard hoặc mouse."""
        normalized = _normalize_category(category)
        if not normalized:
            return {
                "success": False,
                "message": "Danh mục không hợp lệ. Chọn laptop, phone, headphone, keyboard hoặc mouse.",
            }

        profile = trang_thai["customer_profile"]
        profile["active_category"] = normalized
        return {
            "success": True,
            "active_category": normalized,
            "message": f"Đã chuyển sang danh mục {normalized}. Hồ sơ cũ của danh mục này vẫn được giữ.",
        }

    def update_customer_profile(
        category: str = "",
        scope: str = "category",
        field: str = "",
        status: str = "SET",
        value: str = "",
        strength: str = "HARD",
        excluded_values: str = "",
    ) -> dict:
        """Cập nhật một tiêu chí trong Customer Profile.

        Args:
            category: laptop, phone, headphone, keyboard hoặc mouse.
            scope: category hoặc shared. Chỉ dùng shared khi khách nói rõ áp dụng chung.
            field: budget_max, brand, ram_min, storage_min, cpu, screen, battery,
                connection, feature, layout, switch, dpi_min hoặc usage_purpose.
            status: UNKNOWN, ANY, SET hoặc EXCLUDED.
            value: giá trị muốn đặt; với EXCLUDED có thể là giá trị muốn loại.
            strength: HARD (bắt buộc), SOFT (ưu tiên), NONE.
            excluded_values: các giá trị cần loại trừ, ngăn cách bằng dấu |.
        """
        profile = trang_thai["customer_profile"]
        normalized_category = _normalize_category(category) or profile.get("active_category")
        normalized_scope = str(scope or "category").strip().lower()
        normalized_field = FIELD_ALIASES.get(str(field).strip().lower(), str(field).strip().lower())
        normalized_status = str(status or "SET").strip().upper()
        normalized_strength = str(strength or "HARD").strip().upper()

        if normalized_status not in VALID_STATUSES:
            return {"success": False, "message": "Trạng thái tiêu chí không hợp lệ."}
        if normalized_scope not in {"category", "shared"}:
            return {"success": False, "message": "Phạm vi phải là category hoặc shared."}

        if normalized_scope == "shared":
            if normalized_field not in SHARED_FIELDS:
                return {
                    "success": False,
                    "message": "Hồ sơ dùng chung hiện chỉ hỗ trợ budget_max và brand.",
                }
            target = profile["shared_profile"]
        else:
            if not normalized_category:
                return {
                    "success": False,
                    "message": "Chưa xác định được danh mục để cập nhật tiêu chí.",
                }
            if normalized_field not in CATEGORY_FIELDS.get(normalized_category, set()):
                return {
                    "success": False,
                    "message": f"Trường {normalized_field} không áp dụng cho danh mục {normalized_category}.",
                }
            profile["active_category"] = normalized_category
            target = profile["category_profiles"][normalized_category]

        old_criterion = target.get(normalized_field, _new_criterion())
        excluded = list(old_criterion.get("excluded_values") or [])
        new_excluded = _parse_list_values(excluded_values)

        if normalized_status in {"UNKNOWN", "ANY"}:
            # Khi khách nói không quan tâm nữa, tiêu chí cũ và danh sách loại trừ
            # của chính trường đó đều được gỡ.
            criterion = {
                "status": normalized_status,
                "value": None,
                "strength": "NONE",
                "excluded_values": [],
            }

        elif normalized_status == "EXCLUDED":
            candidates = _parse_list_values(value) + new_excluded
            if not candidates:
                return {
                    "success": False,
                    "message": "Cần có ít nhất một giá trị cụ thể để loại trừ.",
                }
            combined = _parse_list_values(excluded + candidates)
            criterion = {
                "status": "EXCLUDED",
                "value": None,
                "strength": "HARD",
                "excluded_values": combined,
            }

        else:  # SET
            try:
                parsed_value = _coerce_field_value(normalized_field, value)
            except ValueError as error:
                return {"success": False, "message": str(error)}

            if normalized_strength not in {"HARD", "SOFT"}:
                normalized_strength = "SOFT" if normalized_field == "brand" else "HARD"

            # Loại trừ trước đó vẫn được giữ khi khách chỉ đổi giá trị ưu tiên.
            combined = _parse_list_values(excluded + new_excluded)
            criterion = {
                "status": "SET",
                "value": parsed_value,
                "strength": normalized_strength,
                "excluded_values": combined,
            }

        target[normalized_field] = criterion
        return {
            "success": True,
            "message": "Đã cập nhật Customer Profile.",
            "category": normalized_category,
            "scope": normalized_scope,
            "field": normalized_field,
            "criterion": deepcopy(criterion),
        }

    def search_products(category: str = "") -> list[dict]:
        """Tìm tối đa 5 sản phẩm còn hàng theo Customer Profile hiện tại."""
        profile = trang_thai["customer_profile"]
        normalized_category = _normalize_category(category) or profile.get("active_category")

        if not normalized_category:
            trang_thai["products"] = []
            return []

        profile["active_category"] = normalized_category
        results = tim_san_pham(
            danh_muc=normalized_category,
            customer_profile=profile,
            limit=5,
        )
        search_mode = "exact"

        # Chỉ tìm phương án thay thế khi không có sản phẩm khớp đủ HARD.
        if not results:
            results = tim_san_pham_thay_the(
                danh_muc=normalized_category,
                customer_profile=profile,
                limit=5,
            )
            if results:
                search_mode = "alternative"

        trang_thai["products"] = results
        trang_thai["last_search"] = {
            "category": normalized_category,
            "products": deepcopy(results),
            "profile": deepcopy(profile),
            "search_mode": search_mode,
        }

        print(
            "TechZone AI tìm thấy:", len(results),
            "sản phẩm thay thế" if search_mode == "alternative" else "sản phẩm phù hợp",
            "thuộc", normalized_category, flush=True,
        )
        return results

    def suggest_add_to_cart(product_id: str, quantity: int = 1) -> dict:
        """Tạo đề xuất thêm sản phẩm vào giỏ, chờ khách xác nhận trên website."""
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return {"success": False, "message": "Số lượng không hợp lệ."}

        if quantity < 1:
            return {"success": False, "message": "Số lượng phải lớn hơn 0."}

        # Kiểm tra trực tiếp sản phẩm và tồn kho mới nhất trong Firestore.
        from backend.firebase_config import db
        doc = db.collection("products").document(str(product_id)).get()
        if not doc.exists:
            return {
                "success": False,
                "message": "Không tìm thấy sản phẩm hoặc sản phẩm đã hết hàng.",
            }

        san_pham = doc.to_dict() or {}
        san_pham["id"] = doc.id
        try:
            stock = int(san_pham.get("stock", 0) or 0)
        except (TypeError, ValueError):
            stock = 0

        if stock <= 0:
            return {"success": False, "message": "Sản phẩm hiện đã hết hàng."}
        if quantity > stock:
            return {
                "success": False,
                "message": f"Hiện chỉ còn {stock} sản phẩm trong kho.",
            }

        trang_thai["cart_action"] = {
            "id": str(san_pham["id"]),
            "name": san_pham.get("name", ""),
            "price": san_pham.get("price", 0),
            "stock": stock,
            "quantity": quantity,
        }
        return {
            "success": True,
            "message": "Đã tạo đề xuất. Đang chờ khách xác nhận trên website.",
            "product": trang_thai["cart_action"],
        }

    # Gemini chỉ giữ nhiệm vụ hội thoại và đề xuất giỏ hàng.
    # Cập nhật hồ sơ và tìm kiếm được Python gọi trực tiếp trong gui_tin_nhan().
    chat = client.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[suggest_add_to_cart],
        ),
    )

    return {
        "chat": chat,
        "state": trang_thai,
        "handlers": {
            "set_active_category": set_active_category,
            "update_customer_profile": update_customer_profile,
            "search_products": search_products,
            "suggest_add_to_cart": suggest_add_to_cart,
        },
    }


def gui_tin_nhan(phien_chat, tin_nhan):
    """Phân tích bằng Gemini, còn cập nhật hồ sơ/tìm kiếm do Python điều phối."""
    state = phien_chat["state"]
    handlers = phien_chat["handlers"]
    state["products"] = []
    state["cart_action"] = None

    # Bước 1: Gemini chỉ trích xuất ý định và các tiêu chí thành JSON.
    extraction = _extract_customer_intent(phien_chat, tin_nhan)
    intent = str(extraction.get("intent", "GENERAL")).strip().upper()
    if intent not in {"SEARCH", "ASK", "UPDATE", "COMPARE", "CART", "GENERAL"}:
        intent = "GENERAL"
    # Bắt yêu cầu thêm giỏ hàng bằng Python để tránh Gemini bỏ sót.
    cart_phrases = (
        "them vao gio",
        "them vao gio hang",
        "cho vao gio",
        "cho vao gio hang",
        "them san pham",
        "mua san pham nay",
    )

    normalized_message = _plain_text(tin_nhan)

    if any(phrase in normalized_message for phrase in cart_phrases):
        intent = "CART"
    category = _normalize_category(extraction.get("category"))
    if not category:
        category = state["customer_profile"].get("active_category")

    if category:
        handlers["set_active_category"](category)

    # Bước 2: Python kiểm tra và cập nhật từng tiêu chí.
    update_results = []
    updated_fields = []
    updates = extraction.get("updates", [])
    if not isinstance(updates, list):
        updates = []

    for item in updates:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", "")).strip()
        scope = str(item.get("scope", "category") or "category").strip().lower()
        status = str(item.get("status", "SET") or "SET").strip().upper()
        value = item.get("value")
        strength = str(item.get("strength", "NONE") or "NONE").strip().upper()
        excluded_values = item.get("excluded_values", [])

        if scope != "shared" and not category:
            continue
        value = _canonicalize_extracted_value(category, field, value)
        if isinstance(excluded_values, list):
            excluded_values = "|".join(str(v) for v in excluded_values)

        result = handlers["update_customer_profile"](
            category=category or "",
            scope=scope,
            field=field,
            status=status,
            value="" if value is None else str(value),
            strength=strength,
            excluded_values=str(excluded_values or ""),
        )
        update_results.append(result)
        if result.get("success"):
            updated_fields.append(field)

    profile = state["customer_profile"]
    if not category:
        category = profile.get("active_category")

    print(
        f"[TechZone NLU] intent={intent} category={category or 'none'} "
        f"updates={updated_fields}",
        flush=True,
    )

    # Bước 3: Python trực tiếp điều phối tìm kiếm, so sánh và giỏ hàng.
    products = []
    search_performed = False
    cart_result = None
    cart_selection_error = None

    search_requested = (
        bool(extraction.get("should_search"))
        or intent == "SEARCH"
        or _contains_search_language(tin_nhan)
    )

    answered_clarification = bool(
        state.get("awaiting_criteria") and updated_fields
    )

    last_search = state.get("last_search") or {}
    last_products = last_search.get("products") or []

    comparison_available = bool(last_products)

    if intent == "CART":
        # Không đưa lại danh sách 5 sản phẩm lên giao diện.
        state["products"] = []

        selected_product, quantity, selection_error = (
            _chon_san_pham_gio_hang(tin_nhan, last_products)
        )

        if selected_product:
            product_id = selected_product.get("id")

            if product_id is None:
                cart_selection_error = "Sản phẩm được chọn không có mã định danh."
            else:
                cart_result = handlers["suggest_add_to_cart"](
                    product_id=str(product_id),
                    quantity=quantity,  
                )

                if cart_result.get("success"):
                    # Frontend dùng cart_action để hiện thẻ xác nhận.
                    state["cart_action"] = cart_result.get("product")             
                else:
                    cart_selection_error = cart_result.get(
                        "message",
                        "Không thể tạo đề xuất thêm vào giỏ hàng."
                    )
        else:
            cart_selection_error = selection_error

        products = []

    elif intent == "COMPARE" and comparison_available:
        products = last_products
        state["products"] = products

    elif category and (search_requested or answered_clarification):
        if _has_meaningful_criteria(profile, category):
            print(
                f"[TechZone] Python chủ động gọi search_products cho {category}.",
                flush=True,
            )

            products = handlers["search_products"](category)
            search_performed = True
            state["awaiting_criteria"] = False
        else:
            intent = "ASK"
            state["awaiting_criteria"] = True

    elif intent == "ASK":
        state["awaiting_criteria"] = True

    elif intent == "UPDATE":
        pass

    # Nếu chưa tìm mà Gemini đang cần hỏi thêm, lấy câu hỏi gợi ý từ JSON.
    action_context = {
        "intent": intent,
        "category": category,
        "updated_fields": updated_fields,
        "update_results": [
            {"success": item.get("success"), "message": item.get("message"), "field": item.get("field")}
            for item in update_results
        ],
        "search_performed": search_performed,
        "cart_result": cart_result,
        "cart_selection_error": cart_selection_error,
        "products_found": len(products) if search_performed else None,
        "products_for_reference": _product_context(products),
        "search_mode": (state.get("last_search") or {}).get("search_mode"),
        "comparison_available": comparison_available,
        "clarifying_question": str(extraction.get("question", "") or "").strip(),
        "awaiting_criteria": state.get("awaiting_criteria", False),
    }

    # Bước 4: Gemini chỉ diễn đạt kết quả Python vừa xử lý.
    message_for_gemini = f"""TIN NHẮN GỐC CỦA KHÁCH:
{tin_nhan}

KẾT QUẢ XỬ LÝ TỪ PYTHON (DỮ LIỆU TIN CẬY):
{json.dumps(action_context, ensure_ascii=False)}

Hãy trả lời khách bằng tiếng Việt, tự nhiên và ngắn gọn theo kết quả trên.
- Nếu search_performed=true và products_found > 0: giới thiệu tối đa 3 sản phẩm đầu tiên trong products_for_reference ngay trong tin nhắn. Với mỗi sản phẩm, ghi tên, giá, các thông số quan trọng có dữ liệu và một lý do ngắn gọn gắn với nhu cầu khách. Không bịa thông số hoặc lý do không được dữ liệu hỗ trợ.
- Nếu search_performed=true và products_found=0: nói chưa có sản phẩm còn hàng trong danh mục.
- Nếu search_performed=true và search_mode=alternative: nói rõ KHÔNG có sản phẩm đáp ứng đủ mọi điều kiện bắt buộc; tối đa 3 mẫu được nêu chỉ là lựa chọn tham khảo gần nhất. Dựa vào alternative_mismatches để chỉ rõ từng mẫu lệch tiêu chí nào; tuyệt đối không gọi chúng là sản phẩm đáp ứng đầy đủ yêu cầu. Không tự ý sửa hồ sơ khách.
- Nếu intent=ASK: hỏi một câu ngắn theo clarifying_question; nếu câu đó trống, hãy hỏi ngân sách hoặc mục đích sử dụng.
- Nếu intent=UPDATE: xác nhận ngắn gọn những trường đã cập nhật; không nói đã tìm kiếm.
- Nếu intent=COMPARE và comparison_available=true: so sánh các sản phẩm trong products_for_reference. Nếu khách nêu tên cụ thể, chỉ so sánh những mẫu tương ứng; nếu không, chọn tối đa 3 mẫu tiêu biểu. Nêu khác biệt về giá và thông số có dữ liệu; không bịa thông số thiếu. Nếu search_mode=alternative, nhắc rõ đây là các lựa chọn tham khảo chưa chắc đạt đủ tiêu chí bắt buộc. Trình bày bằng tiêu đề và gạch đầu dòng dễ đọc; không dùng bảng Markdown vì giao diện chat hiển thị văn bản thuần.
- Nếu intent=COMPARE và comparison_available=false: hỏi khách muốn so sánh những sản phẩm nào hoặc đề nghị tìm sản phẩm trước.
- Nếu intent=CART và cart_result.success=true:
  Xác nhận đã tạo đề xuất thêm sản phẩm; website sẽ hiển thị phần xác nhận để khách chọn.
  Không được nói sản phẩm đã được thêm vào giỏ.
- Nếu intent=CART và cart_selection_error có nội dung:
  Thông báo ngắn gọn lỗi hoặc hỏi khách chọn sản phẩm cụ thể.
- Nếu intent=CART và cart_result.success=false:
  Thông báo lý do không thể tạo đề xuất.
- Python đã xử lý giỏ hàng, không tự gọi công cụ thêm giỏ hàng.
- Nếu updates_valid=false, không nói đã cập nhật thành công hoặc đã tìm kiếm; giải thích ngắn gọn lỗi và hỏi lại thông tin bị lỗi.
- Không nhắc tới JSON, công cụ nội bộ hoặc chi tiết triển khai.
"""

    phan_hoi = phien_chat["chat"].send_message(message_for_gemini)
    reply = getattr(phan_hoi, "text", None) or "Xin lỗi, mình chưa thể trả lời câu hỏi này."

    # Lưu lịch sử ngắn để lần trích xuất sau hiểu được câu trả lời theo ngữ cảnh.
    history = state.setdefault("conversation_history", [])
    history.append({"role": "user", "content": str(tin_nhan)})
    history.append({"role": "assistant", "content": str(reply)})
    state["conversation_history"] = history[-16:]

    return {
        "reply": reply,
        "products": state["products"],
        "cart_action": state["cart_action"],
    }
