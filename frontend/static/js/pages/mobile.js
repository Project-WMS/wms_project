WMS.ready(function (me) {
    const { esc, num, date, run } = WMS.ui;
    const $ = id => document.getElementById(id);
    const scanModalEl = $('scanModal'), scanModal = new bootstrap.Modal(scanModalEl);
    let tab = 'putaway', data = { putaway_tasks: [], picking_tasks: [] }, lastSig = '', scanner = null, scanTarget = null, busy = false;

    if (me.role !== 'worker') $('btnBackOffice').classList.remove('d-none');   // Admin/Thủ kho có thể quay lại trang quản lý

    const vibrate = p => { try { if (navigator.vibrate) navigator.vibrate(p); } catch (_) { /* thiết bị không hỗ trợ */ } };

    // ---------- Vẽ danh sách nhiệm vụ ----------
    function card(kind, t, idx) {
        const putaway = kind === 'putaway', qty = putaway ? t.assigned_qty : t.allocated_qty;
        return `<div class="task-card${!putaway && idx === 0 ? ' priority' : ''}" data-kind="${kind}" data-id="${t.task_id}" data-qty="${qty}">
            <div class="d-flex justify-content-between align-items-center"><span class="ref">${esc(putaway ? t.receipt_code : t.issue_code)}</span>
                ${!putaway && idx === 0 ? '<span class="badge text-bg-warning">Ưu tiên FEFO</span>' : ''}</div>
            <div class="prod">${esc(t.sku)} — ${esc(t.product_name)}</div>
            <div class="meta">Lô <b>${esc(t.batch_no)}</b> • HSD ${date(t.expiry_date)} • <b>${num(qty)} ${esc(t.unit)}</b></div>
            <div class="target">${putaway ? 'Xếp vào ô' : 'Lấy hàng tại ô'}<br><b>${esc(t.location_code)}</b></div>
            <label class="form-label">Mã QR ô kệ</label>
            <div class="input-group mb-2"><input class="form-control f-qr" autocomplete="off" autocapitalize="characters" placeholder="Quét hoặc nhập mã ô kệ">
                <button class="btn btn-outline-info f-scan" data-field="qr" type="button" aria-label="Quét QR ô kệ"><i class="fa-solid fa-camera"></i></button></div>
            ${putaway ? '' : `<label class="form-label">Mã vạch sản phẩm</label>
            <div class="input-group mb-2"><input class="form-control f-bc" autocomplete="off" placeholder="Quét hoặc nhập mã vạch bao bì">
                <button class="btn btn-outline-info f-scan" data-field="bc" type="button" aria-label="Quét mã vạch"><i class="fa-solid fa-barcode"></i></button></div>`}
            <label class="form-label">Số lượng thực tế (tối đa ${num(qty)})</label>
            <input type="number" class="form-control f-qty mb-3" min="1" max="${qty}" step="1" value="${qty}" inputmode="numeric">
            <button class="btn ${putaway ? 'btn-success' : 'btn-warning'} w-100 f-confirm" type="button">
                <i class="fa-solid fa-check me-1"></i>${putaway ? 'Xác nhận xếp kệ' : 'Xác nhận lấy hàng'}</button></div>`;
    }

    function render(force) {
        const list = tab === 'putaway' ? data.putaway_tasks : data.picking_tasks;
        const sig = tab + JSON.stringify(list.map(t => [t.task_id, t.location_code, t.batch_no]));
        $('cntPutaway').textContent = data.putaway_tasks.length;
        $('cntPicking').textContent = data.picking_tasks.length;
        if (sig === lastSig && !force) return;            // danh sách không đổi -> không đụng DOM, giữ nguyên chữ đang gõ (NFR1)
        const saved = {};
        document.querySelectorAll('.task-card').forEach(c => {
            saved[c.dataset.id] = { qr: c.querySelector('.f-qr')?.value, bc: c.querySelector('.f-bc')?.value, qty: c.querySelector('.f-qty')?.value };
        });
        lastSig = sig;
        $('taskList').innerHTML = list.map((t, i) => card(tab, t, i)).join('') ||
            `<div class="m-empty"><i class="fa-solid fa-clipboard-check"></i>Không có nhiệm vụ ${tab === 'putaway' ? 'xếp kệ' : 'lấy hàng'} nào.</div>`;
        document.querySelectorAll('.task-card').forEach(c => {
            const s = saved[c.dataset.id]; if (!s) return;
            if (s.qr) c.querySelector('.f-qr').value = s.qr;
            if (s.bc && c.querySelector('.f-bc')) c.querySelector('.f-bc').value = s.bc;
            if (s.qty) c.querySelector('.f-qty').value = s.qty;
        });
    }

    async function load() {
        try { data = await WMS.api.get('/api/mobile/tasks'); render(false); }
        catch (e) { if (e.status !== 401 && !busy) WMS.ui.error(e.message); }
    }

    document.querySelectorAll('.m-tab').forEach(b => b.addEventListener('click', () => {
        tab = b.dataset.tab;
        document.querySelectorAll('.m-tab').forEach(x => x.classList.toggle('active', x === b)); render(true);
    }));
    $('btnRefresh').addEventListener('click', load);

    // ---------- Quét bằng camera ----------
    async function stopScanner() {
        if (scanner) { try { await scanner.stop(); } catch (_) { /* đã dừng */ } try { scanner.clear(); } catch (_) { /* ignore */ } scanner = null; }
    }
    let pendingStart = null;
    function openScanner(input, title) {
        if (typeof Html5Qrcode === 'undefined') { WMS.ui.error('Không tải được thư viện quét mã. Hãy nhập mã bằng tay.'); return; }
        scanTarget = input;
        $('scanTitle').textContent = title;
        // Chỉ bật camera sau khi hộp thoại đã mở xong: nếu đóng khi đang chạy hiệu ứng, Bootstrap sẽ bỏ qua lệnh hide()
        pendingStart = async () => {
            try {
                scanner = new Html5Qrcode('qrReader');
                await scanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: { width: 240, height: 240 } }, text => {
                    if (scanTarget) { scanTarget.value = text.trim(); scanTarget.dispatchEvent(new Event('input', { bubbles: true })); }
                    vibrate(120);
                    scanModal.hide();
                }, () => { /* chưa nhận diện được khung hình này */ });
            } catch (_) {
                WMS.ui.error('Không mở được camera (cần cấp quyền và truy cập qua HTTPS/localhost). Hãy nhập mã bằng tay.');
                scanModal.hide();
            }
        };
        scanModal.show();
    }
    scanModalEl.addEventListener('shown.bs.modal', () => { if (pendingStart) { const fn = pendingStart; pendingStart = null; fn(); } });
    scanModalEl.addEventListener('hidden.bs.modal', () => { pendingStart = null; stopScanner(); });

    // ---------- Xác nhận nhiệm vụ ----------
    $('taskList').addEventListener('click', async e => {
        const scan = e.target.closest('.f-scan'), ok = e.target.closest('.f-confirm');
        const c = e.target.closest('.task-card');
        if (!c) return;
        if (scan) return openScanner(c.querySelector(scan.dataset.field === 'qr' ? '.f-qr' : '.f-bc'), scan.dataset.field === 'qr' ? 'Quét QR ô kệ' : 'Quét mã vạch sản phẩm');
        if (!ok) return;

        const kind = c.dataset.kind, max = Number(c.dataset.qty);
        const qr = c.querySelector('.f-qr').value.trim(), bc = (c.querySelector('.f-bc')?.value || '').trim(), qty = parseInt(c.querySelector('.f-qty').value, 10);
        const fail = msg => { WMS.ui.error(msg); vibrate([200, 100, 200]); };
        if (!qr) return fail('Hãy quét hoặc nhập mã QR của ô kệ trước khi xác nhận.');
        if (kind === 'picking' && !bc) return fail('Hãy quét mã vạch sản phẩm trên bao bì trước khi xác nhận.');
        if (!Number.isInteger(qty) || qty < 1 || qty > max) return fail(`Số lượng thực tế phải từ 1 đến ${max}.`);

        busy = true; WMS.ui.setBusy(ok, true);
        const url = kind === 'putaway' ? '/api/mobile/putaway/confirm' : '/api/mobile/picking/confirm';
        const body = kind === 'putaway' ? { task_id: Number(c.dataset.id), scanned_qr: qr, actual_qty: qty }
                                        : { task_id: Number(c.dataset.id), scanned_qr: qr, scanned_barcode: bc, actual_qty: qty };
        let res = null;
        try { res = await WMS.api.post(url, body); WMS.ui.success(res.message); vibrate(100); }
        catch (err) { if (err.status !== 401) fail(err.message); }
        busy = false; WMS.ui.setBusy(ok, false);
        if (res) await load();
    });

    load();
    WMS.poll(load, 3000);
});
