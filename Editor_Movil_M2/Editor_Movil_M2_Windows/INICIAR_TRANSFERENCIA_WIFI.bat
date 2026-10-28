@echo off
chcp 65001 >nul
cd /d "%~dp0"
python puente_wifi.py
if errorlevel 1 (echo. & echo No se pudo iniciar. Comprueba que Python 3 esta instalado.)
pause
