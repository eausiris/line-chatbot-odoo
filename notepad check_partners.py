from app.services.odoo_service import odoo

ids = odoo._execute('res.partner', 'search', [[['ref', 'like', 'LINE:']]])
partners = odoo._execute('res.partner', 'read', ids, fields=['id', 'name', 'ref'])
for p in partners[:5]:
    print(p)