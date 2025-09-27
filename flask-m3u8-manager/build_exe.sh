#!/bin/bash

echo "========================================"
echo "Flask M3U8 Manager - Executable Builder"
echo "========================================"

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "Error: Python3 is not installed or not in PATH"
    exit 1
fi

# 检查是否在正确的目录
if [ ! -f "app.py" ]; then
    echo "Error: Please run this script from the flask-m3u8-manager directory"
    exit 1
fi

echo "Installing dependencies..."
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt
pip3 install pyinstaller

echo ""
echo "Building executable..."
if [ -f "flask_m3u8_manager.spec" ]; then
    echo "Using existing spec file..."
    pyinstaller flask_m3u8_manager.spec --clean --noconfirm
else
    echo "Creating new spec file..."
    pyinstaller start.py \
        --name "Flask-M3U8-Manager" \
        --onefile \
        --console \
        --clean \
        --noconfirm \
        --add-data "templates:templates" \
        --add-data "static:static" \
        --add-data "config.py:." \
        --add-data "models.py:." \
        --add-data "m3u8_processor.py:." \
        --add-data "app.py:." \
        --hidden-import flask \
        --hidden-import flask_cors \
        --hidden-import flask_sqlalchemy \
        --hidden-import requests \
        --hidden-import m3u8 \
        --hidden-import pycryptodomex \
        --hidden-import urllib3 \
        --hidden-import colorlog \
        --hidden-import sqlite3 \
        --hidden-import werkzeug \
        --hidden-import jinja2 \
        --hidden-import markupsafe \
        --hidden-import itsdangerous \
        --hidden-import sqlalchemy
fi

if [ -f "dist/Flask-M3U8-Manager" ]; then
    echo ""
    echo "========================================"
    echo "Build completed successfully!"
    echo "========================================"
    echo "Executable location: dist/Flask-M3U8-Manager"
    echo "File size: $(ls -lh dist/Flask-M3U8-Manager | awk '{print $5}')"
    echo ""
    echo "You can now run the executable to start the Flask M3U8 Manager."
    echo "The application will be available at http://localhost:5001"
    echo ""

    # 询问是否要运行
    read -p "Do you want to run the executable now? (y/n): " run_now
    if [[ $run_now == "y" || $run_now == "Y" ]]; then
        echo "Starting Flask M3U8 Manager..."
        chmod +x dist/Flask-M3U8-Manager
        ./dist/Flask-M3U8-Manager
    fi
else
    echo ""
    echo "========================================"
    echo "Build failed!"
    echo "========================================"
    echo "Please check the error messages above."
    exit 1
fi
