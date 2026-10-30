WMS.ready(function () {
    const { esc, num, run } = WMS.ui;
    const PAGE_SIZE = 10;
    let all = [], page = 1, editing = null;
    const $ = id => document.getElementById(id);
    const modal = new bootstrap.Modal($('productModal'));

    function filtered() {
        const q = $('q').value.trim().toLowerCase(), st = $('statusFilter').value;
        return all.filter(p => (!st || (st === 'active') === !!p.is_active) &&
            (!q || [p.sku, p.barcode, p.product_name].some(v => String(v).toLowerCase().includes(q))));
    }

    function render() {
        const list = filtered(), rows = WMS.ui.paginate(list, page, PAGE_SIZE);
        $('tbody').innerHTML = rows.map(p => `<tr>
            <td><b>${esc(p.sku)}</b><div class="sub">${esc(p.product_name)}</div></td>
            <td class="ledger-ref">${esc(p.barcode)}</td><td>${esc(p.unit)}</td><td class="num">${num(p.unit_weight_kg)}</td>
            <td class="num">${num(p.total_on_hand)}</td><td class="num">${num(p.total_available)}</td>
            <td class="num">${num(p.min_safety_stock)} / ${num(p.max_safety_stock)}</td>
            <td>${p.is_active ? '<span class="badge-soft bg-soft-success">Đang dùng</span>' : '<span class="badge-soft bg-soft-secondary">Đã khóa</span>'}</td>
            <td class="text-nowrap text-end">
                <button class="btn btn-sm btn-outline-primary" data-edit="${p.id}" title="Sửa"><i class="fa-solid fa-pen"></i></button>
                <button class="btn btn-sm ${p.is_active ? 'btn-outline-danger' : 'btn-outline-success'}" data-toggle="${p.id}" title="${p.is_active ? 'Khóa' : 'Mở khóa'}">
                    <i class="fa-solid ${p.is_active ? 'fa-lock' : 'fa-lock-open'}"></i></button>
            </td></tr>`).join('') || WMS.ui.empty(9, 'fa-box-open', 'Không có sản phẩm nào phù hợp');
        WMS.ui.renderPager($('pager'), { total: list.length, page, size: PAGE_SIZE, onChange: p => { page = p; render(); } });
    }

    async function load() {
        try { all = (await WMS.api.get('/api/products')).items; render(); }
        catch (e) { if (e.status !== 401) WMS.ui.error(e.message); }
    }

    function openForm(p) {
        editing = p || null;
        $('productForm').reset();
        $('productModalTitle').textContent = p ? `Sửa sản phẩm ${p.sku}` : 'Thêm sản phẩm';
        ['fSku', 'fBarcode'].forEach(id => $(id).readOnly = !!p);
        const hasStock = p && (Number(p.total_on_hand) > 0);
        $('fWeight').readOnly = !!hasStock;
        $('fHint').textContent = p ? 'SKU và mã vạch không đổi sau khi tạo.' + (hasStock ? ' Đang có tồn kho nên không đổi được trọng lượng (BR04).' : '') : '';
        if (p) {
            $('fSku').value = p.sku; $('fBarcode').value = p.barcode; $('fName').value = p.product_name; $('fUnit').value = p.unit;
            $('fWeight').value = p.unit_weight_kg; $('fMin').value = p.min_safety_stock; $('fMax').value = p.max_safety_stock;
        }
        modal.show();
    }

    $('btnAdd').addEventListener('click', () => openForm(null));
    $('q').addEventListener('input', WMS.ui.debounce(() => { page = 1; render(); }, 200));
    $('statusFilter').addEventListener('change', () => { page = 1; render(); });
    $('tbody').addEventListener('click', async e => {
        const edit = e.target.closest('[data-edit]'), tog = e.target.closest('[data-toggle]');
        if (edit) return openForm(all.find(p => p.id == edit.dataset.edit));
        if (tog) {
            const p = all.find(x => x.id == tog.dataset.toggle);
            const ok = await WMS.ui.confirm({ title: p.is_active ? 'Khóa sản phẩm' : 'Mở khóa sản phẩm', danger: p.is_active,
                message: p.is_active ? `Khóa ${p.sku}? Sản phẩm bị khóa sẽ không thể lập phiếu nhập/xuất mới.` : `Mở khóa ${p.sku}?` });
            if (ok && await run(() => WMS.api.put(`/api/products/${p.id}`, { is_active: !p.is_active }))) load();
        }
    });

    $('productForm').addEventListener('submit', async e => {
        e.preventDefault();
        if (!e.target.reportValidity()) return;
        const body = { product_name: $('fName').value.trim(), unit: $('fUnit').value.trim(), unit_weight_kg: parseFloat($('fWeight').value),
                       min_safety_stock: parseInt($('fMin').value, 10), max_safety_stock: parseInt($('fMax').value, 10) };
        const btn = $('btnSave'); WMS.ui.setBusy(btn, true);
        const res = await run(() => editing ? WMS.api.put(`/api/products/${editing.id}`, body)
            : WMS.api.post('/api/products', { ...body, sku: $('fSku').value.trim(), barcode: $('fBarcode').value.trim() }));
        WMS.ui.setBusy(btn, false);
        if (res) { modal.hide(); load(); }
    });

    load();
    WMS.poll(load, 15000);
});
