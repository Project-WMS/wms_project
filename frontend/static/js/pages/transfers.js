WMS.ready(function () {
    const { esc, num, datetime, badge, run } = WMS.ui;
    const $ = id => document.getElementById(id);
    const PAGE_SIZE = 10, modal = new bootstrap.Modal($('docModal'));
    let page = 1, total = 0, items = [], lk = null, stocks = [];
    const expanded = new Set();

    function render() {
        $('tbody').innerHTML = items.map(t => {
            const open = expanded.has(t.id), first = t.items[0], more = t.items.length - 1;
            const detail = open ? `<tr class="detail-row"><td colspan="5"><table class="table table-sm mb-0"><thead><tr><th>Sản phẩm</th><th>Lô</th><th>Từ ô</th><th>Đến ô</th><th class="num">Số lượng</th></tr></thead><tbody>` +
                t.items.map(l => `<tr><td><b>${esc(l.sku)}</b> <span class="text-muted">${esc(l.product_name)}</span></td><td>${esc(l.batch_no)}</td><td class="ledger-ref">${esc(l.from_loc)}</td>
                    <td class="ledger-ref">${esc(l.to_loc)}</td><td class="num">${num(l.transfer_qty)} ${esc(l.unit)}</td></tr>`).join('') + '</tbody></table></td></tr>' : '';
            return `<tr><td><button class="btn btn-sm btn-link p-0" data-expand="${t.id}" aria-label="Xem chi tiết"><i class="fa-solid ${open ? 'fa-chevron-down' : 'fa-chevron-right'}"></i></button></td>
                <td class="ledger-ref fw-semibold">${esc(t.transfer_code)}</td>
                <td>${first ? `<b>${esc(first.sku)}</b> ${num(first.transfer_qty)} • <span class="ledger-ref">${esc(first.from_loc)}</span> <i class="fa-solid fa-arrow-right text-muted"></i> <span class="ledger-ref">${esc(first.to_loc)}</span>` : '–'}${more > 0 ? ` <span class="badge-soft bg-soft-secondary">+${more} dòng</span>` : ''}</td>
                <td>${badge('transfer', t.status)}</td><td>${esc(t.created_by_name)}<div class="sub">${datetime(t.created_at)}</div></td></tr>${detail}`;
        }).join('') || WMS.ui.empty(5, 'fa-right-left', 'Chưa có phiếu điều chuyển nào');
        WMS.ui.renderPager($('pager'), { total, page, size: PAGE_SIZE, onChange: p => { page = p; load(); } });
    }

    async function load() {
        try {
            const res = await WMS.api.get('/api/transfers', { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
            items = res.items; total = res.total; render();
        } catch (e) { if (e.status !== 401) WMS.ui.error(e.message); }
    }
    $('tbody').addEventListener('click', e => {
        const ex = e.target.closest('[data-expand]');
        if (ex) { const id = Number(ex.dataset.expand); expanded.has(id) ? expanded.delete(id) : expanded.add(id); render(); }
    });

    // ---------- Form ----------
    function addLine() {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td><select class="form-select form-select-sm f-stock" required><option value="">-- Chọn lô hàng --</option>${
            stocks.map(s => `<option value="${s.id}">${esc(s.location_code)} | ${esc(s.sku)} | Lô ${esc(s.batch_no)} | khả dụng ${num(s.quantity_available)}</option>`).join('')}</select></td>
            <td><select class="form-select form-select-sm f-to" required><option value="">-- Chọn ô đích --</option></select><div class="line-hint f-tohint"></div></td>
            <td><input type="number" min="1" step="1" class="form-control form-control-sm f-qty" required><div class="line-hint f-qhint"></div></td>
            <td><button type="button" class="btn btn-sm btn-outline-danger f-del" aria-label="Xóa dòng"><i class="fa-solid fa-xmark"></i></button></td>`;
        $('lines').appendChild(tr);
    }

    function onStockChange(tr) {
        const s = stocks.find(x => x.id == tr.querySelector('.f-stock').value), to = tr.querySelector('.f-to'), qty = tr.querySelector('.f-qty');
        if (!s) { to.innerHTML = '<option value="">-- Chọn ô đích --</option>'; qty.removeAttribute('max'); tr.querySelector('.f-qhint').textContent = ''; return; }
        const keep = to.value;
        to.innerHTML = '<option value="">-- Chọn ô đích --</option>' + lk.locations.filter(l => l.status === 'active' && l.id !== s.location_id)
            .map(l => `<option value="${l.id}">${esc(l.location_code)} (trống ~${num(WMS.freeKg(l))} kg)</option>`).join('');
        if (keep) to.value = keep;
        qty.max = s.quantity_available;
        tr.querySelector('.f-qhint').textContent = `Tối đa ${num(s.quantity_available)} ${s.unit} • ${num(s.unit_weight_kg)} kg/${s.unit}`;
    }

    $('btnAdd').addEventListener('click', async () => {
        try {
            lk = await WMS.lookups(true);
            stocks = (await WMS.api.get('/api/stocks')).items.filter(s => s.quantity_available > 0);
        } catch (e) { return WMS.ui.error(e.message); }
        if (!stocks.length) return WMS.ui.error('Hiện không có lô hàng khả dụng để điều chuyển.');
        if (lk.locations.filter(l => l.status === 'active').length < 2) return WMS.ui.error('Cần ít nhất 2 ô kệ đang hoạt động để điều chuyển.');
        $('docForm').reset(); $('lines').innerHTML = ''; addLine(); modal.show();
    });
    $('btnAddLine').addEventListener('click', addLine);
    $('lines').addEventListener('change', e => { if (e.target.classList.contains('f-stock')) onStockChange(e.target.closest('tr')); });
    $('lines').addEventListener('click', e => { const d = e.target.closest('.f-del'); if (d && $('lines').children.length > 1) d.closest('tr').remove(); });

    $('docForm').addEventListener('submit', async e => {
        e.preventDefault();
        if (!e.target.reportValidity()) return;
        const body = { items: [...$('lines').querySelectorAll('tr')].map(tr => ({
            stock_id: Number(tr.querySelector('.f-stock').value), to_location_id: Number(tr.querySelector('.f-to').value),
            quantity: parseInt(tr.querySelector('.f-qty').value, 10) })) };
        const btn = $('btnSave'); WMS.ui.setBusy(btn, true);
        const res = await run(() => WMS.api.post('/api/transfers', body));
        WMS.ui.setBusy(btn, false);
        if (res) { modal.hide(); page = 1; load(); }
    });

    load();
    WMS.poll(load, 8000);
});
