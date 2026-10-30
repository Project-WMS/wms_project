WMS.ready(function () {
    const { esc, num, datetime, badge, run } = WMS.ui;
    const $ = id => document.getElementById(id);
    const PAGE_SIZE = 10, newModal = new bootstrap.Modal($('newModal')), sheetModal = new bootstrap.Modal($('sheetModal'));
    let page = 1, total = 0, items = [], current = null;

    const varCell = v => v === 0 ? '<span class="text-muted">0</span>' : `<b class="${v > 0 ? 'qty-in' : 'qty-out'}">${v > 0 ? '+' : ''}${num(v)}</b>`;

    function render() {
        $('tbody').innerHTML = items.map(c => `<tr>
            <td class="ledger-ref fw-semibold">${esc(c.count_code)}</td><td class="ledger-ref">${esc(c.location_code) || '–'}</td>
            <td class="num">${c.items.length}</td><td class="num">${varCell(c.variance_total)}</td><td>${badge('count', c.status)}</td>
            <td>${esc(c.created_by_name)}<div class="sub">${datetime(c.created_at)}</div></td><td>${esc(c.approved_by_name) || '–'}</td>
            <td class="text-end"><button class="btn btn-sm btn-outline-primary" data-open="${c.id}">${c.status === 'reconciled' ? 'Xem' : 'Mở phiếu'}</button></td></tr>`).join('')
            || WMS.ui.empty(8, 'fa-clipboard-check', 'Chưa có phiếu kiểm kê nào');
        WMS.ui.renderPager($('pager'), { total, page, size: PAGE_SIZE, onChange: p => { page = p; load(); } });
    }
    async function load() {
        try {
            const res = await WMS.api.get('/api/counts', { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE, status: $('statusFilter').value });
            items = res.items; total = res.total; render();
        } catch (e) { if (e.status !== 401) WMS.ui.error(e.message); }
    }
    $('statusFilter').addEventListener('change', () => { page = 1; load(); });
    $('tbody').addEventListener('click', e => { const b = e.target.closest('[data-open]'); if (b) openSheet(items.find(c => c.id == b.dataset.open)); });

    // ---------- Phiếu kiểm kê (nhập số đếm thực tế) ----------
    function openSheet(c) {
        current = c;
        const open = c.status !== 'reconciled';
        $('sheetTitle').textContent = `Phiếu kiểm kê ${c.count_code}`;
        $('sheetInfo').innerHTML = `Ô kệ <b class="ledger-ref">${esc(c.location_code)}</b> • ${badge('count', c.status)} • tạo bởi ${esc(c.created_by_name)} lúc ${datetime(c.created_at)}` +
            (c.approved_by_name ? ` • duyệt bởi ${esc(c.approved_by_name)}` : '');
        $('sheetBody').innerHTML = c.items.map(l => `<tr data-detail="${l.detail_id}" data-system="${l.system_qty}">
            <td><b>${esc(l.sku)}</b><div class="sub">${esc(l.product_name)}</div></td><td>${esc(l.batch_no)}</td><td class="num">${num(l.system_qty)} ${esc(l.unit)}</td>
            <td><input type="number" min="0" step="1" class="form-control form-control-sm f-actual" value="${l.actual_qty}" ${open ? '' : 'disabled'}></td>
            <td class="num f-var">${varCell(l.actual_qty - l.system_qty)}</td></tr>`).join('');
        $('sheetFooter').querySelectorAll('#btnDelete, #btnSaveSheet, #btnApprove').forEach(b => b.classList.toggle('d-none', !open));
        sheetModal.show();
    }
    $('sheetBody').addEventListener('input', e => {
        if (!e.target.classList.contains('f-actual')) return;
        const tr = e.target.closest('tr'), v = (parseInt(e.target.value, 10) || 0) - Number(tr.dataset.system);
        tr.querySelector('.f-var').innerHTML = varCell(v);
    });
    const collect = () => [...$('sheetBody').querySelectorAll('tr')].map(tr => ({ detail_id: Number(tr.dataset.detail), actual_qty: parseInt(tr.querySelector('.f-actual').value, 10) }));
    const valid = () => collect().every(l => Number.isInteger(l.actual_qty) && l.actual_qty >= 0);

    $('btnSaveSheet').addEventListener('click', async () => {
        if (!valid()) return WMS.ui.error('Số đếm thực tế phải là số nguyên không âm.');
        if (await run(() => WMS.api.put(`/api/counts/${current.id}`, { lines: collect() }))) { sheetModal.hide(); load(); }
    });
    $('btnApprove').addEventListener('click', async () => {
        if (!valid()) return WMS.ui.error('Số đếm thực tế phải là số nguyên không âm.');
        const diff = collect().reduce((s, l) => s + (l.actual_qty - Number(current.items.find(i => i.detail_id === l.detail_id).system_qty)), 0);
        const ok = await WMS.ui.confirm({ title: 'Duyệt cân bằng kho', okText: 'Duyệt cân bằng',
            message: diff === 0 ? 'Số liệu khớp với hệ thống. Duyệt phiếu?' : `Tồn kho sẽ được điều chỉnh (tổng chênh lệch ${diff > 0 ? '+' : ''}${diff}) và ghi vào Thẻ kho. Thao tác không thể hoàn tác.` });
        if (!ok) return;
        const saved = await run(() => WMS.api.put(`/api/counts/${current.id}`, { lines: collect() }), { silent: true });
        if (saved && await run(() => WMS.api.post(`/api/counts/${current.id}/approve`))) { sheetModal.hide(); load(); }
    });
    $('btnDelete').addEventListener('click', async () => {
        const ok = await WMS.ui.confirm({ title: 'Xóa phiếu kiểm kê', danger: true, okText: 'Xóa phiếu', message: `Xóa phiếu ${current.count_code}? Tồn kho không bị ảnh hưởng.` });
        if (ok && await run(() => WMS.api.del(`/api/counts/${current.id}`))) { sheetModal.hide(); load(); }
    });

    // ---------- Lập phiếu mới ----------
    $('btnAdd').addEventListener('click', async () => {
        let lk;
        try { lk = await WMS.lookups(true); } catch (e) { return WMS.ui.error(e.message); }
        const opts = lk.locations.filter(l => l.lot_count > 0).map(l => ({ value: l.id, label: `${l.location_code} (${l.lot_count} lô)` }));
        if (!opts.length) return WMS.ui.error('Chưa có ô kệ nào đang chứa hàng để kiểm kê.');
        $('fLocation').dataset.sig = '';
        WMS.ui.fillSelect('fLocation', opts, { placeholder: '-- Chọn ô kệ --' });
        $('newForm').reset(); newModal.show();
    });
    $('newForm').addEventListener('submit', async e => {
        e.preventDefault();
        if (!e.target.reportValidity()) return;
        const btn = $('btnCreate'); WMS.ui.setBusy(btn, true);
        const res = await run(() => WMS.api.post('/api/counts', { location_id: Number($('fLocation').value) }));
        WMS.ui.setBusy(btn, false);
        if (res) {
            newModal.hide(); page = 1; await load();
            const created = items.find(c => c.id === res.id);
            if (created) setTimeout(() => openSheet(created), 250);
        }
    });

    load();
    WMS.poll(load, 8000);
});
