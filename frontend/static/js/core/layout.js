/* Khung trang quản trị: kiểm tra đăng nhập/phân quyền, sidebar, topbar, hàng đợi WMS.ready */
(function (w) {
    const WMS = (w.WMS = w.WMS || {});
    const queue = [];
    let currentUser = null;

    WMS.ready = fn => { if (currentUser) fn(currentUser); else queue.push(fn); };
    WMS.user = () => currentUser;

    document.addEventListener('DOMContentLoaded', async () => {
        const body = document.body;
        const allowed = (body.dataset.roles || '').split(',').filter(Boolean);
        if (!WMS.session.token() || !WMS.session.user()) return WMS.session.logout();

        let me;
        try { me = await WMS.api.get('/api/auth/me'); }
        catch (e) { if (e.status !== 401) { body.classList.remove('wms-pending'); WMS.ui.error(e.message); } return; }
        WMS.session.save(null, { id: me.id, username: me.username, full_name: me.full_name, role: me.role });

        if (allowed.length && !allowed.includes(me.role)) {
            location.href = me.role === 'worker' ? '/mobile' : '/';
            return;
        }
        currentUser = me;

        // Sidebar: chỉ hiện mục phù hợp vai trò
        document.querySelectorAll('[data-roles-show]').forEach(el => {
            if (!el.dataset.rolesShow.split(',').includes(me.role)) el.remove();
        });
        document.querySelectorAll('.nav-group').forEach(g => {            // ẩn tiêu đề nhóm nếu nhóm trống
            let n = g.nextElementSibling, has = false;
            while (n && !n.classList.contains('nav-group')) { has = true; n = n.nextElementSibling; }
            if (!has) g.remove();
        });
        document.querySelectorAll('[data-user-name]').forEach(el => el.textContent = me.full_name);
        document.querySelectorAll('[data-user-role]').forEach(el => el.textContent = WMS.ui.roleLabel(me.role));
        document.querySelectorAll('[data-logout]').forEach(el => el.addEventListener('click', e => { e.preventDefault(); WMS.session.logout(); }));

        body.classList.remove('wms-pending');
        queue.splice(0).forEach(fn => fn(me));
    });
})(window);
