#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化测试脚本
用于验证新环境下的数据库创建和API响应
"""

import os
import sys
import requests
import time
import json

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_api_endpoints():
    """测试各个API端点在数据库初始化期间的响应"""
    base_url = "http://localhost:5001"

    endpoints = [
        "/api/queue/status",
        "/api/tasks",
        "/api/statistics",
        "/api/settings/all"
    ]

    print("=" * 50)
    print("🧪 测试API端点响应")
    print("=" * 50)

    for endpoint in endpoints:
        try:
            print(f"\n📡 测试端点: {endpoint}")
            response = requests.get(f"{base_url}{endpoint}", timeout=10)

            if response.status_code == 200:
                data = response.json()

                # 检查是否包含database_initializing字段
                if 'database_initializing' in data:
                    status = "初始化中" if data['database_initializing'] else "就绪"
                    print(f"   ✅ 状态码: {response.status_code}")
                    print(f"   📊 数据库状态: {status}")

                    if data.get('database_initializing'):
                        print(f"   ⏳ 系统正在初始化，这是正常的")
                    else:
                        print(f"   🎉 系统已就绪")
                else:
                    print(f"   ✅ 状态码: {response.status_code}")
                    print(f"   📄 响应正常（无初始化状态字段）")

            else:
                print(f"   ❌ 状态码: {response.status_code}")
                print(f"   📄 响应: {response.text[:200]}...")

        except requests.exceptions.RequestException as e:
            print(f"   ❌ 请求失败: {e}")
        except Exception as e:
            print(f"   ❌ 解析失败: {e}")

def check_database_files():
    """检查数据库文件是否存在"""
    print("\n" + "=" * 50)
    print("📁 检查数据库文件")
    print("=" * 50)

    db_path = os.path.join(os.path.dirname(__file__), 'downloads.db')
    config_path = os.path.join(os.path.dirname(__file__), 'user_config.json')
    downloads_dir = os.path.join(os.path.dirname(__file__), 'downloads')

    files_to_check = [
        ("数据库文件", db_path),
        ("配置文件", config_path),
        ("下载目录", downloads_dir)
    ]

    for name, path in files_to_check:
        if os.path.exists(path):
            if os.path.isfile(path):
                size = os.path.getsize(path)
                print(f"✅ {name}: {path} (大小: {size} 字节)")
            else:
                print(f"✅ {name}: {path} (目录)")
        else:
            print(f"❌ {name}: {path} (不存在)")

def wait_for_server():
    """等待服务器启动"""
    print("⏳ 等待服务器启动...")

    for i in range(30):  # 最多等待30秒
        try:
            response = requests.get("http://localhost:5001/", timeout=5)
            if response.status_code == 200:
                print("✅ 服务器已启动")
                return True
        except:
            pass

        time.sleep(1)
        print(f"   等待中... ({i+1}/30)")

    print("❌ 服务器启动超时")
    return False

def main():
    """主测试函数"""
    print("🎬 Flask M3U8 Manager - 数据库初始化测试")

    # 检查数据库文件
    check_database_files()

    # 等待服务器启动
    if not wait_for_server():
        return

    # 测试API端点
    test_api_endpoints()

    # 等待一段时间后再次测试（确保初始化完成）
    print("\n⏳ 等待5秒后再次测试...")
    time.sleep(5)

    print("\n" + "=" * 50)
    print("🔄 再次测试API端点（应该已初始化完成）")
    print("=" * 50)
    test_api_endpoints()

    # 最终检查数据库文件
    check_database_files()

    print("\n" + "=" * 50)
    print("✅ 测试完成！")
    print("=" * 50)

if __name__ == '__main__':
    main()
