@echo off
cd /d "%~dp0"
python pixel_server.py
if errorlevel 1 (
  echo.
  echo Nao foi possivel iniciar. Confira se Python, OpenCV, NumPy, Pillow,
  echo PyAutoGUI e PyGetWindow estao instalados.
  pause
)
