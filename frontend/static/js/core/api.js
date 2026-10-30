/* Lớp gọi API + quản lý phiên đăng nhập (JWT lưu trong localStorage) */
(function (w) {
    const WMS = (w.WMS = w.WMS || {});
    const TOKEN_KEY = 'wms_token';
    const USER_KEY = 'wms_user';

    WMS.session = {
        token() { return localStorage.getItem(TOKEN_KEY); },
        user() { try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch (_) { return null; } },
        save(token, user) {
            if (token) localStorage.setItem(TOKEN_KEY, token);
            localStorage.setItem(USER_KEY, JSON.stringify(user));
        },
        clear() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); },
        logout(reason) { this.clear(); location.href = '/login' + (reason ? '?reason=' + reason : ''); },
    };

    class ApiError extends Error {
        constructor(message, status) { super(message); this.status = status; }
    }
    WMS.ApiError = ApiError;

    function errText(data) {
        if (!data) return 'Có lỗi xảy ra, vui lòng thử lại.';
        if (typeof data.detail === 'string') return data.detail;
        if (Array.isArray(data.detail)) return data.detail.map(d => d.msg || d).join(' ');
        return data.message || 'Có lỗi xảy ra, vui lòng thử lại.';
    }

    async function request(method, url, body, opts) {
        opts = opts || {};
        const headers = {};
        if (body !== undefined) headers['Content-Type'] = 'application/json';
        if (opts.auth !== false) headers['Authorization'] = 'Bearer ' + (WMS.session.token() || '');
        let res;
        try {
            res = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
        } catch (_) {
            throw new ApiError('Không kết nối được máy chủ. Hãy kiểm tra mạng / FastAPI!', 0);
        }
        let data = null;
        try { data = await res.json(); } catch (_) { /* phản hồi không có JSON */ }
        if (res.status === 401 && opts.auth !== false) {
            WMS.session.logout('expired');
            throw new ApiError(errText(data), 401);
        }
        if (!res.ok) throw new ApiError(errText(data), res.status);
        return data;
    }

    function withQuery(url, params) {
        if (!params) return url;
        const qs = Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== null && v !== '')
            .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
        return qs ? url + (url.includes('?') ? '&' : '?') + qs : url;
    }

    WMS.api = {
        get: (url, params, opts) => request('GET', withQuery(url, params), undefined, opts),
        post: (url, body, opts) => request('POST', url, body === undefined ? {} : body, opts),
        put: (url, body, opts) => request('PUT', url, body, opts),
        del: (url, opts) => request('DELETE', url, undefined, opts),
    };
})(window);
