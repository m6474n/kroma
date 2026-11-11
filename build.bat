@echo off
setlocal
echo ====================================================
echo   Building Kroma Desktop Executable (.exe)
echo ====================================================

REM Prefer virtualenv Python if present
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" "%~dp0build_exe.py" %*

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ====================================================
    echo   BUILD SUCCESSFUL!
    echo   Executable located at: dist\Kroma\Kroma.exe
    echo ====================================================
) else (
    echo.
    echo [ERROR] Build failed with exit code %ERRORLEVEL%.
)

pause

