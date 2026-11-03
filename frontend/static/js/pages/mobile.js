WMS.ready(function () {
    const { esc, num, date } = WMS.ui;
    const $ = id => document.getElementById(id);
    const scanModalEl = $('scanModal');
    const scanModal = window.bootstrap?.Modal ? new bootstrap.Modal(scanModalEl) : null;
    let screen = 'dashboard';
    let taskKind = 'putaway';
    let data = { putaway_tasks: [], picking_tasks: [] };
    let listSignature = '';
    let scanner = null;
    let scanTarget = null;
    let pendingStart = null;
    let loading = false;
    let busy = false;
    let lastLoadError = '';
    let selectedTask = null;
    let selectedKind = '';

    if (WMS.user().role !== 'worker') $('btnBackOffice').classList.remove('d-none');

    const vibrate = pattern => {
        if (navigator.vibrate) navigator.vibrate(pattern);
    };

    function taskQuantity(kind, task) {
        return kind === 'putaway' ? task.assigned_qty : task.allocated_qty;
    }

    function taskEntries(kind) {
        const putaway = (data.putaway_tasks || []).map((task, index) => ({
            kind: 'putaway',
            task,
            priority: false,
            index
        }));
        const picking = (data.picking_tasks || []).map((task, index) => ({
            kind: 'picking',
            task,
            priority: index === 0,
            index
        }));
        if (kind === 'putaway') return putaway;
        if (kind === 'picking') return picking;
        return [...putaway, ...picking];
    }

    function renderCounts() {
        const putawayCount = data.putaway_tasks.length;
        const pickingCount = data.picking_tasks.length;
        $('cntPutaway').textContent = num(putawayCount);
        $('cntPicking').textContent = num(pickingCount);
        $('cntAll').textContent = num(putawayCount + pickingCount);
    }

    function renderTaskCard(entry) {
        const { kind, task, priority } = entry;
        const putaway = kind === 'putaway';
        const quantity = taskQuantity(kind, task);
        const reference = putaway ? task.receipt_code : task.issue_code;
        return `<button class="m-task-item" type="button" data-kind="${kind}" data-id="${Number(task.task_id)}" data-qty="${Number(quantity)}">
            <span class="m-task-item-top">
                <span class="m-ref">${esc(reference)}</span>
                <span class="d-flex gap-1">
                    <span class="m-type-badge">${putaway ? 'Xếp kệ' : 'Lấy hàng'}</span>
                    ${priority ? '<span class="m-fefo-badge">Ưu tiên FEFO</span>' : ''}
                </span>
            </span>
            <span class="m-task-product">${esc(task.product_name)}</span>
            <span class="m-task-sku">SKU ${esc(task.sku)}</span>
            <span class="m-task-metadata">
                <span><small>Lô hàng</small>${esc(task.batch_no)}</span>
                <span><small>Hạn sử dụng</small>${date(task.expiry_date)}</span>
                <span><small>Số lượng</small>${num(quantity)} ${esc(task.unit)}</span>
                <span class="m-task-location"><small>${putaway ? 'Ô kệ đích' : 'Vị trí lấy hàng'}</small><span>${esc(task.location_code)}</span></span>
            </span>
            <span class="m-task-open">Xem chi tiết <i class="fa-solid fa-arrow-right" aria-hidden="true"></i></span>
        </button>`;
    }

    function renderList(force) {
        const entries = taskEntries(taskKind);
        const signature = taskKind + JSON.stringify(entries.map(({ kind, task, priority }) => [
            kind, task.task_id, task.receipt_code, task.issue_code, task.sku, task.product_name,
            task.unit, task.location_code, task.batch_no, task.expiry_date,
            taskQuantity(kind, task), priority
        ]));
        $('listSummary').textContent = `${num(entries.length)} phiếu đang chờ`;
        $('taskList').setAttribute('aria-busy', 'false');
        if (!force && signature === listSignature) return;
        listSignature = signature;
        $('taskList').innerHTML = entries.length
            ? entries.map(renderTaskCard).join('')
            : `<div class="m-empty-state" role="status">
                <i class="fa-solid fa-clipboard-check" aria-hidden="true"></i>
                <strong>Chưa có phiếu ${taskKind === 'putaway' ? 'xếp kệ' : taskKind === 'picking' ? 'lấy hàng' : 'nhiệm vụ'} đang chờ.</strong>
                <p>Dữ liệu sẽ được cập nhật khi hệ thống có phiếu mới.</p>
            </div>`;
    }

    function showScreen(next) {
        screen = next;
        $('dashboardView').hidden = next !== 'dashboard';
        $('listView').hidden = next !== 'list';
        $('detailView').hidden = next !== 'detail';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function openTaskList(kind) {
        taskKind = kind;
        listSignature = '';
        $('listTitle').textContent = kind === 'putaway'
            ? 'Phiếu xếp kệ'
            : kind === 'picking' ? 'Phiếu lấy hàng' : 'Tất cả nhiệm vụ';
        $('listDescription').textContent = kind === 'picking'
            ? 'Danh sách giữ nguyên thứ tự ưu tiên FEFO của hệ thống.'
            : kind === 'all'
                ? 'Các phiếu đang chờ trong kho. Chọn một phiếu để xử lý.'
                : 'Chọn một phiếu để xem hàng hóa và vị trí cần xếp.';
        showScreen('list');
        renderList(true);
    }

    function findTask(kind, taskId) {
        const key = kind === 'putaway' ? 'putaway_tasks' : 'picking_tasks';
        return data[key].find(task => String(task.task_id) === String(taskId));
    }

    function openTaskDetail(kind, task, priority) {
        selectedTask = task;
        selectedKind = kind;
        const putaway = kind === 'putaway';
        const quantity = taskQuantity(kind, task);
        $('detailRef').textContent = putaway ? task.receipt_code : task.issue_code;
        $('detailPriority').classList.toggle('d-none', !priority);
        $('detailProduct').textContent = task.product_name;
        $('detailSku').textContent = `SKU ${task.sku}`;
        $('detailBatch').textContent = task.batch_no || '–';
        $('detailExpiry').textContent = date(task.expiry_date);
        $('detailQty').textContent = num(quantity);
        $('detailUnit').textContent = task.unit || '';
        $('detailLocation').textContent = task.location_code;
        $('locationAction').textContent = putaway ? 'Ô kệ đích' : 'Vị trí lấy hàng';
        $('locationHint').textContent = putaway
            ? 'Đối chiếu mã vị trí trên kệ trước khi xác nhận.'
            : 'Xác nhận đúng ô theo lô được hệ thống phân bổ FEFO.';
        $('confirmLabel').textContent = putaway ? 'Xác nhận xếp kệ' : 'Xác nhận lấy hàng';
        $('barcodeField').hidden = putaway;
        $('taskQr').value = '';
        $('taskBarcode').value = '';
        $('taskQty').value = String(quantity);
        $('taskQty').max = String(quantity);
        $('qtyLimit').textContent = `Tối đa ${num(quantity)} ${task.unit || ''}`;
        $('staleTaskNotice').hidden = true;
        $('btnConfirmTask').disabled = false;
        showScreen('detail');
        $('taskQr').focus({ preventScroll: true });
    }

    async function load(options = {}) {
        if (loading || busy) return;
        loading = true;
        if (options.manual) {
            $('btnRefresh').disabled = true;
            $('btnRefresh').classList.add('is-loading');
            $('refreshStatus').textContent = 'Đang làm mới dữ liệu';
        }
        try {
            const latest = await WMS.api.get('/api/mobile/tasks');
            data = {
                putaway_tasks: latest.putaway_tasks || [],
                picking_tasks: latest.picking_tasks || []
            };
            lastLoadError = '';
            renderCounts();
            if (screen === 'list') renderList(false);
            if (screen === 'detail' && selectedTask) {
                const current = findTask(selectedKind, selectedTask.task_id);
                if (!current) {
                    $('staleTaskNotice').hidden = false;
                    $('btnConfirmTask').disabled = true;
                } else {
                    selectedTask = current;
                }
            }
        } catch (error) {
            if (error.status !== 401 && error.message !== lastLoadError) {
                lastLoadError = error.message;
                WMS.ui.error(error.message);
            }
        } finally {
            loading = false;
            if (options.manual) {
                $('btnRefresh').disabled = false;
                $('btnRefresh').classList.remove('is-loading');
                $('refreshStatus').textContent = 'Đã làm mới dữ liệu';
            }
        }
    }

    async function stopScanner() {
        const activeScanner = scanner;
        scanner = null;
        scanTarget = null;
        if (!activeScanner) return;
        try {
            await activeScanner.stop();
        } catch (error) {
            console.debug('QR scanner was already stopped.', error);
        }
        try {
            activeScanner.clear();
        } catch (error) {
            console.error('Unable to clear the QR scanner.', error);
        }
    }

    function openScanner(input, title) {
        if (!scanModal) {
            WMS.ui.error('Không mở được cửa sổ quét mã. Hãy tải lại trang hoặc nhập mã bằng tay.');
            return;
        }
        if (typeof Html5Qrcode === 'undefined') {
            WMS.ui.error('Không tải được thư viện quét mã. Hãy nhập mã bằng tay.');
            return;
        }
        scanTarget = input;
        $('scanTitle').textContent = title;
        pendingStart = async () => {
            try {
                scanner = new Html5Qrcode('qrReader');
                await scanner.start(
                    { facingMode: 'environment' },
                    { fps: 10, qrbox: { width: 240, height: 240 } },
                    text => {
                        if (scanTarget) {
                            scanTarget.value = text.trim();
                            scanTarget.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                        vibrate(120);
                        scanModal.hide();
                    },
                    () => {}
                );
            } catch (error) {
                console.error('Unable to start the mobile code scanner.', error);
                WMS.ui.error('Không mở được camera. Hãy cấp quyền và dùng HTTPS hoặc localhost, hoặc nhập mã bằng tay.');
                scanModal.hide();
            }
        };
        scanModal.show();
    }

    $('dashboardView').addEventListener('click', event => {
        const button = event.target.closest('.m-task-tile[data-task-kind]');
        if (!button || !['putaway', 'picking', 'all'].includes(button.dataset.taskKind)) return;
        openTaskList(button.dataset.taskKind);
    });
    $('btnBackDashboard').addEventListener('click', () => showScreen('dashboard'));
    $('btnBackList').addEventListener('click', () => {
        showScreen('list');
        renderList(true);
    });
    $('btnRefresh').addEventListener('click', () => load({ manual: true }));

    $('taskList').addEventListener('click', event => {
        const button = event.target.closest('.m-task-item');
        if (!button) return;
        const kind = button.dataset.kind;
        const task = findTask(kind, button.dataset.id);
        if (!task) {
            WMS.ui.error('Phiếu không còn trong danh sách chờ. Hãy làm mới dữ liệu.');
            return;
        }
        const priority = kind === 'picking' && (data.picking_tasks[0]?.task_id === task.task_id);
        openTaskDetail(kind, task, priority);
    });

    $('detailView').addEventListener('click', event => {
        const button = event.target.closest('.m-scan-button');
        if (!button) return;
        const input = button.dataset.field === 'qr' ? $('taskQr') : $('taskBarcode');
        openScanner(input, button.dataset.field === 'qr' ? 'Quét QR ô kệ' : 'Quét mã vạch sản phẩm');
    });

    if (scanModal) {
        scanModalEl.addEventListener('shown.bs.modal', () => {
            if (pendingStart) {
                const start = pendingStart;
                pendingStart = null;
                start();
            }
        });
        scanModalEl.addEventListener('hidden.bs.modal', () => {
            pendingStart = null;
            stopScanner();
        });
    }

    $('taskForm').addEventListener('submit', async event => {
        event.preventDefault();
        if (!selectedTask || busy) return;
        const qr = $('taskQr').value.trim();
        const barcode = $('taskBarcode').value.trim();
        const quantity = Number($('taskQty').value);
        const maxQuantity = Number(taskQuantity(selectedKind, selectedTask));
        const fail = message => {
            WMS.ui.error(message);
            vibrate([200, 100, 200]);
        };
        if (!qr) return fail('Hãy quét hoặc nhập mã QR của ô kệ trước khi xác nhận.');
        if (selectedKind === 'picking' && !barcode) return fail('Hãy quét hoặc nhập mã vạch sản phẩm trước khi xác nhận.');
        if (!Number.isInteger(quantity) || quantity < 1 || quantity > maxQuantity) {
            return fail(`Số lượng thực tế phải từ 1 đến ${num(maxQuantity)}.`);
        }

        busy = true;
        const button = $('btnConfirmTask');
        WMS.ui.setBusy(button, true, 'Đang xác nhận…');
        const endpoint = selectedKind === 'putaway'
            ? '/api/mobile/putaway/confirm'
            : '/api/mobile/picking/confirm';
        const body = selectedKind === 'putaway'
            ? { task_id: Number(selectedTask.task_id), scanned_qr: qr, actual_qty: quantity }
            : {
                task_id: Number(selectedTask.task_id),
                scanned_qr: qr,
                scanned_barcode: barcode,
                actual_qty: quantity
            };
        try {
            const result = await WMS.api.post(endpoint, body);
            WMS.ui.success(result.message);
            vibrate(100);
            if (selectedKind === 'putaway') {
                data.putaway_tasks = data.putaway_tasks.filter(task => task.task_id !== selectedTask.task_id);
            } else {
                data.picking_tasks = data.picking_tasks.filter(task => task.task_id !== selectedTask.task_id);
            }
            selectedTask = null;
            renderCounts();
            listSignature = '';
            showScreen('list');
            renderList(true);
            busy = false;
            WMS.ui.setBusy(button, false);
            await load();
        } catch (error) {
            if (error.status !== 401) fail(error.message);
        } finally {
            busy = false;
            WMS.ui.setBusy(button, false);
        }
    });

    renderCounts();
    load();
    WMS.poll(load, 3000);
});
