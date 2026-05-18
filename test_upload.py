import xmlrpc.client
import urllib.request
import urllib.parse
import json

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

# อัปโหลดไป freeimage.host
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

with urllib.request.urlopen(req, timeout=30) as resp:
    result = json.loads(resp.read())

print('Image URL:', result['image']['url'])