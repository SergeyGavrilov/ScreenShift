@echo off
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Building ScreenShift.exe...
pyinstaller --onefile --windowed --name ScreenShift screenshift.py

echo.
echo Done! ScreenShift.exe is in the dist\ folder.
pause
