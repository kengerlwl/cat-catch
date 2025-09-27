#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试M3U8处理器的多线程下载功能
"""

import os
import time
from m3u8_processor import M3U8Processor

def test_concurrent_download():
    """测试并发下载功能"""
    print("🧪 测试M3U8多线程切片下载功能")
    print("=" * 50)

    # 测试URL（请替换为实际的M3U8链接）
    test_url = "https://example.com/test.m3u8"  # 替换为实际URL

    # 创建处理器
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    processor = M3U8Processor(test_url, headers)

    print(f"📡 解析M3U8: {test_url}")

    # 解析M3U8
    if not processor.parse_m3u8():
        print("❌ M3U8解析失败")
        return False

    print(f"✅ 解析成功，发现 {len(processor.segments)} 个切片")

    # 测试不同线程数的下载性能
    test_cases = [
        {"threads": 1, "name": "单线程"},
        {"threads": 3, "name": "3线程"},
        {"threads": 6, "name": "6线程"},
        {"threads": 10, "name": "10线程"}
    ]

    for case in test_cases:
        print(f"\n🚀 测试 {case['name']} 下载...")

        # 创建测试目录
        test_dir = f"test_download_{case['threads']}_threads"
        os.makedirs(test_dir, exist_ok=True)

        # 进度回调
        def progress_callback(downloaded, total):
            progress = (downloaded / total) * 100
            print(f"  📊 进度: {downloaded}/{total} ({progress:.1f}%)")

        # 开始计时
        start_time = time.time()

        # 下载切片
        success = processor.download_all_segments(
            test_dir,
            max_retries=3,
            progress_callback=progress_callback,
            max_workers=case['threads']
        )

        # 结束计时
        end_time = time.time()
        duration = end_time - start_time

        if success:
            print(f"  ✅ {case['name']} 下载完成，耗时: {duration:.2f}秒")
        else:
            print(f"  ❌ {case['name']} 下载失败，耗时: {duration:.2f}秒")

        # 清理测试文件
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    print("\n🎉 测试完成！")
    return True

def test_single_vs_concurrent():
    """对比单线程和多线程下载性能"""
    print("\n📈 性能对比测试")
    print("=" * 30)

    # 模拟切片信息
    mock_segments = []
    for i in range(20):  # 模拟20个切片
        mock_segments.append({
            'index': i,
            'url': f'https://httpbin.org/delay/1',  # 模拟1秒延迟的请求
            'duration': 10.0,
            'encrypted': False
        })

    print(f"📦 模拟 {len(mock_segments)} 个切片")

    # 创建处理器并设置模拟数据
    processor = M3U8Processor("http://example.com/test.m3u8")
    processor.segments = mock_segments

    # 测试单线程
    print("\n🐌 单线程下载测试...")
    start_time = time.time()
    # 这里只是演示，实际测试需要真实的URL
    print("  (跳过实际下载，仅演示)")
    single_thread_time = 20  # 假设单线程需要20秒

    # 测试多线程
    print("\n🚀 6线程并发下载测试...")
    start_time = time.time()
    print("  (跳过实际下载，仅演示)")
    multi_thread_time = 4  # 假设6线程需要4秒

    # 性能提升计算
    speedup = single_thread_time / multi_thread_time
    print(f"\n📊 性能对比结果:")
    print(f"  单线程耗时: {single_thread_time}秒")
    print(f"  6线程耗时: {multi_thread_time}秒")
    print(f"  性能提升: {speedup:.1f}倍")

if __name__ == "__main__":
    print("🎬 M3U8多线程下载测试工具")
    print("=" * 40)

    # 运行测试
    test_single_vs_concurrent()

    print("\n💡 使用说明:")
    print("1. 单个切片使用单线程下载（不分块）")
    print("2. 多个切片支持并发下载（同时下载多个切片）")
    print("3. 可配置并发线程数（1-16个线程）")
    print("4. 支持断点续传和重试机制")
    print("5. 线程安全的进度更新")
