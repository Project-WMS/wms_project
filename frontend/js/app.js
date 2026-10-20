
async function kiemTraKetNoiDatabase() {
    const trangThai = document.getElementById("trang-thai-database");

    try {
        const phanHoi = await fetch(
            "http://127.0.0.1:8000/api/health/database"
        );

        if (!phanHoi.ok) {
            throw new Error("API trả về HTTP " + phanHoi.status);
        }

        const duLieu = await phanHoi.json();

        if (duLieu.status === "ok") {
            trangThai.textContent =
                "Đã kết nối PostgreSQL thành công!";
        } else {
            trangThai.textContent =
                "API hoạt động nhưng database đang gặp lỗi.";
        }
    } catch (loi) {
        trangThai.textContent =
            "Không kết nối được backend. Hãy kiểm tra FastAPI.";
        console.error("Lỗi kết nối:", loi);
    }
}

kiemTraKetNoiDatabase();
