/* Dữ liệu cho các ô chọn trong biểu mẫu (sản phẩm đang dùng, ô kệ, nhà cung cấp, khách hàng) */
(function (w) {
    const WMS = (w.WMS = w.WMS || {});
    let cache = null, at = 0;
    WMS.lookups = async function (force) {
        if (!force && cache && Date.now() - at < 15000) return cache;
        cache = await WMS.api.get('/api/lookups');
        at = Date.now();
        return cache;
    };
    // Tải trọng còn trống của Bin (đã trừ hàng đang chờ xếp)
    WMS.freeKg = l => Math.max(0, Number(l.max_capacity_kg) - Number(l.current_weight_kg) - Number(l.pending_weight_kg || 0));
})(window);
