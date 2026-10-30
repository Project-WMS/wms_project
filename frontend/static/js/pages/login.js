(function () {
    const $ = id => document.getElementById(id);
    const home = u => (u.role === 'worker' ? '/mobile' : '/');

    function show(text, kind) {
        const m = $('msg');
        m.textContent = text;
        m.className = `alert alert-${kind} py-2 small`;
    }
    function setTab(tab) {
        const login = tab === 'login';
        $('loginForm').classList.toggle('d-none', !login); $('registerForm').classList.toggle('d-none', login);
        $('tabLogin').classList.toggle('active', login); $('tabRegister').classList.toggle('active', !login);
        $('msg').className = 'alert d-none';
    }
    document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => setTab(b.dataset.tab)));

    const reason = new URLSearchParams(location.search).get('reason');
    if (reason === 'expired') show('Phiên đăng nhập đã hết hạn hoặc tài khoản không còn hoạt động. Vui lòng đăng nhập lại.', 'warning');

    // Đã có phiên hợp lệ thì vào thẳng hệ thống
    if (WMS.session.token() && WMS.session.user() && reason !== 'expired') {
        WMS.api.get('/api/auth/me').then(me => { location.href = home(me); }).catch(() => WMS.session.clear());
    }

    $('loginForm').addEventListener('submit', async e => {
        e.preventDefault();
        const btn = $('btnLogin'); btn.disabled = true;
        try {
            const res = await WMS.api.post('/api/auth/login', { username: $('lUser').value, password: $('lPass').value }, { auth: false });
            WMS.session.save(res.token, res.user);
            location.href = home(res.user);
        } catch (err) {
            show(err.message, 'danger');
            btn.disabled = false;
        }
    });

    $('registerForm').addEventListener('submit', async e => {
        e.preventDefault();
        if (!e.target.reportValidity()) return;
        const btn = $('btnRegister'); btn.disabled = true;
        try {
            const res = await WMS.api.post('/api/auth/register', {
                full_name: $('rName').value, username: $('rUser').value, password: $('rPass').value, role: $('rRole').value }, { auth: false });
            show(res.message, 'success'); e.target.reset();
        } catch (err) { show(err.message, 'danger'); }
        btn.disabled = false;
    });
})();
