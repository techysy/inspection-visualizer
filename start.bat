@echo off
cd /d "%~dp0"

echo.
echo ========================================
echo   Film Price Tracker
echo ========================================
echo.

echo [1/3] Virtual environment...
if not exist "venv" (
    python -m venv venv
    echo   Created
) else (
    echo   Exists
)

call venv\Scripts\activate.bat

echo [2/3] Installing dependencies...
pip install -r requirements.txt --quiet --disable-pip-version-check
echo   Done

echo [3/3] Checking OCR...
python -c "from rapidocr_onnxruntime import RapidOCR"
if errorlevel 1 (
    echo   Not installed
) else (
    echo   Ready
)

echo.
echo ========================================
echo   http://127.0.0.1:5001
echo   Press Ctrl+C to stop
echo ========================================
echo.
python app.py

echo.
echo Stopped
pause
