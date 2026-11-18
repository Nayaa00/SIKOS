"""Optional project-local npm from the official registry; no global installation."""
from pathlib import Path
from urllib.request import urlopen
from io import BytesIO
import base64, hashlib, json, tarfile
root=Path(__file__).resolve().parents[1]
target=root/'.tools'/'npm'
if (target/'bin/npm-cli.js').exists():
    print('npm lokal sudah tersedia.')
else:
    with urlopen('https://registry.npmjs.org/npm/latest',timeout=60) as response: metadata=json.load(response)
    url=metadata['dist']['tarball']
    if not url.startswith('https://registry.npmjs.org/npm/-/'):raise RuntimeError('Unexpected registry URL')
    with urlopen(url,timeout=120) as response:raw=response.read()
    expected=metadata['dist']['integrity'].removeprefix('sha512-')
    if base64.b64encode(hashlib.sha512(raw).digest()).decode()!=expected:raise RuntimeError('Integrity mismatch')
    archive_root=root/'.tools';archive_root.mkdir(exist_ok=True)
    with tarfile.open(fileobj=BytesIO(raw),mode='r:gz') as archive:
        archive.extractall(archive_root,filter='data')
    (archive_root/'package').rename(target)
    print('npm lokal siap:',metadata['version'])
