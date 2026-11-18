@echo off
setlocal
pushd "%~dp0.."
if not exist ".tools\cloudflared.exe" (
  echo cloudflared belum tersedia di .tools. Baca docs\DOCKER.md.
  popd
  exit /b 1
)
docker compose --env-file .env.docker up -d web
if errorlevel 1 (
  popd
  exit /b 1
)
echo Biarkan terminal ini terbuka. URL publik sementara ditampilkan di bawah.
".tools\cloudflared.exe" tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:8002
set "SIKOS_EXIT=%ERRORLEVEL%"
popd
exit /b %SIKOS_EXIT%
