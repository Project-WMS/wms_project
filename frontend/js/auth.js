/* Tiện ích đăng nhập dùng chung cho index.html và mobile.html */
const WMS_TOKEN_KEY = 'wms_token';
const WMS_USER_KEY = 'wms_user';

function wmsToken() { return localStorage.getItem(WMS_TOKEN_KEY); }

function wmsUser() {
    try { return JSON.parse(localStorage.getItem(WMS_USER_KEY) || 'null'); } catch (_) { return null; }
}

function wmsLogout() {
    localStorage.removeItem(WMS_TOKEN_KEY);
    localStorage.removeItem(WMS_USER_KEY);
    location.href = '/login';
}

/* fetch tự gắn token; gặp 401 (hết phiên/bị khóa) thì quay về trang đăng nhập */
async function apiFetch(url, options = {}) {
    const headers = Object.assign({}, options.headers || {}, { 'Authorization': 'Bearer ' + (wmsToken() || '') });
    const res = await fetch(url, Object.assign({}, options, { headers }));
    if (res.status === 401) { wmsLogout(); throw new Error('unauthorized'); }
    return res;
}

/* Bắt buộc đã đăng nhập và đúng vai trò; trả về user hoặc null (đã chuyển trang) */
function requireLogin(allowedRoles) {
    const u = wmsUser();
    if (!wmsToken() || !u) { location.href = '/login'; return null; }
    if (allowedRoles && !allowedRoles.includes(u.role)) {
        location.href = u.role === 'worker' ? '/mobile' : '/';
        return null;
    }
    return u;
}

const ROLE_LABEL = { admin: 'Admin', manager: 'Thủ kho', worker: 'Công nhân' };
