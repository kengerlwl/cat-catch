#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask M3U8 下载管理器 API 测试脚本
"""

import requests
import json
import time

BASE_URL = 'http://localhost:5001'

def test_api():
    """测试API功能"""
    print("🧪 开始测试 Flask M3U8 下载管理器 API")
    print("=" * 50)

    # 测试服务器是否运行
    try:
        response = requests.get(f"{BASE_URL}/api/tasks", timeout=5)
        print("✅ 服务器连接成功")
    except requests.exceptions.RequestException as e:
        print(f"❌ 服务器连接失败: {e}")
        print("请确保Flask应用正在运行 (python start.py)")
        return

    # 测试获取任务列表
    print("\n📋 测试获取任务列表...")
    response = requests.get(f"{BASE_URL}/api/tasks")
    if response.status_code == 200:
        tasks = response.json()['tasks']
        print(f"✅ 获取任务列表成功，当前有 {len(tasks)} 个任务")
    else:
        print(f"❌ 获取任务列表失败: {response.status_code}")

    # 测试创建任务（使用示例M3U8链接）
    print("\n📥 测试创建下载任务...")
    test_task = {
        "url": "https://example.com/test.m3u8",
        "title": "API测试任务",
        "custom_dir": "test"
    }

    response = requests.post(
        f"{BASE_URL}/api/tasks",
        headers={'Content-Type': 'application/json'},
        data=json.dumps(test_task)
    )

    if response.status_code == 200:
        task_data = response.json()
        task_id = task_data.get('task_id')
        print(f"✅ 创建任务成功，任务ID: {task_id}")

        # 测试获取单个任务
        print(f"\n🔍 测试获取任务详情...")
        response = requests.get(f"{BASE_URL}/api/tasks/{task_id}")
        if response.status_code == 200:
            task_info = response.json()
            print(f"✅ 获取任务详情成功: {task_info['title']}")
        else:
            print(f"❌ 获取任务详情失败: {response.status_code}")

        # 等待一下让任务开始
        time.sleep(2)

        # 测试暂停任务
        print(f"\n⏸️  测试暂停任务...")
        response = requests.post(f"{BASE_URL}/api/tasks/{task_id}/pause")
        if response.status_code == 200:
            print("✅ 暂停任务成功")
        else:
            print(f"❌ 暂停任务失败: {response.status_code}")

        # 测试恢复任务
        print(f"\n▶️  测试恢复任务...")
        response = requests.post(f"{BASE_URL}/api/tasks/{task_id}/resume")
        if response.status_code == 200:
            print("✅ 恢复任务成功")
        else:
            print(f"❌ 恢复任务失败: {response.status_code}")

        # 测试更新任务URL
        print(f"\n✏️  测试更新任务...")
        update_data = {
            "url": "https://example.com/updated.m3u8",
            "title": "更新后的测试任务"
        }
        response = requests.post(
            f"{BASE_URL}/api/tasks/{task_id}/update_url",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(update_data)
        )
        if response.status_code == 200:
            print("✅ 更新任务成功")
        else:
            print(f"❌ 更新任务失败: {response.status_code}")

        # 测试删除任务
        print(f"\n🗑️  测试删除任务...")
        response = requests.delete(f"{BASE_URL}/api/tasks/{task_id}/delete")
        if response.status_code == 200:
            print("✅ 删除任务成功")
        else:
            print(f"❌ 删除任务失败: {response.status_code}")

    else:
        print(f"❌ 创建任务失败: {response.status_code}")
        if response.headers.get('content-type', '').startswith('application/json'):
            error_data = response.json()
            print(f"错误信息: {error_data.get('error', '未知错误')}")

    print("\n" + "=" * 50)
    print("🎉 API测试完成")

if __name__ == '__main__':
    test_api()
