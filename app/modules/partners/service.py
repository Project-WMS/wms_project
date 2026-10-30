"""FR1 - Danh mục Đối tác: Nhà cung cấp (phiếu nhập) và Khách hàng (phiếu xuất)."""
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.utils import first, rows

TYPE_LABEL = {"supplier": "Nhà cung cấp", "customer": "Khách hàng"}


def list_partners(db: Session, ptype: str = None) -> list:
    sql = "SELECT id, partner_code, partner_name, type, phone, address FROM partners"
    params = {}
    if ptype in TYPE_LABEL:
        sql += " WHERE type = :t"
        params["t"] = ptype
    return rows(db.execute(text(sql + " ORDER BY type, partner_name"), params))


def ensure_partner(db: Session, partner_id: int, ptype: str) -> dict:
    p = first(db.execute(text("SELECT id, partner_name, type FROM partners WHERE id = :id"), {"id": partner_id}))
    if not p:
        raise HTTPException(404, "Đối tác không tồn tại!")
    if p["type"] != ptype:
        raise HTTPException(400, f"Đối tác '{p['partner_name']}' không phải {TYPE_LABEL[ptype]}!")
    return p


def create_partner(db: Session, data: dict) -> dict:
    if data["type"] not in TYPE_LABEL:
        raise HTTPException(400, "Loại đối tác phải là Nhà cung cấp (supplier) hoặc Khách hàng (customer)!")
    code = data["partner_code"].strip().upper()
    if db.execute(text("SELECT 1 FROM partners WHERE partner_code = :c"), {"c": code}).first():
        raise HTTPException(400, "Mã đối tác đã tồn tại!")
    pid = db.execute(text("""
        INSERT INTO partners (partner_code, partner_name, type, phone, address)
        VALUES (:c, :n, :t, :p, :a) RETURNING id
    """), {"c": code, "n": data["partner_name"].strip(), "t": data["type"],
           "p": (data.get("phone") or "").strip() or None, "a": (data.get("address") or "").strip() or None}).scalar()
    db.commit()
    return {"message": f"Đã thêm đối tác {data['partner_name'].strip()}!", "id": pid}


def update_partner(db: Session, partner_id: int, data: dict) -> dict:
    cur = first(db.execute(text("SELECT id, partner_name FROM partners WHERE id = :id FOR UPDATE"), {"id": partner_id}))
    if not cur:
        raise HTTPException(404, "Đối tác không tồn tại!")
    fields = {}
    if data.get("partner_name") is not None:
        fields["partner_name"] = data["partner_name"].strip()
    for k in ("phone", "address"):
        if k in data:
            fields[k] = (data[k] or "").strip() or None
    if not fields:
        raise HTTPException(400, "Không có thông tin nào để cập nhật!")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    db.execute(text(f"UPDATE partners SET {sets} WHERE id = :id"), {**fields, "id": partner_id})
    db.commit()
    return {"message": f"Đã cập nhật đối tác {fields.get('partner_name', cur['partner_name'])}!"}
