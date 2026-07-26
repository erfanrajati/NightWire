@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo NightWire requires uv. Install uv, then run this file again.
  echo https://docs.astral.sh/uv/
  pause
  exit /b 1
)

if not defined PORT set "PORT=8080"
if defined NIGHTWIRE_PORT set "PORT=%NIGHTWIRE_PORT%"
uv run --locked python app.py
if errorlevel 1 pause
