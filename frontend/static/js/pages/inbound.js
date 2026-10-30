WMS.ready(function () {
    const { esc, num, date, datetime, badge, run } = WMS.ui;
    const $ = id => document.getElementById(id);
    const PAGE_SIZE = 10, modal = new bootstrap.Modal($('docModal'));
    let page = 1, total = 0, items = [], lk = null;
    const expanded = new Set();

    // ---------- Danh sách phiếu ----------
    function detailHtml(r) {
        return `<tr class="detail-row"><td colspan="8"><table class="table table-sm mb-0"><thead><tr><th>Sản phẩm</th><th>Lô</th><th>HSD</th><th>Ô kệ đích</th><th class="num">Dự kiến</th><th class="num">Đã xếp</th><th>Nhiệm vụ</th></tr></thead><tbody>` +
            r.items.map(l => `<tr><td><b>${esc(l.sku)}</b> <span class="text-muted">${esc(l.product_name)}</span></td><td>${esc(l.batch_no)}</td><td>${date(l.expiry_date)}</td>
                <td class="ledger-ref">${esc(l.location_code)}</td><td class="num">${num(l.expected_qty)} ${esc(l.unit)}</td><td class="num">${num(l.putaway_qty)}${l.task_status === 'completed' && l.putaway_qty < l.expected_qty ? ` <span class="text-danger">(thiếu ${l.expected_qty - l.putaway_qty})</span>` : ''}</td>
                <td>${badge('task', l.task_status)}</td></tr>`).join('') + '</tbody></table></td></tr>';
    }

    function render() {
        $('tbody').innerHTML = items.map(r => {
            const exp = r.items.reduce((s, l) => s + l.expected_qty, 0), put = r.items.reduce((s, l) => s + l.putaway_qty, 0);
            const first = r.items[0], more = r.items.length - 1, open = expanded.has(r.id);
            const pct = exp ? Math.round(put / exp * 100) : 0;
            return `<tr><td><button class="btn btn-sm btn-link p-0" data-expand="${r.id}" aria-label="Xem chi tiết"><i class="fa-solid ${open ? 'fa-chevron-down' : 'fa-chevron-right'}"></i></button></td>
                <td class="ledger-ref fw-semibold">${esc(r.receipt_code)}</td><td>${esc(r.supplier_name)}</td>
                <td>${first ? `<b>${esc(first.sku)}</b> <span class="text-muted">${esc(first.product_name)}</span>` : '–'}${more > 0 ? ` <span class="badge-soft bg-soft-secondary">+${more} dòng</span>` : ''}</td>
                <td style="min-width:150px"><div class="small">${num(put)} / ${num(exp)}</div><div class="cap-bar mt-1"><span style="width:${pct}%"></span></div></td>
                <td>${badge('receipt', r.status)}</td><td>${esc(r.created_by_name)}<div class="sub">${datetime(r.created_at)}</div></td>
                <td class="text-end">${r.can_cancel ? `<button class="btn btn-sm btn-outline-danger" data-cancel="${r.id}" title="Hủy phiếu"><i class="fa-solid fa-ban"></i></button>` : ''}</td></tr>${open ? detailHtml(r) : ''}`;
        }).join('') || WMS.ui.empty(8, 'fa-truck-ramp-box', 'Chưa có phiếu nhập nào');
        WMS.ui.renderPager($('pager'), { total, page, size: PAGE_SIZE, onChange: p => { page = p; load(); } });
    }

    async function load() {
        try {
            const res = await WMS.api.get('/api/inbound', { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE, status: $('statusFilter').value, q: $('q').value.trim() });
            items = res.items; total = res.total; render();
        } catch (e) { if (e.status !== 401) WMS.ui.error(e.message); }
    }

    $('tbody').addEventListener('click', async e => {
        const ex = e.target.closest('[data-expand]'), cn = e.target.closest('[data-cancel]');
        if (ex) { const id = Number(ex.dataset.expand); expanded.has(id) ? expanded.delete(id) : expanded.add(id); render(); }
        if (cn) {
            const r = items.find(x => x.id == cn.dataset.cancel);
            const ok = await WMS.ui.confirm({ title: 'Hủy phiếu nhập', danger: true, okText: 'Hủy phiếu', message: `Hủy phiếu ${r.receipt_code}? Các lệnh xếp kệ trên Mobile sẽ bị thu hồi.` });
            if (ok && await run(() => WMS.api.del(`/api/inbound/${r.id}`))) load();
        }
    });
    $('q').addEventListener('input', WMS.ui.debounce(() => { page = 1; load(); }, 300));
    $('statusFilter').addEventListener('change', () => { page = 1; load(); });

    // ---------- Form lập phiếu ----------
    const prodOpts = () => lk.products.map(p => `<option value="${p.id}">${esc(p.sku)} | ${esc(p.product_name)}</option>`).join('');
    const locOpts = () => lk.locations.filter(l => l.status === 'active').map(l => `<option value="${l.id}">${esc(l.location_code)} (trống ~${num(WMS.freeKg(l))} kg)</option>`).join('');

    function addLine() {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td><select class="form-select form-select-sm f-prod" required><option value="">-- Chọn sản phẩm --</option>${prodOpts()}</select><div class="line-hint f-prodhint"></div></td>
            <td><input class="form-control form-control-sm f-batch" required maxlength="50" placeholder="LOT-001"></td>
            <td><input type="date" class="form-control form-control-sm f-exp" required min="${WMS.ui.todayISO()}"></td>
            <td><input type="number" min="1" step="1" class="form-control form-control-sm f-qty" required></td>
            <td><select class="form-select form-select-sm f-loc" required><option value="">-- Chọn ô kệ --</option>${locOpts()}</select><div class="line-hint f-lochint"></div></td>
            <td><button type="button" class="btn btn-sm btn-outline-danger f-del" aria-label="Xóa dòng"><i class="fa-solid fa-xmark"></i></button></td>`;
        $('lines').appendChild(tr);
        updateSummary();
    }

    function lineWeight(tr) {
        const p = lk.products.find(x => x.id == tr.querySelector('.f-prod').value);
        return p ? (parseInt(tr.querySelector('.f-qty').value, 10) || 0) * Number(p.unit_weight_kg) : 0;
    }
    function updateSummary() {
        let qty = 0, kg = 0;
        const perLoc = {};
        $('lines').querySelectorAll('tr').forEach(tr => {
            const q = parseInt(tr.querySelector('.f-qty').value, 10) || 0, w = lineWeight(tr), loc = tr.querySelector('.f-loc').value;
            qty += q; kg += w; if (loc) perLoc[loc] = (perLoc[loc] || 0) + w;
            const p = lk.products.find(x => x.id == tr.querySelector('.f-prod').value);
            tr.querySelector('.f-prodhint').textContent = p ? `${num(p.unit_weight_kg)} kg/${p.unit}` : '';
            const l = lk.locations.find(x => x.id == loc), hint = tr.querySelector('.f-lochint');
            if (l && w) { const over = perLoc[loc] > WMS.freeKg(l); hint.textContent = `${num(w)} kg${over ? ' — có thể vượt tải trọng ô!' : ''}`; hint.style.color = over ? '#b91c1c' : ''; }
            else { hint.textContent = ''; }
        });
        $('docSummary').textContent = `${$('lines').children.length} dòng • tổng ${num(qty)} đơn vị • ~${num(kg)} kg`;
    }

    $('btnAdd').addEventListener('click', async () => {
        try { lk = await WMS.lookups(true); } catch (e) { return WMS.ui.error(e.message); }
        if (!lk.suppliers.length) return WMS.ui.error('Chưa có nhà cung cấp. Hãy thêm ở mục Danh mục > Đối tác.');
        $('docForm').reset(); $('lines').innerHTML = '';
        WMS.ui.fillSelect('fSupplier', lk.suppliers.map(s => ({ value: s.id, label: s.partner_name })), { placeholder: '-- Chọn nhà cung cấp --' });
        $('fSupplier').dataset.sig = '';
        addLine(); modal.show();
    });
    $('btnAddLine').addEventListener('click', addLine);
    $('lines').addEventListener('input', updateSummary);
    $('lines').addEventListener('change', updateSummary);
    $('lines').addEventListener('click', e => { const d = e.target.closest('.f-del'); if (d && $('lines').children.length > 1) { d.closest('tr').remove(); updateSummary(); } });

    $('docForm').addEventListener('submit', async e => {
        e.preventDefault();
        if (!e.target.reportValidity()) return;
        const itemsBody = [...$('lines').querySelectorAll('tr')].map(tr => ({
            product_id: Number(tr.querySelector('.f-prod').value), batch_no: tr.querySelector('.f-batch').value.trim(),
            expiry_date: tr.querySelector('.f-exp').value, quantity: parseInt(tr.querySelector('.f-qty').value, 10),
            to_location_id: Number(tr.querySelector('.f-loc').value) }));
        const btn = $('btnSave'); WMS.ui.setBusy(btn, true);
        const res = await run(() => WMS.api.post('/api/inbound', { supplier_id: Number($('fSupplier').value), items: itemsBody }));
        WMS.ui.setBusy(btn, false);
        if (res) { modal.hide(); page = 1; load(); }
    });

    load();
    WMS.poll(load, 5000);
});
