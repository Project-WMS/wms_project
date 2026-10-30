WMS.ready(function () {
    const { esc, num, date, datetime, badge, run } = WMS.ui;
    const $ = id => document.getElementById(id);
    const PAGE_SIZE = 10, modal = new bootstrap.Modal($('docModal'));
    let page = 1, total = 0, items = [], lk = null;
    const expanded = new Set();

    function detailHtml(r) {
        return `<tr class="detail-row"><td colspan="8">` + r.items.map(l => `
            <div class="mb-2"><b>${esc(l.sku)}</b> <span class="text-muted">${esc(l.product_name)}</span> — yêu cầu <b>${num(l.requested_qty)}</b> ${esc(l.unit)}, đã lấy <b>${num(l.picked_qty)}</b>
            <table class="table table-sm mb-0 mt-1"><thead><tr><th>Ô kệ lấy hàng</th><th>Lô</th><th>HSD</th><th class="num">Giữ chỗ</th><th class="num">Đã lấy</th><th>Trạng thái</th></tr></thead><tbody>` +
            l.tasks.map(t => `<tr><td class="ledger-ref">${esc(t.location_code)}</td><td>${esc(t.batch_no)}</td><td>${date(t.expiry_date)}</td>
                <td class="num">${num(t.allocated_qty)}</td><td class="num">${t.picked_qty === null ? '–' : num(t.picked_qty)}</td><td>${badge('task', t.status)}</td></tr>`).join('') +
            '</tbody></table></div>').join('') + '</td></tr>';
    }

    function render() {
        $('tbody').innerHTML = items.map(r => {
            const req = r.items.reduce((s, l) => s + l.requested_qty, 0), picked = r.items.reduce((s, l) => s + l.picked_qty, 0);
            const first = r.items[0], more = r.items.length - 1, open = expanded.has(r.id), pct = req ? Math.round(picked / req * 100) : 0;
            return `<tr><td><button class="btn btn-sm btn-link p-0" data-expand="${r.id}" aria-label="Xem chi tiết"><i class="fa-solid ${open ? 'fa-chevron-down' : 'fa-chevron-right'}"></i></button></td>
                <td class="ledger-ref fw-semibold">${esc(r.issue_code)}</td><td>${esc(r.customer_name)}</td>
                <td>${first ? `<b>${esc(first.sku)}</b> <span class="text-muted">${esc(first.product_name)}</span>` : '–'}${more > 0 ? ` <span class="badge-soft bg-soft-secondary">+${more} dòng</span>` : ''}</td>
                <td style="min-width:150px"><div class="small">${num(picked)} / ${num(req)}</div><div class="cap-bar mt-1"><span style="width:${pct}%"></span></div></td>
                <td>${badge('issue', r.status)}</td><td>${esc(r.created_by_name)}<div class="sub">${datetime(r.created_at)}</div></td>
                <td class="text-end">${r.can_cancel ? `<button class="btn btn-sm btn-outline-danger" data-cancel="${r.id}" title="Hủy phiếu"><i class="fa-solid fa-ban"></i></button>` : ''}</td></tr>${open ? detailHtml(r) : ''}`;
        }).join('') || WMS.ui.empty(8, 'fa-dolly', 'Chưa có phiếu xuất nào');
        WMS.ui.renderPager($('pager'), { total, page, size: PAGE_SIZE, onChange: p => { page = p; load(); } });
    }

    async function load() {
        try {
            const res = await WMS.api.get('/api/outbound', { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE, status: $('statusFilter').value, q: $('q').value.trim() });
            items = res.items; total = res.total; render();
        } catch (e) { if (e.status !== 401) WMS.ui.error(e.message); }
    }

    $('tbody').addEventListener('click', async e => {
        const ex = e.target.closest('[data-expand]'), cn = e.target.closest('[data-cancel]');
        if (ex) { const id = Number(ex.dataset.expand); expanded.has(id) ? expanded.delete(id) : expanded.add(id); render(); }
        if (cn) {
            const r = items.find(x => x.id == cn.dataset.cancel);
            const ok = await WMS.ui.confirm({ title: 'Hủy phiếu xuất', danger: true, okText: 'Hủy phiếu', message: `Hủy phiếu ${r.issue_code}? Hàng đang giữ chỗ sẽ được giải phóng và lệnh lấy hàng bị thu hồi.` });
            if (ok && await run(() => WMS.api.del(`/api/outbound/${r.id}`))) load();
        }
    });
    $('q').addEventListener('input', WMS.ui.debounce(() => { page = 1; load(); }, 300));
    $('statusFilter').addEventListener('change', () => { page = 1; load(); });

    function addLine() {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td><select class="form-select form-select-sm f-prod" required><option value="">-- Chọn sản phẩm --</option>${
            lk.products.map(p => `<option value="${p.id}">${esc(p.sku)} | ${esc(p.product_name)} (khả dụng ${num(p.available)})</option>`).join('')}</select>
            <div class="line-hint f-hint"></div></td>
            <td><input type="number" min="1" step="1" class="form-control form-control-sm f-qty" required></td>
            <td><button type="button" class="btn btn-sm btn-outline-danger f-del" aria-label="Xóa dòng"><i class="fa-solid fa-xmark"></i></button></td>`;
        $('lines').appendChild(tr);
    }
    function checkHints() {
        const used = {};
        $('lines').querySelectorAll('tr').forEach(tr => {
            const pid = tr.querySelector('.f-prod').value, q = parseInt(tr.querySelector('.f-qty').value, 10) || 0, hint = tr.querySelector('.f-hint');
            const p = lk.products.find(x => x.id == pid);
            if (!p) { hint.textContent = ''; return; }
            used[pid] = (used[pid] || 0) + q;
            const over = used[pid] > Number(p.available);
            hint.textContent = `Khả dụng: ${num(p.available)} ${p.unit}${over ? ' — vượt tồn khả dụng!' : ''}`;
            hint.style.color = over ? '#b91c1c' : '';
        });
    }

    $('btnAdd').addEventListener('click', async () => {
        try { lk = await WMS.lookups(true); } catch (e) { return WMS.ui.error(e.message); }
        if (!lk.customers.length) return WMS.ui.error('Chưa có khách hàng. Hãy thêm ở mục Danh mục > Đối tác.');
        $('docForm').reset(); $('lines').innerHTML = '';
        $('fCustomer').dataset.sig = '';
        WMS.ui.fillSelect('fCustomer', lk.customers.map(c => ({ value: c.id, label: c.partner_name })), { placeholder: '-- Chọn khách hàng --' });
        addLine(); modal.show();
    });
    $('btnAddLine').addEventListener('click', addLine);
    $('lines').addEventListener('input', checkHints);
    $('lines').addEventListener('change', checkHints);
    $('lines').addEventListener('click', e => { const d = e.target.closest('.f-del'); if (d && $('lines').children.length > 1) d.closest('tr').remove(); });

    $('docForm').addEventListener('submit', async e => {
        e.preventDefault();
        if (!e.target.reportValidity()) return;
        const itemsBody = [...$('lines').querySelectorAll('tr')].map(tr => ({ product_id: Number(tr.querySelector('.f-prod').value), quantity: parseInt(tr.querySelector('.f-qty').value, 10) }));
        const btn = $('btnSave'); WMS.ui.setBusy(btn, true);
        const res = await run(() => WMS.api.post('/api/outbound', { customer_id: Number($('fCustomer').value), items: itemsBody }));
        WMS.ui.setBusy(btn, false);
        if (res) { modal.hide(); page = 1; load(); }
    });

    load();
    WMS.poll(load, 5000);
});
