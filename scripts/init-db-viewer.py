"""Create a read-only database browser account without printing credentials."""
from pathlib import Path
import os,secrets,subprocess

root=Path(__file__).resolve().parents[1]
private=root/'.env.docker'
assert private.exists(), 'Prepare the private .env.docker first'
content=private.read_text(encoding='utf-8')
entries=dict(line.split('=',1) for line in content.splitlines() if line and not line.startswith('#') and '=' in line)
password=entries.get('SIKOS_DB_VIEWER_PASSWORD')
if not password:
    password=secrets.token_hex(32)
    with private.open('a',encoding='utf-8') as stream:
        stream.write('\nSIKOS_DB_VIEWER_PASSWORD='+password+'\n')
assert len(password)>=32 and all(c in '0123456789abcdef' for c in password),'Viewer secret must be at least 32 hex characters'
sql=("CREATE USER IF NOT EXISTS 'sikos_browser'@'%' IDENTIFIED BY '"+password+"';"
     "GRANT SELECT,SHOW VIEW ON sikos.* TO 'sikos_browser'@'%';")
command=['docker','compose','--env-file','.env.docker','exec','-T','db','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot']
result=subprocess.run(command,cwd=root,input=sql.encode(),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
if result.returncode:
    raise SystemExit('Could not provision database viewer. No credentials were printed.')
print('Read-only SIKOS database browser account ready. Private password was not displayed.')
