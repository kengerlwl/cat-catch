@echo off
chcp 65001 >nul
title Flask M3U8 下载管理器

echo ========================================
echo 🎬 Flask M3U8 下载管理器
echo ========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到Python，请先安装Python 3.7+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 检查pip是否可用
pip --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: pip不可用，请检查Python安装
    pause
    exit /b 1
)

echo ✅ Python环境检查通过
echo.

REM 检查是否存在虚拟环境
if not exist "venv" (
    echo 📦 创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo ❌ 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo ✅ 虚拟环境创建成功
)

REM 激活虚拟环境
echo 🔄 激活虚拟环境...
call venv\Scripts\activate.bat

REM 安装依赖
echo 📥 安装依赖包...
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)

echo ✅ 依赖安装完成
echo.

REM 启动Flask应用
echo 🚀 启动Flask M3U8 下载管理器...
echo.
python start.py

pause
