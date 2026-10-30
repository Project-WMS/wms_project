/* Tiện ích giao diện dùng chung: escape HTML, định dạng, toast, hộp xác nhận, phân trang, CSV, select giữ trạng thái */
(function (w) {
    const WMS = (w.WMS = w.WMS || {});
    const ui = (WMS.ui = {});

    // Chống chèn HTML/JS từ dữ liệu người dùng nhập (NFR3 - XSS)
    ui.esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    // ---------- Định dạng ----------
    ui.num = v => (v === null || v === undefined || v === '') ? '–' : Number(v).toLocaleString('vi-VN', { maximumFractionDigits: 2 });
    ui.kg = v => ui.num(v) + ' kg';
    ui.date = iso => {
        if (!iso) return '–';
        const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
        return m ? `${m[3]}/${m[2]}/${m[1]}` : ui.esc(iso);
    };
    // Thời gian trong DB lưu UTC -> hiển thị giờ Việt Nam (UTC+7)
    ui.datetime = iso => {
        if (!iso) return '–';
        let s = String(iso).replace(' ', 'T');
        if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(s)) s += 'Z';
        const d = new Date(s);
        if (isNaN(d)) return ui.esc(iso);
        return d.toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
    };
    ui.todayISO = () => {
        const d = new Date(Date.now() + 7 * 3600 * 1000); // ngày theo giờ VN
        return d.toISOString().slice(0, 10);
    };
    ui.expiryBadge = (days) => {
        if (days === null || days === undefined) return '';
        if (days < 0) return `<span class="badge-soft bg-soft-danger">Đã hết hạn (quá ${Math.abs(days)} ngày)</span>`;
        if (days <= 30) return `<span class="badge-soft bg-soft-warning">Cận date • còn ${days} ngày</span>`;
        return `<span class="badge-soft bg-soft-success">Còn ${days} ngày</span>`;
    };

    const BADGES = {
        receipt: { approved: ['Chờ xếp kệ', 'warning'], putting_away: ['Đang xếp kệ', 'info'], completed: ['Hoàn tất', 'success'], draft: ['Nháp', 'secondary'] },
        issue: { allocated: ['Chờ lấy hàng', 'warning'], picking: ['Đang lấy hàng', 'info'], completed: ['Hoàn tất', 'success'], draft: ['Nháp', 'secondary'] },
        count: { draft: ['Nháp', 'secondary'], counting: ['Đang kiểm đếm', 'info'], reconciled: ['Đã cân bằng', 'success'] },
        location: { active: ['Hoạt động', 'success'], maintenance: ['Bảo trì', 'warning'], locked: ['Đã khóa', 'danger'] },
        ledger: { PUTAWAY: ['Xếp kệ', 'success'], PICK: ['Lấy hàng', 'danger'], TRANSFER: ['Điều chuyển', 'primary'], COUNT_ADJUST: ['Kiểm kê', 'warning'] },
        task: { pending: ['Chờ xếp', 'warning'], completed: ['Đã xếp', 'success'], allocated: ['Chờ lấy', 'warning'], picked: ['Đã lấy', 'success'] },
        transfer: { completed: ['Hoàn tất', 'success'], draft: ['Nháp', 'secondary'] },
    };
    ui.badge = (kind, status) => {
        const [label, color] = (BADGES[kind] || {})[status] || [status, 'secondary'];
        return `<span class="badge-soft bg-soft-${color}">${ui.esc(label)}</span>`;
    };
    ui.roleLabel = r => ({ admin: 'Admin', manager: 'Thủ kho', worker: 'Công nhân' }[r] || r);

    // ---------- Toast & hộp xác nhận ----------
    ui.toast = (message, type) => {
        const box = document.getElementById('toastContainer');
        if (!box) return alert(message);
        const color = { success: 'text-bg-success', error: 'text-bg-danger', warning: 'text-bg-warning' }[type || 'success'];
        const el = document.createElement('div');
        el.className = `toast align-items-center border-0 ${color}`;
        el.setAttribute('role', 'alert');
        el.innerHTML = `<div class="d-flex"><div class="toast-body">${ui.esc(message)}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Đóng"></button></div>`;
        box.appendChild(el);
        const t = new bootstrap.Toast(el, { delay: type === 'error' ? 6500 : 3500 });
        el.addEventListener('hidden.bs.toast', () => el.remove());
        t.show();
    };
    ui.success = m => ui.toast(m, 'success');
    ui.error = m => ui.toast(m, 'error');

    ui.confirm = ({ title = 'Xác nhận', message = '', okText = 'Đồng ý', danger = false } = {}) => new Promise(resolve => {
        const el = document.getElementById('confirmModal');
        el.querySelector('.modal-title').textContent = title;
        el.querySelector('.modal-body').textContent = message;
        const ok = el.querySelector('[data-confirm-ok]');
        ok.textContent = okText;
        ok.className = 'btn ' + (danger ? 'btn-danger' : 'btn-primary');
        const modal = bootstrap.Modal.getOrCreateInstance(el);
        let answered = false;
        const done = v => { if (!answered) { answered = true; resolve(v); } };
        ok.onclick = () => { done(true); modal.hide(); };
        el.addEventListener('hidden.bs.modal', () => done(false), { once: true });
        modal.show();
    });

    // Gọi API và tự hiện thông báo; trả về dữ liệu hoặc null khi lỗi
    ui.run = async (fn, { successMsg, silent } = {}) => {
        try {
            const res = await fn();
            const msg = successMsg || (res && res.message);
            if (msg && !silent) ui.success(msg);
            return res || true;
        } catch (e) {
            if (e.status !== 401) ui.error(e.message);
            return null;
        }
    };

    ui.setBusy = (btn, busy, text) => {
        if (!btn) return;
        if (busy) { btn.dataset.label = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>${text || 'Đang xử lý...'}`; }
        else { btn.disabled = false; if (btn.dataset.label) btn.innerHTML = btn.dataset.label; }
    };

    // ---------- Select: đổ lại option nhưng giữ nguyên lựa chọn đang có (NFR1) ----------
    ui.fillSelect = (sel, options, { placeholder } = {}) => {
        if (typeof sel === 'string') sel = document.getElementById(sel);
        const html = (placeholder !== undefined ? `<option value="">${ui.esc(placeholder)}</option>` : '') +
            options.map(o => `<option value="${ui.esc(o.value)}"${o.disabled ? ' disabled' : ''}>${ui.esc(o.label)}</option>`).join('');
        if (sel.dataset.sig === html) return;
        const keep = sel.value;
        sel.innerHTML = html;
        sel.dataset.sig = html;
        if (keep && [...sel.options].some(o => o.value === keep)) sel.value = keep;
    };

    ui.debounce = (fn, ms = 300) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

    // ---------- Phân trang ----------
    ui.paginate = (items, page, size) => items.slice((page - 1) * size, page * size);
    ui.renderPager = (el, { total, page, size, onChange }) => {
        const pages = Math.max(1, Math.ceil(total / size));
        page = Math.min(Math.max(page, 1), pages);
        const from = total ? (page - 1) * size + 1 : 0, to = Math.min(page * size, total);
        const nums = [];
        for (let p = Math.max(1, page - 2); p <= Math.min(pages, page + 2); p++) nums.push(p);
        const li = (p, label, disabled, active) =>
            `<li class="page-item${disabled ? ' disabled' : ''}${active ? ' active' : ''}"><a class="page-link" href="#" data-page="${p}">${label}</a></li>`;
        el.innerHTML = `<div>Hiển thị ${from}–${to} / ${total}</div>
            <ul class="pagination pagination-sm mb-0">${li(page - 1, '&laquo;', page <= 1)}${nums.map(p => li(p, p, false, p === page)).join('')}${li(page + 1, '&raquo;', page >= pages)}</ul>`;
        el.querySelectorAll('a[data-page]').forEach(a => a.addEventListener('click', e => {
            e.preventDefault();
            const p = Number(a.dataset.page);
            if (!a.parentElement.classList.contains('disabled') && p !== page) onChange(p);
        }));
    };

    // ---------- Xuất CSV (UTF-8 BOM để Excel đọc đúng tiếng Việt) ----------
    ui.downloadCSV = (filename, headers, rows) => {
        const q = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
        const csv = '\ufeff' + [headers, ...rows].map(r => r.map(q).join(',')).join('\r\n');
        const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
        const a = document.createElement('a');
        a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    };

    ui.empty = (cols, icon, text) => `<tr><td colspan="${cols}"><div class="empty-state"><i class="fa-solid ${icon}"></i>${ui.esc(text)}</div></td></tr>`;

    // Tự làm mới dữ liệu nhưng tạm dừng khi tab ẩn hoặc đang mở hộp thoại -> không mất thao tác đang dở (NFR1)
    WMS.poll = (fn, ms) => {
        const id = setInterval(() => {
            if (document.hidden || document.querySelector('.modal.show')) return;
            fn();
        }, ms);
        return () => clearInterval(id);
    };
})(window);
