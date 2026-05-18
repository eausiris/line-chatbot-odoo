import xmlrpc.client
import logging
import urllib.request
import urllib.parse
import json
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

IMAGE_CACHE = {}  # Cache URL รูปเพื่อไม่ต้องอัปโหลดซ้ำ


def upload_image_to_host(img_b64: str, product_id: int) -> Optional[str]:
    """อัปโหลด Base64 image ไปที่ freeimage.host แล้วคืน URL"""
    if product_id in IMAGE_CACHE:
        return IMAGE_CACHE[product_id]
    try:
        post_data = urllib.parse.urlencode({
            'key': '6d207e02198a847aa98d0a2a901485a5',
            'action': 'upload',
            'source': img_b64,
            'format': 'json'
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://freeimage.host/api/1/upload',
            data=post_data,
            method='POST'
        )
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        url = result['image']['url']
        IMAGE_CACHE[product_id] = url
        logger.info(f"Image uploaded: {url}")
        return url
    except Exception as e:
        logger.error(f"Image upload error: {e}")
        return None


class OdooService:
    def __init__(self):
        self.url = settings.odoo_url
        self.db = settings.odoo_db
        self.username = settings.odoo_username
        self.password = settings.odoo_password
        self._uid: Optional[int] = None
        self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    @property
    def uid(self) -> int:
        if not self._uid:
            self._uid = self._common.authenticate(
                self.db, self.username, self.password, {}
            )
            if not self._uid:
                raise ConnectionError("Odoo login failed!")
            logger.info(f"Odoo login OK uid={self._uid}")
        return self._uid

    def _execute(self, model, method, *args, **kwargs):
        try:
            return self._models.execute_kw(
                self.db, self.uid, self.password,
                model, method, list(args), kwargs
            )
        except Exception as e:
            logger.error(f"Odoo error [{model}.{method}]: {e}")
            raise

    def get_stock_by_warehouse(self, product_id: int) -> list:
        try:
            warehouse_ids = self._execute(
                "stock.warehouse", "search", [["active", "=", True]]
            )
            warehouses = self._execute(
                "stock.warehouse", "read", warehouse_ids,
                fields=["id", "name", "lot_stock_id"]
            )
            result = []
            for wh in warehouses:
                location_id = wh["lot_stock_id"][0] if wh.get("lot_stock_id") else False
                if not location_id:
                    continue
                quant_ids = self._execute(
                    "stock.quant", "search",
                    [["product_id", "=", product_id], ["location_id", "=", location_id]]
                )
                qty = 0
                if quant_ids:
                    quants = self._execute(
                        "stock.quant", "read", quant_ids,
                        fields=["quantity", "reserved_quantity"]
                    )
                    qty = sum(q["quantity"] - q.get("reserved_quantity", 0) for q in quants)
                result.append({"warehouse": wh["name"], "qty": int(max(qty, 0))})
            return result
        except Exception as e:
            logger.error(f"Stock by warehouse error: {e}")
            return []

    def get_product_variants(self, template_id: int) -> list:
        try:
            variant_ids = self._execute(
                "product.product", "search",
                [["product_tmpl_id", "=", template_id], ["active", "=", True]]
            )
            if not variant_ids:
                return []
            variants = self._execute(
                "product.product", "read", variant_ids,
                fields=["id", "display_name", "lst_price", "uom_id", "qty_available"]
            )
            return [{
                "id": v["id"],
                "name": v["display_name"],
                "price": v["lst_price"],
                "uom": v["uom_id"][1] if v.get("uom_id") else "ชิ้น",
                "stock": int(v.get("qty_available", 0)),
            } for v in variants]
        except Exception as e:
            logger.error(f"Variants error: {e}")
            return []

    def search_products(self, keyword="", category="", limit=5):
        domain = [["sale_ok", "=", True], ["active", "=", True]]
        if keyword:
            domain.append(["name", "ilike", keyword])
        if category:
            domain.append(["categ_id.name", "ilike", category])

        ids = self._execute("product.template", "search", domain, limit=limit)
        if not ids:
            return []

        products = self._execute(
            "product.template", "read", ids,
            fields=["id", "name", "description_sale", "list_price",
                    "qty_available", "categ_id", "product_variant_ids",
                    "uom_id", "image_512"]
        )

        result = []
        for p in products:
            variant_id = p["product_variant_ids"][0] if p.get("product_variant_ids") else p["id"]
            variants = self.get_product_variants(p["id"])
            stock_by_warehouse = self.get_stock_by_warehouse(variant_id)

            # อัปโหลดรูปไปที่ freeimage.host
            image_url = None
            if p.get("image_512"):
                image_url = upload_image_to_host(p["image_512"], p["id"])

            result.append({
                "id": variant_id,
                "template_id": p["id"],
                "name": p["name"],
                "description": p.get("description_sale") or "",
                "price": p["list_price"],
                "stock": int(p.get("qty_available", 0)),
                "stock_by_warehouse": stock_by_warehouse,
                "category": p["categ_id"][1] if p.get("categ_id") else "-",
                "uom": p["uom_id"][1] if p.get("uom_id") else "ชิ้น",
                "variants": variants,
                "image_url": image_url,
            })
        return result

    def get_or_create_partner(self, line_user_id, display_name):
        ids = self._execute(
            "res.partner", "search",
            [["ref", "=", f"LINE:{line_user_id}"]]
        )
        if ids:
            return ids[0]
        return self._execute("res.partner", "create", {
            "name": display_name,
            "ref": f"LINE:{line_user_id}",
            "customer_rank": 1,
        })

    def check_stock_sufficient(self, product_id: int, qty_needed: int) -> dict:
        stock_list = self.get_stock_by_warehouse(product_id)
        total = sum(w["qty"] for w in stock_list)
        sufficient = [w for w in stock_list if w["qty"] >= qty_needed]
        return {
            "total_stock": total,
            "is_sufficient": total >= qty_needed,
            "sufficient_warehouses": sufficient,
            "stock_by_warehouse": stock_list,
        }

    def create_quotation(self, partner_id, cart_items, note=""):
        order_lines = []
        warnings = []
        for item in cart_items:
            stock_info = self.check_stock_sufficient(item["product_id"], item["qty"])
            if not stock_info["is_sufficient"]:
                warnings.append(
                    f"{item['name']}: ต้องการ {item['qty']} มีแค่ {stock_info['total_stock']}"
                )
            order_lines.append((0, 0, {
                "product_id": item["product_id"],
                "product_uom_qty": item["qty"],
                "price_unit": item["price_unit"],
            }))
        order_id = self._execute("sale.order", "create", {
            "partner_id": partner_id,
            "order_line": order_lines,
            "note": note or "Order from LINE OA Bot",
            "origin": "LINE OA Chatbot",
        })
        data = self._execute(
            "sale.order", "read", [order_id],
            fields=["name", "amount_total"]
        )[0]
        return {
            "order_id": order_id,
            "order_name": data["name"],
            "amount_total": data["amount_total"],
            "portal_url": f"{self.url}/my/orders/{order_id}",
            "warnings": warnings,
        }


odoo = OdooService()
