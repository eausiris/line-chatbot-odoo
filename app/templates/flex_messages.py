NO_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/6/65/No-Image-Placeholder.svg/330px-No-Image-Placeholder.svg.png"


def product_card(product: dict, odoo_url: str = "") -> dict:
    uom = product.get("uom", "ชิ้น")
    image_url = product.get("image_url") or NO_IMAGE_URL

    # Product URL ใน Odoo
    product_url = f"{odoo_url}/odoo/inventory/products/{product['template_id']}" if odoo_url else ""

    variant_rows = []
    for v in product.get("variants", [])[:5]:
        color = "#27AE60" if v["stock"] > 0 else "#E74C3C"
        variant_rows.append({
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text", "text": v["uom"], "size": "xs", "color": "#34495E", "flex": 2},
                {"type": "text", "text": f"\u0e3f{v['price']:,.0f}", "size": "xs",
                 "color": "#E74C3C", "align": "center", "flex": 2},
                {"type": "text", "text": f"{v['stock']} {v['uom']}", "size": "xs",
                 "color": color, "align": "end", "flex": 2},
            ],
        })

    stock_rows = []
    for wh in product.get("stock_by_warehouse", []):
        color = "#27AE60" if wh["qty"] > 0 else "#E74C3C"
        stock_rows.append({
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text", "text": f"• {wh['warehouse']}", "size": "xs",
                 "color": "#7F8C8D", "flex": 3},
                {"type": "text", "text": f"{wh['qty']} {uom}", "size": "xs",
                 "color": color, "align": "end", "flex": 1},
            ],
        })

    body_contents = [
        {"type": "text", "text": product["name"],
         "weight": "bold", "size": "lg", "wrap": True, "color": "#1A1A2E"},
        {"type": "box", "layout": "baseline", "contents": [
            {"type": "text", "text": "ราคา", "color": "#95A5A6", "size": "sm", "flex": 0},
            {"type": "text", "text": f"\u0e3f{product['price']:,.0f}/{uom} (VAT)",
             "weight": "bold", "size": "md", "color": "#E74C3C", "flex": 1, "align": "end"},
        ]},
        {"type": "separator"},
    ]

    if variant_rows:
        body_contents.append({
            "type": "text", "text": "\U0001f4e6 Package / หน่วย",
            "size": "xs", "color": "#2C3E50", "weight": "bold"
        })
        body_contents.append({
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text", "text": "หน่วย", "size": "xs", "color": "#BDC3C7", "flex": 2},
                {"type": "text", "text": "ราคา", "size": "xs", "color": "#BDC3C7", "align": "center", "flex": 2},
                {"type": "text", "text": "คงเหลือ", "size": "xs", "color": "#BDC3C7", "align": "end", "flex": 2},
            ],
        })
        body_contents.extend(variant_rows)
        body_contents.append({"type": "separator"})

    if stock_rows:
        body_contents.append({
            "type": "text", "text": "\U0001f3ea สต็อกแยกสาขา",
            "size": "xs", "color": "#2C3E50", "weight": "bold"
        })
        body_contents.extend(stock_rows)

    # Footer buttons (ชิดขอบล่างเท่ากันทุกการ์ด)
    footer_buttons = [
        {
            "type": "button", "style": "primary", "color": "#1A1A2E", "height": "sm",
            "action": {
                "type": "message", "label": "\U0001f6d2 เพิ่มลงตะกร้า",
                "text": f"เพิ่มสินค้า {product['name']} ลงตะกร้า",
            },
        },
    ]

    # ปุ่มรายละเอียด (ถ้ามี URL)
    if product_url:
        footer_buttons.append({
            "type": "button", "style": "secondary", "height": "sm",
            "action": {
                "type": "uri", "label": "\U0001f4cb รายละเอียด",
                "uri": product_url,
            },
        })

    bubble = {
        "type": "bubble", "size": "mega",
        "hero": {
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "4:3",
            "aspectMode": "cover",
            "action": {"type": "uri", "label": "view", "uri": image_url},
        },
        "body": {
            "type": "box", "layout": "vertical",
            "spacing": "sm", "paddingAll": "16px",
            "contents": body_contents,
        },
        "footer": {
            "type": "box", "layout": "vertical",
            "spacing": "sm", "paddingAll": "12px",
            "contents": footer_buttons,
        },
    }

    return bubble


def view_all_card(total_count: int, odoo_url: str = "") -> dict:
    """การ์ดสุดท้าย: ดูสินค้าทั้งหมด"""
    shop_url = f"{odoo_url}/shop" if odoo_url else "https://odoo.com"
    return {
        "type": "bubble", "size": "mega",
        "body": {
            "type": "box", "layout": "vertical",
            "justifyContent": "center",
            "contents": [
                {"type": "text", "text": "\U0001f6d2",
                 "size": "5xl", "align": "center"},
                {"type": "text",
                 "text": f"มีสินค้าทั้งหมด\n{total_count} รายการ",
                 "weight": "bold", "size": "xl", "align": "center",
                 "wrap": True, "color": "#1A1A2E"},
                {"type": "text", "text": "กดเพื่อดูสินค้าทั้งหมด",
                 "size": "sm", "color": "#7F8C8D", "align": "center"},
            ],
        },
        "footer": {
            "type": "box", "layout": "vertical",
            "contents": [{
                "type": "button", "style": "primary", "color": "#E74C3C",
                "action": {
                    "type": "uri",
                    "label": "\U0001f4e6 ดูสินค้าทั้งหมด",
                    "uri": shop_url,
                },
            }],
        },
    }


def product_carousel(products: list, total_count: int = 0, odoo_url: str = "") -> dict:
    """สร้าง Carousel สินค้า ถ้ามีมากกว่า 5 ชิ้น การ์ดสุดท้ายเป็น 'ดูทั้งหมด'"""
    MAX_SHOW = 9  # LINE รองรับสูงสุด 10 bubbles

    bubbles = [product_card(p, odoo_url) for p in products[:MAX_SHOW]]

    # ถ้ามีสินค้ามากกว่าที่แสดง ใส่การ์ด "ดูทั้งหมด"
    if total_count > len(products) or len(products) > MAX_SHOW:
        bubbles.append(view_all_card(total_count or len(products), odoo_url))

    return {"type": "carousel", "contents": bubbles}


def order_summary_bubble(cart_items: list, quotation: dict = None) -> dict:
    line_contents = []
    total = 0
    for item in cart_items:
        item_total = item["price_unit"] * item["qty"]
        total += item_total
        line_contents.append({
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text",
                 "text": f"{item['name']} x{item['qty']} {item.get('uom', 'ชิ้น')}",
                 "size": "sm", "color": "#2C3E50", "flex": 3, "wrap": True},
                {"type": "text", "text": f"\u0e3f{item_total:,.0f}",
                 "size": "sm", "align": "end", "flex": 1},
            ],
        })
        if item.get("stock_warning"):
            line_contents.append({
                "type": "text",
                "text": f"\u26a0\ufe0f สต็อกมีแค่ {item.get('available_stock', 0)}",
                "size": "xs", "color": "#E74C3C"
            })

    if quotation:
        warn_rows = [
            {"type": "text", "text": f"\u26a0\ufe0f {w}",
             "size": "xs", "color": "#E67E22", "wrap": True}
            for w in quotation.get("warnings", [])
        ]
        footer_contents = [
            {"type": "text", "text": f"\u2705 เลขที่: {quotation['order_name']}",
             "weight": "bold", "color": "#27AE60", "align": "center"},
            *warn_rows,
            {"type": "button", "style": "primary", "color": "#27AE60",
             "action": {"type": "uri", "label": "\U0001f4c4 ดูใบเสนอราคา",
                        "uri": quotation["portal_url"]}},
        ]
    else:
        footer_contents = [
            {"type": "button", "style": "primary", "color": "#E74C3C",
             "action": {"type": "message", "label": "\u2705 ยืนยันสั่งซื้อ",
                        "text": "ยืนยันสั่งซื้อ"}},
            {"type": "button", "style": "secondary",
             "action": {"type": "message", "label": "\U0001f5d1\ufe0f ล้างตะกร้า",
                        "text": "ล้างตะกร้า"}},
        ]

    return {
        "type": "bubble",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1A1A2E",
            "contents": [{"type": "text", "text": "\U0001f6d2 รายการสินค้า (รวม VAT แล้ว)",
                          "color": "#FFFFFF", "weight": "bold", "size": "md"}],
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "md",
            "contents": [
                *line_contents,
                {"type": "separator"},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "ยอดรวม (รวม VAT)",
                     "weight": "bold", "size": "lg", "color": "#2C3E50"},
                    {"type": "text", "text": f"\u0e3f{total:,.2f}",
                     "weight": "bold", "size": "lg", "color": "#E74C3C", "align": "end"},
                ]},
            ],
        },
        "footer": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": footer_contents,
        },
    }
