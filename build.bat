@echo off
REM Builds dist\VLAK-Toolkit.exe  (needs Python 3.10+ on the BUILD machine only)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto :err
python -m PyInstaller --noconfirm --clean VLAK-Toolkit.spec || goto :err
echo.
echo Done: dist\VLAK-Toolkit.exe
exit /b 0
:err
echo Build failed.
exit /b 1
