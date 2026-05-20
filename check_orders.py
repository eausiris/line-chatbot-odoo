from app.services.odoo_service import odoo

# ทดสอบด้วย partner ก่อน
partner_ids = odoo._execute(
    "res.partner", "search",
    [["customer_rank", ">", 0]],
    limit=3
)
partners = odoo._execute(
    "res.partner", "read", partner_ids,
    fields=["id", "name", "ref"]
)
print("Partners:", partners)

# ทดสอบ sale.order ด้วย id ที่รู้จัก
try:
    order_ids = odoo._execute(
        "sale.order", "search",
        [["state", "in", ["sale", "done"]]],
        limit=3
    )
    print("Order IDs:", order_ids)
except Exception as e:
    print("sale.order error:", str(e)[:200])