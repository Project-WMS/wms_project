WMS.ready(function () {
    const { esc, num, run, badge } = WMS.ui;
    const $ = id => document.getElementById(id);
    const modal = new bootstrap.Modal($('locationModal')), qrModal = new bootstrap.Modal($('qrModal'));
    let all = [], view = 'table', editing = null, lastSig = '';

    function drawQR(el, text, size) {
        el.innerHTML = '';
        if (typeof QRCode === 'undefined') { el.innerHTML = `<span class="text-muted small">(Không tải được thư viện QR)</span>`; return; }
        new QRCode(el, { text, width: size, height: size, correctLevel: QRCode.CorrectLevel.M });
    }
    const capClass = p => p >= 90 ? 'full' : (p >= 70 ? 'warn' : '');
    const pct = l => Math.min(100, Math.round(Number(l.current_weight_kg) / Number(l.max_capacity_kg) * 1000) / 10);

    function filtered() {
        const q = $('q').value.trim().toLowerCase(), st = $('statusFilter').value;
        return all.filter(l => (!st || l.status === st) && (!q || l.location_code.toLowerCase().includes(q)));
    }

    function render() {
        const list = filtered();
        $('tbody').innerHTML = list.map(l => {
            const p = pct(l);
            return `<tr><td class="ledger-ref fw-semibold">${esc(l.location_code)}</td>
                <td>${esc(l.zone)} / ${esc(l.aisle)} / ${esc(l.rack)} / ${esc(l.shelf_level)} / ${esc(l.bin)}</td>
                <td><div class="d-flex justify-content-between small"><span>${num(l.current_weight_kg)} / ${num(l.max_capacity_kg)} kg</span><b>${p}%</b></div>
                    <div class="cap-bar mt-1"><span class="${capClass(p)}" style="width:${p}%"></span></div>
                    ${Number(l.pending_weight_kg) > 0 ? `<div class="line-hint">+ ${num(l.pending_weight_kg)} kg đang chờ xếp</div>` : ''}</td>
                <td class="num">${num(l.lot_count)}</td><td>${badge('location', l.status)}</td>
                <td class="text-nowrap text-end"><button class="btn btn-sm btn-outline-secondary" data-qr="${l.id}" title="Xem mã QR"><i class="fa-solid fa-qrcode"></i></button>
                    <button class="btn btn-sm btn-outline-primary" data-edit="${l.id}" title="Sửa"><i class="fa-solid fa-pen"></i></button></td></tr>`;
        }).join('') || WMS.ui.empty(6, 'fa-qrcode', 'Chưa có ô kệ nào phù hợp');

        if (view === 'grid') {
            $('gridView').innerHTML = list.map(l => `<div class="qr-card"><div class="qr-box" data-qrbox="${esc(l.location_code)}"></div>
                <div class="code mt-2">${esc(l.location_code)}</div><div class="small text-muted">${num(l.max_capacity_kg)} kg • ${esc(l.status)}</div></div>`).join('')
                || '<div class="empty-state w-100">Chưa có ô kệ nào phù hợp</div>';
            document.querySelectorAll('[data-qrbox]').forEach(b => drawQR(b, b.dataset.qrbox, 128));
        }
    }

    function setView(v) {
        view = v;
        $('tableView').classList.toggle('d-none', v !== 'table'); $('gridView').classList.toggle('d-none', v !== 'grid');
        $('btnPrintAll').classList.toggle('d-none', v !== 'grid');
        $('viewTable').classList.toggle('active', v === 'table'); $('viewGrid').classList.toggle('active', v === 'grid');
        lastSig = ''; render();
    }

    async function load() {
        try {
            const items = (await WMS.api.get('/api/locations')).items;
            const sig = JSON.stringify(items);
            if (sig === lastSig) return;                 // dữ liệu không đổi -> không vẽ lại (đỡ vẽ lại QR)
            lastSig = sig; all = items; render();
        } catch (e) { if (e.status !== 401) WMS.ui.error(e.message); }
    }

    function updatePreview() {
        const part = id => ($(id).value.trim().toUpperCase() || '…');
        $('codePreview').textContent = ['WH01', part('fZone'), part('fAisle'), part('fRack'), part('fLevel'), part('fBin')].join('-');
    }

    function openForm(l) {
        editing = l || null;
        $('locationForm').reset();
        $('locationModalTitle').textContent = l ? `Sửa ô kệ ${l.location_code}` : 'Thêm ô kệ';
        ['fZone', 'fAisle', 'fRack', 'fLevel', 'fBin'].forEach(id => $(id).readOnly = !!l);
        $('fHint').textContent = l ? 'Mã ô kệ không đổi sau khi tạo (đã in tem QR). Chỉ sửa được sức chứa và trạng thái; không giảm sức chứa thấp hơn tải trọng hiện có.' : '';
        if (l) {
            $('codePreview').textContent = l.location_code;
            $('fZone').value = l.zone; $('fAisle').value = l.aisle; $('fRack').value = l.rack; $('fLevel').value = l.shelf_level; $('fBin').value = l.bin;
            $('fCap').value = l.max_capacity_kg; $('fStatus').value = l.status;
        } else { updatePreview(); }
        modal.show();
    }

    ['fZone', 'fAisle', 'fRack', 'fLevel', 'fBin'].forEach(id => $(id).addEventListener('input', () => { if (!editing) updatePreview(); }));
    $('btnAdd').addEventListener('click', () => openForm(null));
    $('q').addEventListener('input', WMS.ui.debounce(render, 200));
    $('statusFilter').addEventListener('change', render);
    $('viewTable').addEventListener('click', () => setView('table'));
    $('viewGrid').addEventListener('click', () => setView('grid'));
    $('btnPrintAll').addEventListener('click', () => window.print());
    $('btnPrintOne').addEventListener('click', () => window.print());

    $('tbody').addEventListener('click', e => {
        const edit = e.target.closest('[data-edit]'), qr = e.target.closest('[data-qr]');
        if (edit) openForm(all.find(l => l.id == edit.dataset.edit));
        if (qr) {
            const l = all.find(x => x.id == qr.dataset.qr);
            $('qrCode').textContent = l.location_code; drawQR($('qrBig'), l.location_code, 220); qrModal.show();
        }
    });

    $('locationForm').addEventListener('submit', async e => {
        e.preventDefault();
        if (!e.target.reportValidity()) return;
        const btn = $('btnSave'); WMS.ui.setBusy(btn, true);
        const cap = parseFloat($('fCap').value), status = $('fStatus').value;
        const res = await run(() => editing ? WMS.api.put(`/api/locations/${editing.id}`, { max_capacity_kg: cap, status })
            : WMS.api.post('/api/locations', { warehouse_id: 1, zone: $('fZone').value, aisle: $('fAisle').value, rack: $('fRack').value,
                                               shelf_level: $('fLevel').value, bin: $('fBin').value, max_capacity_kg: cap, status }));
        WMS.ui.setBusy(btn, false);
        if (res) { modal.hide(); lastSig = ''; load(); }
    });

    load();
    WMS.poll(load, 10000);
});
