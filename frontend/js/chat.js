const API_URL = "https://techzone-ai-api.onrender.com/chat";
const PRODUCT_API_URL = "https://techzone-ai-api.onrender.com";

// Lấy các thành phần HTML
const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const suggestionButtons = document.querySelectorAll(".suggestion-btn"); 

// Lưu phiên chat trong tab trình duyệt hiện tại
let sessionId = sessionStorage.getItem("techzone_session_id");

// Trạng thái gửi tin nhắn
let dangGui = false;
let deXuatDangCho = null;

// Hàm hiển thị tin nhắn
function hienThiTinNhan(noiDung, nguoiGui) {
    const message = document.createElement("div");
    message.className = `message ${nguoiGui}`;

    const content = document.createElement("div");
    content.className = "message-content";

    // Dùng textContent để hiển thị nội dung an toàn
    content.textContent = noiDung;

    // Giữ các dấu xuống dòng trong phản hồi AI
    content.style.whiteSpace = "pre-line";

    message.appendChild(content);
    chatMessages.appendChild(message);

    // Tự động cuộn xuống tin nhắn mới nhất
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return message;
}



// Vô hiệu hóa đề xuất cũ khi khách gửi tin nhắn mới
function voHieuHoaDeXuatCu() {
    if (!deXuatDangCho) return;

    deXuatDangCho.status.textContent =
        "Đề xuất đã hết hiệu lực vì bạn gửi tin nhắn mới.";

    deXuatDangCho.confirmButton.disabled = true;
    deXuatDangCho.cancelButton.disabled = true;

    deXuatDangCho = null;
}


// Hiển thị đề xuất thêm sản phẩm vào giỏ hàng
function hienThiDeXuatGioHang(action) {
    if (!action || !action.id) return;

    const card = document.createElement("div");
    card.className = "card border-primary shadow-sm mt-3";

    const body = document.createElement("div");
    body.className = "card-body";

    const title = document.createElement("h6");
    title.className = "fw-bold";
    title.textContent = "🛒 Đề xuất thêm vào giỏ hàng";

    const name = document.createElement("p");
    name.className = "mb-1";
    name.textContent = action.name || "Sản phẩm";

    const quantity = document.createElement("p");
    quantity.className = "mb-1";
    quantity.textContent =
        `Số lượng: ${action.quantity}`;

    const price = document.createElement("p");
    price.className = "text-primary fw-bold mb-2";
    price.textContent =
        Number(action.price).toLocaleString("vi-VN") + "đ";

    const status = document.createElement("p");
    status.className = "small text-muted mb-3";
    status.textContent =
        "Bạn có muốn thêm sản phẩm này vào giỏ hàng không?";

    const confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.className = "btn btn-primary btn-sm me-2";
    confirmButton.textContent = "Xác nhận";

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "btn btn-outline-secondary btn-sm";
    cancelButton.textContent = "Hủy";

    body.append(
        title,
        name,
        quantity,
        price,
        status,
        confirmButton,
        cancelButton
    );

    card.appendChild(body);
    chatMessages.appendChild(card);

    chatMessages.scrollTop = chatMessages.scrollHeight;

    deXuatDangCho = {
        status,
        confirmButton,
        cancelButton
    };

    // Khách chọn hủy
    cancelButton.addEventListener("click", function() {
        status.textContent = "Bạn đã hủy đề xuất thêm sản phẩm.";
        confirmButton.disabled = true;
        cancelButton.disabled = true;
        deXuatDangCho = null;
    });

    // Khách xác nhận thêm vào giỏ
    confirmButton.addEventListener("click", async function() {

        confirmButton.disabled = true;
        cancelButton.disabled = true;

        try {
            // Kiểm tra cart.js đã được tải chưa
            if (
                typeof getCart !== "function" ||
                typeof addToCart !== "function"
            ) {
                throw new Error(
                    "Không tìm thấy chức năng giỏ hàng."
                );
            }

            // Lấy thông tin mới nhất từ Firebase
            const response = await fetch(
                `${PRODUCT_API_URL}/products/${encodeURIComponent(action.id)}`
            );

            if (!response.ok) {
                throw new Error(
                    "Sản phẩm không còn tồn tại."
                );
            }

            const product = await response.json();

            const stock = Number(product.stock) || 0;
            const soLuongThem = Number(action.quantity) || 1;

            // Kiểm tra số lượng hiện có trong giỏ
            const cart = getCart();

            const sanPhamTrongGio = cart.find(
                item => String(item.id) === String(action.id)
            );

            const soLuongHienTai = sanPhamTrongGio
                ? Number(sanPhamTrongGio.quantity) || 0
                : 0;

            // Kiểm tra tồn kho
            if (stock <= 0) {
                throw new Error(
                    "Sản phẩm hiện đã hết hàng."
                );
            }

            if (soLuongThem + soLuongHienTai > stock) {
                throw new Error(
                    `Không đủ hàng. Hiện còn ${stock} sản phẩm, `
                    + `trong giỏ đã có ${soLuongHienTai} sản phẩm.`
                );
            }

            // Thêm vào giỏ hàng
            const thanhCong = addToCart(
                String(action.id),
                soLuongThem
            );

            if (!thanhCong) {
                throw new Error(
                    "Không thể thêm sản phẩm vào giỏ hàng."
                );
            }

            status.textContent =
                "✓ Đã thêm sản phẩm vào giỏ hàng thành công!";

            status.className =
                "small text-success fw-bold mb-0";

            confirmButton.remove();
            cancelButton.remove();

            deXuatDangCho = null;

        } catch (error) {
            status.textContent = error.message;
            status.className = "small text-danger mb-3";

            confirmButton.disabled = false;
            cancelButton.disabled = false;

            console.error("Lỗi thêm giỏ hàng:", error);
        }
    });
}

// Hàm gửi tin nhắn đến FastAPI

async function guiTinNhan(noiDung) {
    noiDung = noiDung.trim();

    if (!noiDung || dangGui) {
        return;
    }
    voHieuHoaDeXuatCu();

    dangGui = true;
    sendButton.disabled = true;
    messageInput.disabled = true;

    // Hiển thị tin nhắn người dùng
    hienThiTinNhan(noiDung, "user");
    messageInput.value = "";

    // Hiển thị trạng thái chờ
    const loading = hienThiTinNhan(
        "TechZone AI đang trả lời...",
        "bot"
    );

    try {
        // Hàm gửi yêu cầu đến FastAPI
        async function goiChat(id) {
            return fetch(API_URL, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    message: noiDung,
                    session_id: id
                })
            });
        }

        // Gửi tin nhắn
        let response = await goiChat(sessionId);

        // Nếu phiên cũ không tồn tại, tạo phiên mới
        if (response.status === 404 && sessionId) {
            sessionId = null;
            sessionStorage.removeItem("techzone_session_id");

            response = await goiChat(null);
        }

        // Đọc kết quả
        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                typeof data.detail === "string"
                    ? data.detail
                    : "Không thể gửi tin nhắn."
            );
        }

        // Lưu session ID mới
        sessionId = data.session_id;
        sessionStorage.setItem(
            "techzone_session_id",
            sessionId
        );

        // Xóa trạng thái chờ
        loading.remove();

        // Hiển thị câu trả lời
        hienThiTinNhan(data.reply, "bot");

        // Hiển thị đề xuất thêm vào giỏ hàng
        hienThiDeXuatGioHang(data.cart_action);

    } catch (error) {
        loading.remove();

        console.error("Lỗi chatbot:", error);

        hienThiTinNhan(
            "Xin lỗi, mình chưa thể trả lời. Bạn hãy thử lại nhé!",
            "bot"
        );

    } finally {
        dangGui = false;
        sendButton.disabled = false;
        messageInput.disabled = false;
        messageInput.focus();
    }
}


// Sự kiện nhấn nút Gửi hoặc Enter
chatForm.addEventListener("submit", function(event) {
    event.preventDefault();

    guiTinNhan(messageInput.value);
});

// Sự kiện nhấn các nút gợi ý
suggestionButtons.forEach(function(button) {
    button.addEventListener("click", function() {
        const noiDung = button.dataset.message;
        guiTinNhan(noiDung);
    });
});
