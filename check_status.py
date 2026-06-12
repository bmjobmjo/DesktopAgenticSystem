import urllib.request, json
req1 = urllib.request.Request('http://127.0.0.1:8787/auth/login', data=b'{"login":"admin", "password":"admin123"}', headers={'Content-Type': 'application/json'})
token = json.loads(urllib.request.urlopen(req1).read().decode())['access_token']
req2 = urllib.request.Request('http://127.0.0.1:8787/uiport/integrations/whatsapp/headless/status', headers={'Authorization': 'Bearer ' + token})
res = json.loads(urllib.request.urlopen(req2).read().decode())
print(json.dumps(res, indent=2))
