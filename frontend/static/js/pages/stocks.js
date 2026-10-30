WMS.ready(async function () {
    const { esc, num, date, expiryBadge } = WMS.ui;
    const $ = id => document.getElementById(id);
    const PAGE_SIZE = 15;
    let items = [], page = 1;

    try {
        const lk = await WMS.lookups(true);
        WMS.ui.fillSelect('fProduct', lk.products.map(p => ({ value: p.id, label: `${p.sku} | ${p.product_name}` })), { placeholder: 'Mọi sản phẩm' });
        WMS.ui.fillSelect('fLocation', lk.locations.map(l => ({ value: l.id, label: l.location_code })), { placeholder: 'Mọi ô kệ' });
    } catch (e) { WMS.ui.error(e.message); }

    const params = () => ({ q: $('q').value.trim(), product_id: $('fProduct').value, location_id: $('fLocation').value, expiry: $('fExpiry').value });

    function render() {
        $('sumLots').textContent = num(items.length);
        $('sumQty').textContent = num(items.reduce((s, i) => s + i.quantity_on_hand, 0));
        $('sumNear').textContent = num(items.filter(i => i.expiry_status === 'near').length);
        $('sumExpired').textContent = num(items.filter(i => i.expiry_status === 'expired').length);
        $('tbody').innerHTML = WMS.ui.paginate(items, page, PAGE_SIZE).map(s => `<tr>
            <td class="ledger-ref">${esc(s.location_code)}${s.location_status !== 'active' ? ` <span class="badge-soft bg-soft-warning">${esc(s.location_status)}</span>` : ''}</td>
            <td><b>${esc(s.sku)}</b><div class="sub">${esc(s.product_name)}</div></td><td>${esc(s.batch_no)}</td>
            <td>${date(s.expiry_date)}<div class="mt-1">${expiryBadge(s.days_left)}</div></td>
            <td class="num">${num(s.quantity_on_hand)} ${esc(s.unit)}</td><td class="num">${num(s.quantity_allocated)}</td>
            <td class="num fw-semibold">${num(s.quantity_available)}</td><td class="num">${num(s.weight_kg)} kg</td></tr>`).join('')
            || WMS.ui.empty(8, 'fa-warehouse', 'Không có lô hàng nào phù hợp bộ lọc');
        WMS.ui.renderPager($('pager'), { total: items.length, page, size: PAGE_SIZE, onChange: p => { page = p; render(); } });
    }
    async function load(resetPage) {
        try { items = (await WMS.api.get('/api/stocks', params())).items; if (resetPage) page = 1; render(); }
        catch (e) { if (e.status !== 401) WMS.ui.error(e.message); }
    }

    $('q').addEventListener('input', WMS.ui.debounce(() => load(true), 300));
    ['fProduct', 'fLocation', 'fExpiry'].forEach(id => $(id).addEventListener('change', () => load(true)));
    $('btnExport').addEventListener('click', () => WMS.ui.downloadCSV(`ton-kho-${WMS.ui.todayISO()}.csv`,
        ['Ô kệ', 'SKU', 'Sản phẩm', 'Lô', 'Hạn sử dụng', 'Tồn thực tế', 'Giữ chỗ', 'Khả dụng', 'Khối lượng (kg)'],
        items.map(s => [s.location_code, s.sku, s.product_name, s.batch_no, s.expiry_date, s.quantity_on_hand, s.quantity_allocated, s.quantity_available, s.weight_kg])));

    load(true);
    WMS.poll(() => load(false), 10000);
});
