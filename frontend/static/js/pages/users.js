WMS.ready(function (me) {
    const { esc, datetime, roleLabel, run } = WMS.ui;
    const $ = id => document.getElementById(id);
    let users = [], filter = 'all', lastSig = '';

    $('hint').textContent = me.role === 'admin'
        ? 'Admin duyệt/khóa được cả Thủ kho và Công nhân, và là người duy nhất đổi được vai trò.'
        : 'Thủ kho chỉ duyệt/khóa được tài khoản Công nhân (BR07).';

    const stateOf = u => u.approval_status === 'pending' ? 'pending' : u.approval_status === 'rejected' ? 'rejected' : (u.is_active ? 'active' : 'locked');
    const badgeOf = u => ({
        pending: '<span class="badge-soft bg-soft-warning">Chờ duyệt</span>', rejected: '<span class="badge-soft bg-soft-danger">Đã từ chối</span>',
        active: '<span class="badge-soft bg-soft-success">Hoạt động</span>', locked: '<span class="badge-soft bg-soft-secondary">Đã khóa</span>' }[stateOf(u)]);

    function actions(u) {
        const b = (cls, icon, label, act) => `<button class="btn btn-sm ${cls}" data-act="${act}" data-id="${u.id}"><i class="fa-solid ${icon} me-1"></i>${label}</button>`;
        const s = stateOf(u), out = [];
        if (s === 'pending') out.push(b('btn-success', 'fa-check', 'Phê duyệt', 'approve'), b('btn-outline-danger', 'fa-xmark', 'Từ chối', 'reject'));
        else if (s === 'rejected') out.push(b('btn-success', 'fa-rotate-left', 'Duyệt lại', 'approve'));
        else if (s === 'active') out.push(b('btn-outline-secondary', 'fa-lock', 'Khóa', 'lock'));
        else out.push(b('btn-outline-primary', 'fa-lock-open', 'Mở khóa', 'unlock'));
        if (me.role === 'admin' && u.approval_status === 'approved') {
            out.push(`<select class="form-select form-select-sm d-inline-block w-auto" data-role-of="${u.id}" aria-label="Đổi vai trò">
                <option value="worker"${u.role === 'worker' ? ' selected' : ''}>Công nhân</option><option value="manager"${u.role === 'manager' ? ' selected' : ''}>Thủ kho</option></select>`);
        }
        return out.join(' ');
    }

    function render() {
        const cnt = { all: users.length, pending: 0, active: 0, locked: 0, rejected: 0 };
        users.forEach(u => cnt[stateOf(u)]++);
        document.querySelectorAll('[data-cnt]').forEach(el => el.textContent = cnt[el.dataset.cnt]);
        const list = users.filter(u => filter === 'all' || stateOf(u) === filter);
        $('tbody').innerHTML = list.map(u => `<tr><td><b>${esc(u.username)}</b><div class="sub">${esc(u.full_name)}</div></td>
            <td>${esc(roleLabel(u.role))}</td><td>${badgeOf(u)}</td><td class="text-nowrap">${datetime(u.created_at)}</td><td>${esc(u.approved_by_name) || '–'}</td>
            <td class="text-end text-nowrap">${actions(u)}</td></tr>`).join('') || WMS.ui.empty(6, 'fa-users', 'Không có tài khoản nào trong mục này');
    }

    async function load(force) {
        try {
            users = (await WMS.api.get('/api/users')).users;
            const sig = JSON.stringify(users);
            if (sig !== lastSig || force) { lastSig = sig; render(); }
        } catch (e) { if (e.status !== 401) WMS.ui.error(e.message); }
    }

    document.querySelectorAll('#statusTabs [data-filter]').forEach(b => b.addEventListener('click', () => {
        filter = b.dataset.filter;
        document.querySelectorAll('#statusTabs [data-filter]').forEach(x => x.classList.toggle('active', x === b)); render();
    }));

    $('tbody').addEventListener('click', async e => {
        const btn = e.target.closest('[data-act]');
        if (!btn) return;
        const u = users.find(x => x.id == btn.dataset.id), act = btn.dataset.act;
        if (act === 'reject' || act === 'lock') {
            const ok = await WMS.ui.confirm({ title: act === 'lock' ? 'Khóa tài khoản' : 'Từ chối tài khoản', danger: true, okText: act === 'lock' ? 'Khóa' : 'Từ chối',
                message: `${act === 'lock' ? 'Khóa' : 'Từ chối'} tài khoản ${u.username}?` });
            if (!ok) return;
        }
        if (await run(() => WMS.api.post(`/api/users/${u.id}/${act}`))) load(true);
    });
    $('tbody').addEventListener('change', async e => {
        const sel = e.target.closest('[data-role-of]');
        if (!sel) return;
        const u = users.find(x => x.id == sel.dataset.roleOf);
        if (!(await run(() => WMS.api.post(`/api/users/${u.id}/role`, { role: sel.value })))) sel.value = u.role;
        load(true);
    });

    load(true);
    WMS.poll(() => load(false), 6000);
});
