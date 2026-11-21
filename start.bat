@echo off
setlocal

REM Luon chay tu thu muc chua start.bat (thu muc goc cua du an).
cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"

echo.
echo ========================================
echo          STARTING TECHZONE AI
echo ========================================
echo Project: %PROJECT_DIR%
echo Backend: %PROJECT_DIR%\backend\main.py
echo Chatbot: %PROJECT_DIR%\backend\chatbot.py
echo Product: %PROJECT_DIR%\backend\product_service.py
echo.

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Khong tim thay Python trong .venv:
    echo         %PYTHON_EXE%
    echo Hay dat start.bat trong thu muc goc TECHZONE-AI.
    pause
    exit /b 1
)

if not exist "%PROJECT_DIR%\backend\main.py" (
    echo [ERROR] Khong tim thay backend\main.py.
    echo Hay dat start.bat trong thu muc goc TECHZONE-AI.
    pause
    exit /b 1
)

if not exist "%PROJECT_DIR%\backend\chatbot.py" (
    echo [ERROR] Khong tim thay backend\chatbot.py.
    pause
    exit /b 1
)

if not exist "%PROJECT_DIR%\backend\product_service.py" (
    echo [ERROR] Khong tim thay backend\product_service.py.
    pause
    exit /b 1
)

echo Starting backend on http://127.0.0.1:8001 ...
start "TechZone Backend" /D "%PROJECT_DIR%" "%ComSpec%" /k ""%PYTHON_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8001"

echo Starting frontend on http://127.0.0.1:5500 ...
start "TechZone Frontend" /D "%PROJECT_DIR%" "%ComSpec%" /k ""%PYTHON_EXE%" -m http.server 5500 --directory "%PROJECT_DIR%""

timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:5500/frontend/html/chat.html"

echo.
echo Da gui lenh khoi dong. Neu backend bao loi port 8001 dang duoc su dung,
echo hay dong cua so backend cu truoc khi chay lai.
echo.

endlocal
exit /b 0
