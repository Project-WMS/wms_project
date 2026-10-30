WMS.ready(function () {
    const { esc, num, datetime, badge } = WMS.ui;
    const $ = id => document.getElementById(id);
    const PAGE_SIZE = 20;
    let page = 1, total = 0, items = [];

    // Khởi tạo sẵn placeholder và tải danh sách sản phẩm song song với bảng thẻ kho (không chặn load)
    WMS.ui.fillSelect('fProduct', [], { placeholder: 'Mọi sản phẩm' });
    WMS.lookups(false).then(lk => {
        WMS.ui.fillSelect('fProduct', lk.products.map(p => ({ value: p.id, label: `${p.sku} | ${p.product_name}` })), { placeholder: 'Mọi sản phẩm' });
    }).catch(e => { if (e.status !== 401) WMS.ui.error(e.message); });

    const filters = () => ({ q: $('q').value.trim(), product_id: $('fProduct').value, transaction_type: $('fType').value, date_from: $('fFrom').value, date_to: $('fTo').value });
    const chg = v => `<span class="${v >= 0 ? 'qty-in' : 'qty-out'}">${v > 0 ? '+' : ''}${num(v)}</span>`;

    function render() {
        $('tbody').innerHTML = items.map(r => `<tr>
            <td class="text-nowrap">${datetime(r.created_at)}</td><td>${badge('ledger', r.transaction_type)}</td><td class="ledger-ref">${esc(r.reference_code)}</td>
            <td><b>${esc(r.sku)}</b><div class="sub">${esc(r.product_name)}</div></td><td>${esc(r.batch_no)}</td>
            <td class="ledger-ref">${esc(r.from_loc) || '–'}</td><td class="ledger-ref">${esc(r.to_loc) || '–'}</td>
            <td class="num">${chg(r.quantity_change)}</td><td class="num">${num(r.balance_after)}</td><td>${esc(r.performer)}</td></tr>`).join('')
            || WMS.ui.empty(10, 'fa-book', 'Không có dòng thẻ kho nào phù hợp bộ lọc');
        WMS.ui.renderPager($('pager'), { total, page, size: PAGE_SIZE, onChange: p => { page = p; load(); } });
    }
    async function load() {
        try {
            const res = await WMS.api.get('/api/ledger', { ...filters(), limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
            items = res.items; total = res.total; render();
        } catch (e) { if (e.status !== 401) WMS.ui.error(e.message); }
    }

    $('q').addEventListener('input', WMS.ui.debounce(() => { page = 1; load(); }, 300));
    ['fProduct', 'fType', 'fFrom', 'fTo'].forEach(id => $(id).addEventListener('change', () => { page = 1; load(); }));
    $('btnExport').addEventListener('click', async () => {
        const btn = $('btnExport'); WMS.ui.setBusy(btn, true, 'Đang xuất...');
        try {
            const res = await WMS.api.get('/api/ledger', { ...filters(), limit: 2000, offset: 0 });
            WMS.ui.downloadCSV(`the-kho-${WMS.ui.todayISO()}.csv`,
                ['Thời gian', 'Loại', 'Chứng từ', 'SKU', 'Sản phẩm', 'Lô', 'Từ ô', 'Đến ô', 'Thay đổi', 'Tồn sau', 'Người thực hiện'],
                res.items.map(r => [WMS.ui.datetime(r.created_at), r.transaction_type, r.reference_code, r.sku, r.product_name, r.batch_no, r.from_loc || '', r.to_loc || '', r.quantity_change, r.balance_after, r.performer]));
            if (res.total > res.items.length) WMS.ui.toast(`Chỉ xuất ${res.items.length}/${res.total} dòng mới nhất. Hãy thu hẹp bộ lọc để xuất đầy đủ.`, 'warning');
        } catch (e) { WMS.ui.error(e.message); }
        WMS.ui.setBusy(btn, false);
    });

    load();
    WMS.poll(load, 10000);
});