WMS.ready(function () {
    const { esc, num, date, datetime, badge, expiryBadge } = WMS.ui;
    let chart = null, tab = 'low', data = null, lastError = '';

    document.querySelectorAll('#alertTabs [data-tab]').forEach(btn => btn.addEventListener('click', () => {
        tab = btn.dataset.tab;
        document.querySelectorAll('#alertTabs [data-tab]').forEach(b => b.classList.toggle('active', b === btn));
        if (data) renderAlerts();
    }));

    function renderKpi(d) {
        document.getElementById('kpiOnHand').textContent = num(d.kpi.total_on_hand);
        document.getElementById('kpiAllocated').textContent = num(d.kpi.total_allocated);
        document.getElementById('kpiAvailable').textContent = num(d.kpi.total_available);
        document.getElementById('kpiAlerts').textContent = num(d.alert_total);
        document.getElementById('tilePutaway').textContent = d.pending.putaway_tasks;
        document.getElementById('tilePicking').textContent = d.pending.picking_tasks;
        document.getElementById('tileCounts').textContent = d.pending.open_counts;
        document.getElementById('tileUsers').textContent = d.pending.pending_users;
    }

    function renderChart(d) {
        const canvas = document.getElementById('chartStock');
        const empty = !d.by_product.length;
        document.getElementById('chartEmpty').classList.toggle('d-none', !empty);
        canvas.parentElement.classList.toggle('d-none', empty);
        if (empty || typeof Chart === 'undefined') return;
        const labels = d.by_product.map(p => p.sku);
        const onHand = d.by_product.map(p => Number(p.on_hand));
        const avail = d.by_product.map(p => Number(p.available));
        if (chart) {                                   // cập nhật tại chỗ để biểu đồ không nháy khi tự làm mới
            chart.data.labels = labels; chart.data.datasets[0].data = onHand; chart.data.datasets[1].data = avail;
            chart.update('none');
            return;
        }
        chart = new Chart(canvas, {
            type: 'bar',
            data: { labels, datasets: [
                { label: 'Tồn thực tế', data: onHand, backgroundColor: '#0d9488', borderRadius: 4 },
                { label: 'Khả dụng', data: avail, backgroundColor: '#93c5fd', borderRadius: 4 }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } },
                       scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
        });
    }

    function renderBins(d) {
        const top = d.bin_usage.slice(0, 8);
        document.getElementById('binUsage').innerHTML = top.length ? top.map(b => {
            const cls = b.percent >= 90 ? 'full' : (b.percent >= 70 ? 'warn' : '');
            return `<div class="mb-3"><div class="d-flex justify-content-between small"><span class="ledger-ref">${esc(b.location_code)}</span>
                <span>${num(b.current_kg)} / ${num(b.max_kg)} kg • <b>${b.percent}%</b></span></div>
                <div class="cap-bar mt-1"><span class="${cls}" style="width:${Math.min(b.percent, 100)}%"></span></div></div>`;
        }).join('') : '<div class="empty-state"><i class="fa-solid fa-box"></i>Chưa có ô kệ nào</div>';
    }

    function renderAlerts() {
        const d = data, head = document.getElementById('alertHead'), body = document.getElementById('alertBody');
        document.getElementById('cntLow').textContent = d.low_stock_alerts.length;
        document.getElementById('cntOver').textContent = d.over_stock_alerts.length;
        document.getElementById('cntExp').textContent = d.expiring_alerts.length;
        if (tab === 'low') {
            head.innerHTML = '<tr><th>Sản phẩm</th><th class="num">Khả dụng</th><th class="num">Tồn tối thiểu</th><th>Mức độ</th></tr>';
            body.innerHTML = d.low_stock_alerts.map(a => `<tr><td><b>${esc(a.sku)}</b><div class="sub">${esc(a.product_name)}</div></td>
                <td class="num">${num(a.total_available)} ${esc(a.unit)}</td><td class="num">${num(a.min_safety_stock)}</td>
                <td><span class="badge-soft bg-soft-danger">Thiếu hàng</span></td></tr>`).join('')
                || WMS.ui.empty(4, 'fa-circle-check', 'Không có sản phẩm nào dưới ngưỡng tối thiểu');
        } else if (tab === 'over') {
            head.innerHTML = '<tr><th>Sản phẩm</th><th class="num">Tồn thực tế</th><th class="num">Tồn tối đa</th><th>Mức độ</th></tr>';
            body.innerHTML = d.over_stock_alerts.map(a => `<tr><td><b>${esc(a.sku)}</b><div class="sub">${esc(a.product_name)}</div></td>
                <td class="num">${num(a.total_on_hand)} ${esc(a.unit)}</td><td class="num">${num(a.max_safety_stock)}</td>
                <td><span class="badge-soft bg-soft-warning">Vượt định mức</span></td></tr>`).join('')
                || WMS.ui.empty(4, 'fa-circle-check', 'Không có sản phẩm nào vượt ngưỡng tối đa');
        } else {
            head.innerHTML = '<tr><th>Sản phẩm</th><th>Ô kệ</th><th>Lô</th><th>Hạn dùng</th><th class="num">Tồn</th><th>Tình trạng</th></tr>';
            body.innerHTML = d.expiring_alerts.map(a => `<tr><td><b>${esc(a.sku)}</b><div class="sub">${esc(a.product_name)}</div></td>
                <td class="ledger-ref">${esc(a.location_code)}</td><td>${esc(a.batch_no)}</td><td>${date(a.expiry_date)}</td>
                <td class="num">${num(a.quantity_on_hand)}</td><td>${expiryBadge(a.days_left)}</td></tr>`).join('')
                || WMS.ui.empty(6, 'fa-circle-check', 'Không có lô hàng nào hết hạn hoặc cận date (30 ngày)');
        }
    }

    function renderLedger(d) {
        document.getElementById('recentLedger').innerHTML = d.recent_ledger.map(r => `<tr>
            <td class="text-nowrap">${datetime(r.created_at)}</td><td>${badge('ledger', r.transaction_type)}</td>
            <td class="ledger-ref">${esc(r.reference_code)}</td><td><b>${esc(r.sku)}</b></td><td>${esc(r.batch_no)}</td>
            <td class="num ${r.quantity_change >= 0 ? 'qty-in' : 'qty-out'}">${r.quantity_change > 0 ? '+' : ''}${num(r.quantity_change)}</td>
            <td class="num">${num(r.balance_after)}</td><td>${esc(r.performer)}</td></tr>`).join('')
            || WMS.ui.empty(8, 'fa-book', 'Chưa có biến động kho nào');
    }

    async function load() {
        try {
            data = await WMS.api.get('/api/dashboard');
            lastError = '';
            renderKpi(data); renderChart(data); renderBins(data); renderAlerts(); renderLedger(data);
        } catch (e) {
            if (e.status !== 401 && e.message !== lastError) { lastError = e.message; WMS.ui.error(e.message); }
        }
    }
    load();
    WMS.poll(load, 5000);
});
