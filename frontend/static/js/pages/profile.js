WMS.ready(function (me) {
    const $ = id => document.getElementById(id);
    const fields = {
        fullName: $('pFullName'),
        username: $('pUsername'),
        role: $('pRole'),
        status: $('pStatus'),
        fullNameInput: $('fFullName'),
    };

    function renderAccount(user) {
        fields.fullName.textContent = user.full_name;
        fields.username.textContent = user.username;
        fields.role.textContent = WMS.ui.roleLabel(user.role);
        const approval = {
            approved: 'Đã duyệt',
            pending: 'Chờ duyệt',
            rejected: 'Đã từ chối',
        }[user.approval_status] || 'Không xác định';
        fields.status.textContent = user.is_active ? `${approval} · Đang hoạt động` : `${approval} · Đã khóa`;
        fields.fullNameInput.value = user.full_name;
    }

    async function refreshAccount() {
        try {
            const user = await WMS.api.get('/api/auth/me');
            WMS.session.save(null, user);
            renderAccount(user);
        } catch (error) {
            if (error.status !== 401) WMS.ui.error(error.message);
        }
    }

    renderAccount(me);
    refreshAccount();

    $('profileForm').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        if (!form.reportValidity()) return;
        const button = $('btnSaveProfile');
        WMS.ui.setBusy(button, true, 'Đang lưu…');
        try {
            const response = await WMS.api.put('/api/auth/me', { full_name: fields.fullNameInput.value.trim() });
            WMS.session.save(null, response.user);
            renderAccount(response.user);
            document.querySelectorAll('[data-user-name]').forEach(node => {
                node.textContent = response.user.full_name;
            });
            WMS.ui.success(response.message);
        } catch (error) {
            if (error.status !== 401) WMS.ui.error(error.message);
        } finally {
            WMS.ui.setBusy(button, false);
        }
    });

    $('pwForm').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        if (!form.reportValidity()) return;
        if ($('fNew').value !== $('fConfirm').value) {
            WMS.ui.error('Hai mật khẩu mới không khớp.');
            return;
        }
        const button = $('btnSave');
        WMS.ui.setBusy(button, true, 'Đang cập nhật…');
        try {
            const response = await WMS.api.post('/api/auth/change-password', {
                old_password: $('fOld').value,
                new_password: $('fNew').value,
            });
            WMS.ui.success(response.message);
            form.reset();
        } catch (error) {
            if (error.status !== 401) WMS.ui.error(error.message);
        } finally {
            WMS.ui.setBusy(button, false);
        }
    });
});
