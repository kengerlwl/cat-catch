@echo off
echo ========================================
echo Flask M3U8 Manager - EXE Builder
echo ========================================

:: 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    pause
    exit /b 1
)

:: 检查是否在正确的目录
if not exist "app.py" (
    echo Error: Please run this script from the flask-m3u8-manager directory
    pause
    exit /b 1
)

echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo.
echo Building executable...

:: 备份并移除数据库文件（避免打包进exe）
if exist "downloads.db" (
    echo Backing up database file...
    copy "downloads.db" "downloads.db.backup" >nul
    del "downloads.db"
)

if exist "flask_m3u8_manager.spec" (
    echo Using existing spec file...
    pyinstaller flask_m3u8_manager.spec --clean --noconfirm
) else (
    echo Creating new spec file...
    pyinstaller start.py --name "Flask-M3U8-Manager" --onefile --console --clean --noconfirm ^
        --add-data "templates;templates" ^
        --add-data "static;static" ^
        --add-data "config.py;." ^
        --add-data "models.py;." ^
        --add-data "m3u8_processor.py;." ^
        --add-data "llm_service.py;." ^
        --add-data "app.py;." ^
        --hidden-import flask ^
        --hidden-import flask_cors ^
        --hidden-import flask_sqlalchemy ^
        --hidden-import requests ^
        --hidden-import m3u8 ^
        --hidden-import pycryptodomex ^
        --hidden-import urllib3 ^
        --hidden-import colorlog ^
        --hidden-import sqlite3 ^
        --hidden-import werkzeug ^
        --hidden-import jinja2 ^
        --hidden-import markupsafe ^
        --hidden-import itsdangerous ^
        --hidden-import sqlalchemy
)

:: 恢复数据库文件
if exist "downloads.db.backup" (
    echo Restoring database file...
    move "downloads.db.backup" "downloads.db" >nul
)

if exist "dist\Flask-M3U8-Manager.exe" (
    echo.
    echo ========================================
    echo Build completed successfully!
    echo ========================================
    echo Executable location: dist\Flask-M3U8-Manager.exe
    echo File size:
    dir "dist\Flask-M3U8-Manager.exe" | findstr "Flask-M3U8-Manager.exe"
    echo.
    echo IMPORTANT NOTES:
    echo - First run will automatically create database and initialize all tables
    echo - Default configurations and LLM settings will be created automatically
    echo - All settings can be modified through the web interface
    echo - The application will be available at http://localhost:5001
    echo.

    :: 询问是否要运行
    set /p run_now="Do you want to run the executable now? (y/n): "
    if /i "%run_now%"=="y" (
        echo Starting Flask M3U8 Manager...
        start "" "dist\Flask-M3U8-Manager.exe"
    )
) else (
    echo.
    echo ========================================
    echo Build failed!
    echo ========================================
    echo Please check the error messages above.
)

echo.
pause
