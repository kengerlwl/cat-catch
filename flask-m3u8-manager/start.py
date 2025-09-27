#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask M3U8 下载管理器启动脚本
"""

import os
import sys
import webbrowser
import time
import threading

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

def open_browser():
    """延迟打开浏览器"""
    time.sleep(1.5)
    webbrowser.open('http://localhost:5001')

if __name__ == '__main__':
    print("=" * 50)
    print("🎬 Flask M3U8 下载管理器")
    print("=" * 50)
    print(f"📁 下载目录: {os.path.join(os.path.dirname(__file__), 'downloads')}")
    print("🌐 访问地址: http://localhost:5001")
    print("📖 使用说明:")
    print("  1. 在浏览器中打开 http://localhost:5001")
    print("  2. 添加M3U8链接到下载队列")
    print("  3. 管理下载任务（暂停、恢复、转换等）")
    print("  4. 在cat-catch扩展的m3u8下载页面点击'后台下载'按钮")
    print("=" * 50)

    # 在新线程中打开浏览器
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()

    try:
        app.run(debug=False, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n👋 感谢使用 Flask M3U8 下载管理器！")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        print("请检查端口5000是否被占用")
