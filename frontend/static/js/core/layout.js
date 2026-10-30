/* Khung trang quản trị: kiểm tra đăng nhập/phân quyền, sidebar, topbar, hàng đợi WMS.ready */
(function (w) {
    const WMS = (w.WMS = w.WMS || {});
    const queue = [];
    let currentUser = null;
    const AUTH_CHECK_KEY = 'wms_auth_checked_at';
    const AUTH_TTL_MS = 60000; // Xác thực lại ngầm tối đa mỗi 60 giây để tránh gọi kép /api/auth/me khi chuyển trang

    WMS.ready = fn => { if (currentUser) fn(currentUser); else queue.push(fn); };
    WMS.user = () => currentUser;

    function applyUserUI(me, allowed) {
        if (allowed.length && !allowed.includes(me.role)) {
            location.href = me.role === 'worker' ? '/mobile' : '/';
            return false;
        }
        // Sidebar: chỉ hiện mục phù hợp vai trò
        document.querySelectorAll('[data-roles-show]').forEach(el => {
            if (!el.dataset.rolesShow.split(',').includes(me.role)) el.remove();
        });
        document.querySelectorAll('.nav-group').forEach(g => { // ẩn tiêu đề nhóm nếu nhóm trống
            let n = g.nextElementSibling, has = false;
            while (n && !n.classList.contains('nav-group')) { has = true; n = n.nextElementSibling; }
            if (!has) g.remove();
        });
        document.querySelectorAll('[data-user-name]').forEach(el => el.textContent = me.full_name);
        document.querySelectorAll('[data-user-role]').forEach(el => el.textContent = WMS.ui.roleLabel(me.role));
        return true;
    }

    document.addEventListener('DOMContentLoaded', async () => {
        const body = document.body;
        const allowed = (body.dataset.roles || '').split(',').filter(Boolean);
        const cachedUser = WMS.session.user();
        if (!WMS.session.token() || !cachedUser) return WMS.session.logout();

        // 1. Hiển thị giao diện ngay lập tức từ localStorage (0ms, không trắng trang) và chạy luôn hàm tải dữ liệu trang
        if (!applyUserUI(cachedUser, allowed)) return;
        currentUser = cachedUser;
        document.querySelectorAll('[data-logout]').forEach(el =>
            el.addEventListener('click', e => {
                e.preventDefault();
                sessionStorage.removeItem(AUTH_CHECK_KEY);
                WMS.session.logout();
            })
        );
        body.classList.remove('wms-pending');
        queue.splice(0).forEach(fn => fn(cachedUser));

        // 2. Kiểm tra ngầm /api/auth/me ở background (nếu vừa kiểm tra trong 60s qua thì bỏ qua để giảm tải DB)
        const lastCheck = Number(sessionStorage.getItem(AUTH_CHECK_KEY) || 0);
        if (Date.now() - lastCheck < AUTH_TTL_MS) return;

        try {
            const me = await WMS.api.get('/api/auth/me');
            sessionStorage.setItem(AUTH_CHECK_KEY, String(Date.now()));
            WMS.session.save(null, { id: me.id, username: me.username, full_name: me.full_name, role: me.role });
            currentUser = me;
            applyUserUI(me, allowed);
        } catch (e) {
            if (e.status !== 401) WMS.ui.error(e.message);
        }
    });
})(window);