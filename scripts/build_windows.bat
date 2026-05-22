@echo off
setlocal

cd /d "%~dp0\.."

if not exist "src\tianwen_clearc\treemap.py" (
    echo [ERROR] Missing src\tianwen_clearc\treemap.py
    echo Please use the latest source package and run this script from the project root.
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    py -3.10 -m venv .venv
    if errorlevel 1 exit /b 1
    set "PYTHON=.venv\Scripts\python.exe"
)

"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

"%PYTHON%" -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1

"%PYTHON%" -m pip install -e .
if errorlevel 1 exit /b 1

"%PYTHON%" -c "import tianwen_clearc.treemap; print('import ok:', tianwen_clearc.treemap.__file__)"
if errorlevel 1 (
    echo [ERROR] Python cannot import tianwen_clearc.treemap.
    echo Check that you are using this project folder, not an older installed copy.
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

"%PYTHON%" -m PyInstaller --clean --noconfirm packaging\tianwen_clearc_windows.spec
if errorlevel 1 exit /b 1

echo.
echo Build finished:
echo dist\TianwenClearC\TianwenClearC.exe
