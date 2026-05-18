import xmlrpc.client

env = {}
for line in open('.env', encoding='utf-8'):
    line = line.strip()
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip()

common = xmlrpc.client.ServerProxy(f"{env['ODOO_URL']}/xmlrpc/2/common")
models = xmlrpc.client.ServerProxy(f"{env['ODOO_URL']}/xmlrpc/2/object")
uid = common.authenticate(env['ODOO_DB'], env['ODOO_USERNAME'], env['ODOO_PASSWORD'], {})

data = models.execute_kw(
    env['ODOO_DB'], uid, env['ODOO_PASSWORD'],
    'product.template', 'read', [[44034]],
    {'fields': ['image_512']}
)

img_b64 = data[0]['image_512']
print('Image B64 length:', len(img_b64) if img_b64 else 0)