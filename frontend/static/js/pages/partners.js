WMS.ready(function () {
    const { esc, run } = WMS.ui;
    const PAGE_SIZE = 10, $ = id => document.getElementById(id);
    const modal = new bootstrap.Modal($('partnerModal'));
    let all = [], page = 1, type = '', editing = null;

    const typeBadge = t => t === 'supplier' ? '<span class="badge-soft bg-soft-primary">Nhà cung cấp</span>' : '<span class="badge-soft bg-soft-info">Khách hàng</span>';

    function filtered() {
        const q = $('q').value.trim().toLowerCase();
        return all.filter(p => (!type || p.type === type) && (!q || [p.partner_code, p.partner_name, p.phone].some(v => String(v || '').toLowerCase().includes(q))));
    }
    function render() {
        const list = filtered();
        $('tbody').innerHTML = WMS.ui.paginate(list, page, PAGE_SIZE).map(p => `<tr>
            <td class="ledger-ref fw-semibold">${esc(p.partner_code)}</td><td>${esc(p.partner_name)}</td><td>${typeBadge(p.type)}</td>
            <td>${esc(p.phone) || '–'}</td><td>${esc(p.address) || '–'}</td>
            <td class="text-end"><button class="btn btn-sm btn-outline-primary" data-edit="${p.id}"><i class="fa-solid fa-pen"></i></button></td></tr>`).join('')
            || WMS.ui.empty(6, 'fa-handshake', 'Chưa có đối tác nào phù hợp');
        WMS.ui.renderPager($('pager'), { total: list.length, page, size: PAGE_SIZE, onChange: p => { page = p; render(); } });
    }
    async function load() {
        try { all = (await WMS.api.get('/api/partners')).items; render(); }
        catch (e) { if (e.status !== 401) WMS.ui.error(e.message); }
    }

    function openForm(p) {
        editing = p || null;
        $('partnerForm').reset();
        $('partnerModalTitle').textContent = p ? `Sửa đối tác ${p.partner_code}` : 'Thêm đối tác';
        $('fCode').readOnly = !!p; $('fType').disabled = !!p;
        $('fHint').textContent = p ? 'Mã và loại đối tác không đổi sau khi tạo.' : '';
        if (p) { $('fCode').value = p.partner_code; $('fType').value = p.type; $('fName').value = p.partner_name; $('fPhone').value = p.phone || ''; $('fAddress').value = p.address || ''; }
        else if (type) $('fType').value = type;
        modal.show();
    }

    document.querySelectorAll('#typeTabs [data-type]').forEach(b => b.addEventListener('click', () => {
        type = b.dataset.type; page = 1;
        document.querySelectorAll('#typeTabs [data-type]').forEach(x => x.classList.toggle('active', x === b)); render();
    }));
    $('q').addEventListener('input', WMS.ui.debounce(() => { page = 1; render(); }, 200));
    $('btnAdd').addEventListener('click', () => openForm(null));
    $('tbody').addEventListener('click', e => { const b = e.target.closest('[data-edit]'); if (b) openForm(all.find(p => p.id == b.dataset.edit)); });

    $('partnerForm').addEventListener('submit', async e => {
        e.preventDefault();
        if (!e.target.reportValidity()) return;
        const btn = $('btnSave'); WMS.ui.setBusy(btn, true);
        const base = { partner_name: $('fName').value.trim(), phone: $('fPhone').value.trim(), address: $('fAddress').value.trim() };
        const res = await run(() => editing ? WMS.api.put(`/api/partners/${editing.id}`, base)
            : WMS.api.post('/api/partners', { ...base, partner_code: $('fCode').value.trim(), type: $('fType').value }));
        WMS.ui.setBusy(btn, false);
        if (res) { modal.hide(); load(); }
    });

    load();
    WMS.poll(load, 20000);
});
