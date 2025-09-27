#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask M3U8 下载管理器
提供M3U8视频下载、任务管理、转换等功能
"""

import os
import json
import uuid
import threading
import subprocess
import time
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from flask_cors import CORS
import requests
import m3u8

# 导入配置和数据库模型
from config import config
from models import db, DownloadRecord, DownloadStatistics
from m3u8_processor import M3U8Processor

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 加载配置
app_config = config['default']()
app.config.from_object(app_config)

# 初始化数据库
db.init_app(app)

# 配置
DOWNLOAD_DIR = app_config.DOWNLOAD_DIR
SEGMENTS_DIR = app_config.SEGMENTS_DIR
CONVERTED_DIR = app_config.CONVERTED_DIR

# 确保目录存在
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(SEGMENTS_DIR, exist_ok=True)
os.makedirs(CONVERTED_DIR, exist_ok=True)

# 全局变量
task_lock = threading.Lock()
settings_lock = threading.Lock()

# 运行时设置（可通过API修改）
runtime_settings = app_config.USER_CONFIGURABLE.copy()

# 任务队列管理
task_queue = []
active_tasks = {}  # 存储活跃的任务线程和停止事件
max_concurrent_tasks = runtime_settings['max_concurrent_tasks']

# 任务线程管理
class TaskThread:
    """任务线程管理类"""
    def __init__(self, task_id):
        self.task_id = task_id
        self.thread = None
        self.stop_event = threading.Event()

    def start(self, target):
        """启动线程"""
        self.thread = threading.Thread(target=target, args=(self,))
        self.thread.start()

    def stop(self):
        """停止线程"""
        self.stop_event.set()

    def is_stopped(self):
        """检查是否已停止"""
        return self.stop_event.is_set()

def download_segment(url, filepath, headers=None, timeout=None):
    """下载单个切片"""
    try:
        timeout = timeout or runtime_settings['download_timeout']
        response = requests.get(url, headers=headers or {}, stream=True, timeout=timeout)
        response.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=app_config.CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"下载切片失败 {url}: {e}")
        return False

def process_task_queue():
    """处理任务队列"""
    global active_tasks, max_concurrent_tasks

    while len(active_tasks) < max_concurrent_tasks and task_queue:
        task_id = task_queue.pop(0)

        # 从数据库获取任务记录
        with app.app_context():
            record = DownloadRecord.get_by_task_id(task_id)
            if record and record.status == "queued":
                # 创建任务线程
                task_thread = TaskThread(task_id)
                active_tasks[task_id] = task_thread

                # 更新状态为pending
                record.status = "pending"
                db.session.commit()

                # 启动下载线程
                task_thread.start(download_m3u8_task)

def download_m3u8_task(task_thread):
    """下载M3U8任务的主函数 - 使用新的M3U8处理器"""
    task_id = task_thread.task_id

    with app.app_context():
        try:
            # 从数据库获取任务记录
            record = DownloadRecord.get_by_task_id(task_id)
            if not record:
                print(f"任务记录不存在: {task_id}")
                return

            # 更新状态为下载中
            record.mark_downloading()
            db.session.commit()

            # 创建任务目录
            task_dir = os.path.join(SEGMENTS_DIR, record.title)
            os.makedirs(task_dir, exist_ok=True)
            record.segments_path = task_dir
            db.session.commit()

            # 使用新的M3U8处理器
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            processor = M3U8Processor(record.url, headers)

            # 解析M3U8
            if not processor.parse_m3u8():
                record.mark_failed("M3U8解析失败")
                db.session.commit()
                return

            record.total_segments = len(processor.segments)
            db.session.commit()

            # 检查是否有加密切片
            encrypted_count = sum(1 for seg in processor.segments if seg['encrypted'])
            if encrypted_count > 0:
                print(f"检测到 {encrypted_count} 个加密切片，将自动解密")

            # 创建进度更新回调函数
            def update_progress(downloaded, total):
                record.update_progress(downloaded, total)
                db.session.commit()
                print(f"进度更新: {downloaded}/{total} ({record.progress}%)")

            # 下载所有切片（包含解密处理）- 使用配置的线程数进行并发下载
            success = processor.download_all_segments(
                task_dir,
                max_retries=runtime_settings['max_retry_count'],
                progress_callback=update_progress,
                max_workers=record.thread_count  # 使用任务配置的线程数
            )

            if success:
                # 创建本地M3U8文件
                processor.create_local_m3u8(task_dir)

                record.mark_completed()
                record.downloaded_segments = len(processor.segments)
                db.session.commit()
                print(f"任务 {task_id} 下载完成")
            else:
                record.mark_failed("部分切片下载失败")
                db.session.commit()
                print(f"任务 {task_id} 下载失败")

        except Exception as e:
            record = DownloadRecord.get_by_task_id(task_id)
            if record:
                record.mark_failed(str(e))
                db.session.commit()
            print(f"下载任务失败: {e}")
        finally:
            # 从活跃任务中移除
            if task_id in active_tasks:
                del active_tasks[task_id]
            # 处理队列中的下一个任务
            process_task_queue()

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    """获取所有下载任务"""
    try:
        # 从数据库获取所有任务
        tasks = DownloadRecord.query.order_by(DownloadRecord.created_at.desc()).all()
        tasks_data = [task.to_dict() for task in tasks]
        return jsonify({'tasks': tasks_data})
    except Exception as e:
        return jsonify({'error': f'获取任务列表失败: {str(e)}'}), 500

@app.route('/api/tasks', methods=['POST'])
def create_task():
    """创建新的下载任务"""
    global max_concurrent_tasks

    data = request.json
    url = data.get('url', '').strip()
    title = data.get('title', '').strip()
    custom_dir = data.get('custom_dir', '').strip()
    thread_count = data.get('thread_count', runtime_settings['thread_count'])

    if not url:
        return jsonify({'error': '请提供M3U8链接'}), 400

    # 验证线程数
    if thread_count < app_config.MIN_THREAD_COUNT or thread_count > app_config.MAX_THREAD_COUNT:
        thread_count = runtime_settings['thread_count']

    # 生成任务ID
    task_id = str(uuid.uuid4())

    # 如果没有提供标题，从URL生成
    if not title:
        parsed_url = urlparse(url)
        title = parsed_url.path.split('/')[-1] or f"m3u8_{int(time.time())}"
        if title.endswith('.m3u8'):
            title = title[:-5]

    try:
        # 创建数据库记录
        record = DownloadRecord(task_id, url, title, custom_dir, thread_count)

        # 检查是否可以立即开始下载
        if len(active_tasks) < max_concurrent_tasks:
            record.status = "pending"
            db.session.add(record)
            db.session.commit()

            # 创建任务线程
            task_thread = TaskThread(task_id)
            active_tasks[task_id] = task_thread

            # 启动下载线程
            task_thread.start(download_m3u8_task)
        else:
            # 添加到队列
            record.mark_queued()
            db.session.add(record)
            db.session.commit()
            task_queue.append(task_id)

        return jsonify({'task_id': task_id, 'message': '任务创建成功'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'创建任务失败: {str(e)}'}), 500

@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """获取单个任务信息"""
    try:
        record = DownloadRecord.get_by_task_id(task_id)
        if not record:
            return jsonify({'error': '任务不存在'}), 404
        return jsonify(record.to_dict())
    except Exception as e:
        return jsonify({'error': f'获取任务失败: {str(e)}'}), 500

@app.route('/api/tasks/<task_id>/pause', methods=['POST'])
def pause_task(task_id):
    """暂停任务"""
    try:
        record = DownloadRecord.get_by_task_id(task_id)
        if not record:
            return jsonify({'error': '任务不存在'}), 404

        if record.status == "downloading":
            # 停止线程
            if task_id in active_tasks:
                active_tasks[task_id].stop()

            record.mark_paused()
            db.session.commit()
            return jsonify({'message': '任务已暂停'})
        else:
            return jsonify({'error': '任务状态不允许暂停'}), 400
    except Exception as e:
        return jsonify({'error': f'暂停任务失败: {str(e)}'}), 500

@app.route('/api/tasks/<task_id>/resume', methods=['POST'])
def resume_task(task_id):
    """恢复任务"""
    try:
        record = DownloadRecord.get_by_task_id(task_id)
        if not record:
            return jsonify({'error': '任务不存在'}), 404

        if record.status == "paused":
            # 检查是否可以立即开始下载
            if len(active_tasks) < max_concurrent_tasks:
                record.status = "pending"
                db.session.commit()

                # 创建新的任务线程
                task_thread = TaskThread(task_id)
                active_tasks[task_id] = task_thread

                # 启动下载线程
                task_thread.start(download_m3u8_task)
            else:
                # 添加到队列
                record.mark_queued()
                db.session.commit()
                task_queue.append(task_id)

            return jsonify({'message': '任务已恢复'})
        else:
            return jsonify({'error': '任务状态不允许恢复'}), 400
    except Exception as e:
        return jsonify({'error': f'恢复任务失败: {str(e)}'}), 500

@app.route('/api/tasks/<task_id>/update_url', methods=['POST'])
def update_task_url(task_id):
    """更新任务URL"""
    data = request.json
    new_url = data.get('url', '').strip()
    new_title = data.get('title', '').strip()

    if not new_url:
        return jsonify({'error': '请提供新的URL'}), 400

    try:
        record = DownloadRecord.get_by_task_id(task_id)
        if not record:
            return jsonify({'error': '任务不存在'}), 404

        if record.status == "downloading":
            return jsonify({'error': '请先暂停任务再更新URL'}), 400

        record.url = new_url
        if new_title:
            record.title = new_title
        record.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({'message': '任务已更新'})
    except Exception as e:
        return jsonify({'error': f'更新任务失败: {str(e)}'}), 500

@app.route('/api/tasks/<task_id>/delete', methods=['DELETE'])
def delete_task(task_id):
    """删除任务"""
    try:
        record = DownloadRecord.get_by_task_id(task_id)
        if record:
            # 停止下载
            if record.status == "downloading" and task_id in active_tasks:
                active_tasks[task_id].stop()
                del active_tasks[task_id]

            # 从队列中移除
            if task_id in task_queue:
                task_queue.remove(task_id)

            # 删除数据库记录
            db.session.delete(record)
            db.session.commit()

        return jsonify({'message': '任务已删除'})
    except Exception as e:
        return jsonify({'error': f'删除任务失败: {str(e)}'}), 500

# 设置管理API
@app.route('/api/settings', methods=['GET'])
def get_settings():
    """获取当前设置"""
    with settings_lock:
        current_settings = runtime_settings.copy()
        current_settings.update({
            'max_concurrent_tasks': max_concurrent_tasks,
            'active_tasks_count': len(active_tasks),
            'queued_tasks_count': len(task_queue),
            'min_thread_count': app_config.MIN_THREAD_COUNT,
            'max_thread_count': app_config.MAX_THREAD_COUNT,
            'min_concurrent_tasks': app_config.MIN_CONCURRENT_TASKS,
            'max_concurrent_tasks_limit': app_config.MAX_CONCURRENT_TASKS
        })
    return jsonify(current_settings)

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """更新设置"""
    global max_concurrent_tasks

    data = request.json
    updated = {}

    with settings_lock:
        # 更新线程数
        if 'thread_count' in data:
            thread_count = int(data['thread_count'])
            if app_config.MIN_THREAD_COUNT <= thread_count <= app_config.MAX_THREAD_COUNT:
                runtime_settings['thread_count'] = thread_count
                updated['thread_count'] = thread_count

        # 更新最大并发任务数
        if 'max_concurrent_tasks' in data:
            concurrent_tasks = int(data['max_concurrent_tasks'])
            if app_config.MIN_CONCURRENT_TASKS <= concurrent_tasks <= app_config.MAX_CONCURRENT_TASKS:
                max_concurrent_tasks = concurrent_tasks
                runtime_settings['max_concurrent_tasks'] = concurrent_tasks
                updated['max_concurrent_tasks'] = concurrent_tasks
                # 处理队列中的任务
                process_task_queue()

        # 更新下载超时时间
        if 'download_timeout' in data:
            timeout = int(data['download_timeout'])
            if 5 <= timeout <= 300:  # 5秒到5分钟
                runtime_settings['download_timeout'] = timeout
                updated['download_timeout'] = timeout

        # 更新最大重试次数
        if 'max_retry_count' in data:
            retry_count = int(data['max_retry_count'])
            if 0 <= retry_count <= 10:
                runtime_settings['max_retry_count'] = retry_count
                updated['max_retry_count'] = retry_count

        # 更新FFmpeg线程数
        if 'ffmpeg_threads' in data:
            ffmpeg_threads = int(data['ffmpeg_threads'])
            if 1 <= ffmpeg_threads <= 16:
                runtime_settings['ffmpeg_threads'] = ffmpeg_threads
                updated['ffmpeg_threads'] = ffmpeg_threads

        # 更新自动清理天数
        if 'auto_cleanup_days' in data:
            cleanup_days = int(data['auto_cleanup_days'])
            if 1 <= cleanup_days <= 30:
                runtime_settings['auto_cleanup_days'] = cleanup_days
                updated['auto_cleanup_days'] = cleanup_days

    if updated:
        return jsonify({'message': '设置更新成功', 'updated': updated})
    else:
        return jsonify({'error': '没有有效的设置更新'}), 400

@app.route('/api/settings/reset', methods=['POST'])
def reset_settings():
    """重置设置为默认值"""
    global max_concurrent_tasks

    with settings_lock:
        runtime_settings.update(app_config.USER_CONFIGURABLE.copy())
        max_concurrent_tasks = runtime_settings['max_concurrent_tasks']

    return jsonify({'message': '设置已重置为默认值'})

@app.route('/api/queue/status', methods=['GET'])
def get_queue_status():
    """获取队列状态"""
    try:
        total_tasks = DownloadRecord.query.count()
        return jsonify({
            'active_tasks': len(active_tasks),
            'queued_tasks': len(task_queue),
            'max_concurrent_tasks': max_concurrent_tasks,
            'total_tasks': total_tasks,
            'active_task_ids': list(active_tasks.keys()),
            'queued_task_ids': task_queue
        })
    except Exception as e:
        return jsonify({'error': f'获取队列状态失败: {str(e)}'}), 500

@app.route('/api/tasks/<task_id>/convert', methods=['POST'])
def convert_to_mp4(task_id):
    """将完成的M3U8任务转换为MP4"""
    try:
        record = DownloadRecord.get_by_task_id(task_id)
        if not record:
            return jsonify({'error': '任务不存在'}), 404

        if record.status != "completed":
            return jsonify({'error': '只能转换已完成的任务'}), 400

        if not record.segments_path or not os.path.exists(record.segments_path):
            return jsonify({'error': '切片文件不存在'}), 400

        # 创建转换输出目录
        output_path = os.path.join(CONVERTED_DIR, f"{record.title}.mp4")

        # 创建文件列表
        segments_list = []
        for filename in sorted(os.listdir(record.segments_path)):
            if filename.endswith('.ts'):
                segments_list.append(os.path.join(record.segments_path, filename))

        if not segments_list:
            return jsonify({'error': '没有找到切片文件'}), 400

        # 使用ffmpeg合并切片
        # 创建临时文件列表，使用UTF-8编码
        list_file = os.path.join(record.segments_path, 'filelist.txt')
        with open(list_file, 'w', encoding='utf-8') as f:
            for segment_path in segments_list:
                # 使用绝对路径并正确转义
                abs_path = os.path.abspath(segment_path)
                # 在路径中的单引号需要转义
                escaped_path = abs_path.replace("'", "'\"'\"'")
                f.write(f"file '{escaped_path}'\n")

        # 执行ffmpeg命令
        ffmpeg_path = app_config.FFMPEG_PATH
        print(f"使用 FFmpeg 路径: {ffmpeg_path}")

        cmd = [
            ffmpeg_path, '-f', 'concat', '-safe', '0',
            '-i', list_file, '-c', 'copy', output_path, '-y'
        ]

        print(f"执行 FFmpeg 命令: {' '.join(cmd)}")
        print(f"文件列表路径: {list_file}")
        print(f"输出路径: {output_path}")

        # 检查文件列表内容
        try:
            with open(list_file, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"文件列表内容:\n{content}")
        except Exception as e:
            print(f"读取文件列表失败: {e}")

        result = subprocess.run(cmd, capture_output=True, text=True)

        print(f"FFmpeg 返回码: {result.returncode}")
        if result.stdout:
            print(f"FFmpeg 输出: {result.stdout}")
        if result.stderr:
            print(f"FFmpeg 错误: {result.stderr}")

        # 清理临时文件
        if os.path.exists(list_file):
            os.remove(list_file)

        if result.returncode == 0:
            # 获取文件大小
            file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0

            # 更新数据库记录 - 标记为已转换
            record.mark_converted(output_path, file_size)
            db.session.commit()

            return jsonify({'message': '转换成功', 'output_path': output_path, 'converted': True})
        else:
            # 如果 concat 方法失败，尝试备用方法：直接合并 TS 文件
            print("concat 方法失败，尝试备用方法...")

            try:
                # 方法2：使用 copy 协议直接合并
                temp_output = output_path + '.temp'

                # 创建一个简化的文件名映射
                simple_segments = []
                for i, segment_path in enumerate(segments_list):
                    if os.path.exists(segment_path):
                        simple_segments.append(segment_path)

                if simple_segments:
                    # 使用 binary 模式直接合并文件
                    with open(temp_output, 'wb') as outfile:
                        for segment_path in simple_segments:
                            try:
                                with open(segment_path, 'rb') as infile:
                                    outfile.write(infile.read())
                            except Exception as e:
                                print(f"读取切片文件失败 {segment_path}: {e}")
                                continue

                    # 使用 ffmpeg 转换合并后的文件
                    convert_cmd = [
                        ffmpeg_path, '-i', temp_output,
                        '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
                        output_path, '-y'
                    ]

                    print(f"执行备用转换命令: {' '.join(convert_cmd)}")
                    convert_result = subprocess.run(convert_cmd, capture_output=True, text=True)

                    # 清理临时文件
                    if os.path.exists(temp_output):
                        os.remove(temp_output)

                    if convert_result.returncode == 0:
                        # 获取文件大小
                        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0

                        # 更新数据库记录 - 标记为已转换
                        record.mark_converted(output_path, file_size)
                        db.session.commit()

                        return jsonify({'message': '转换成功（使用备用方法）', 'output_path': output_path, 'converted': True})
                    else:
                        print(f"备用方法也失败: {convert_result.stderr}")
                        return jsonify({'error': f'转换失败: {result.stderr}\n备用方法也失败: {convert_result.stderr}'}), 500
                else:
                    return jsonify({'error': '没有找到有效的切片文件'}), 400

            except Exception as e:
                print(f"备用转换方法出错: {e}")
                return jsonify({'error': f'转换失败: {result.stderr}\n备用方法出错: {str(e)}'}), 500

    except Exception as e:
        return jsonify({'error': f'转换过程中出错: {str(e)}'}), 500

@app.route('/api/tasks/<task_id>/play')
def play_task(task_id):
    """跳转到播放页面"""
    try:
        record = DownloadRecord.get_by_task_id(task_id)
        if not record:
            return jsonify({'error': '任务不存在'}), 404

        # 返回播放页面URL
        play_url = f"/play/{task_id}"
        return jsonify({'play_url': play_url})
    except Exception as e:
        return jsonify({'error': f'获取播放链接失败: {str(e)}'}), 500

@app.route('/play/<task_id>')
def play_page(task_id):
    """播放页面"""
    try:
        record = DownloadRecord.get_by_task_id(task_id)
        if not record:
            return "任务不存在", 404

        return render_template('play.html', task=record.to_dict())
    except Exception as e:
        return f"播放页面加载失败: {str(e)}", 500

@app.route('/api/download/<task_id>')
def download_file(task_id):
    """下载转换后的文件"""
    try:
        record = DownloadRecord.get_by_task_id(task_id)
        if not record:
            return jsonify({'error': '任务不存在'}), 404

        if not record.download_path or not os.path.exists(record.download_path):
            return jsonify({'error': '文件不存在'}), 404

        return send_file(record.download_path, as_attachment=True)
    except Exception as e:
        return jsonify({'error': f'下载文件失败: {str(e)}'}), 500

# 数据库初始化和应用启动前的操作
def init_database():
    """初始化数据库"""
    with app.app_context():
        # 创建所有表
        db.create_all()
        print("数据库初始化完成")

        # 执行数据库迁移
        try:
            from migrate_db import migrate_database
            migrate_database()
        except Exception as e:
            print(f"数据库迁移失败: {e}")

        # 恢复未完成的任务
        restore_active_tasks()

def restore_active_tasks():
    """恢复应用重启前的活跃任务"""
    try:
        # 获取所有未完成的任务
        active_records = DownloadRecord.get_all_active()

        for record in active_records:
            if record.status == "downloading":
                # 将下载中的任务标记为暂停，等待用户手动恢复
                record.mark_paused()
            elif record.status == "queued":
                # 将排队的任务重新加入队列
                task_queue.append(record.task_id)

        db.session.commit()

        if active_records:
            print(f"恢复了 {len(active_records)} 个未完成的任务")

        # 处理队列中的任务
        process_task_queue()

    except Exception as e:
        print(f"恢复活跃任务失败: {e}")

# 添加统计API
@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """获取下载统计信息"""
    try:
        # 更新今日统计
        DownloadStatistics.update_daily_stats()

        # 获取基本统计
        total_tasks = DownloadRecord.query.count()
        completed_tasks = DownloadRecord.query.filter_by(status='completed').count()
        failed_tasks = DownloadRecord.query.filter_by(status='failed').count()
        active_tasks_count = DownloadRecord.query.filter(
            DownloadRecord.status.in_(['pending', 'downloading', 'paused', 'queued'])
        ).count()

        # 获取今日统计
        today_stats = DownloadStatistics.get_or_create_today()

        # 获取最近7天的统计
        from datetime import timedelta
        seven_days_ago = datetime.utcnow().date() - timedelta(days=7)
        recent_stats = DownloadStatistics.query.filter(
            DownloadStatistics.date >= seven_days_ago
        ).order_by(DownloadStatistics.date.desc()).all()

        return jsonify({
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'failed_tasks': failed_tasks,
            'active_tasks': active_tasks_count,
            'success_rate': round((completed_tasks / total_tasks * 100), 2) if total_tasks > 0 else 0,
            'today_stats': today_stats.to_dict(),
            'recent_stats': [stat.to_dict() for stat in recent_stats]
        })
    except Exception as e:
        return jsonify({'error': f'获取统计信息失败: {str(e)}'}), 500

@app.route('/api/tasks/cleanup', methods=['POST'])
def cleanup_old_tasks():
    """清理旧的已完成任务"""
    try:
        data = request.json or {}
        days = data.get('days', runtime_settings['auto_cleanup_days'])

        if days < 1 or days > 30:
            return jsonify({'error': '清理天数必须在1-30之间'}), 400

        cleaned_count = DownloadRecord.cleanup_old_records(days)
        return jsonify({
            'message': f'已清理 {cleaned_count} 个旧任务记录',
            'cleaned_count': cleaned_count
        })
    except Exception as e:
        return jsonify({'error': f'清理任务失败: {str(e)}'}), 500

if __name__ == '__main__':
    print("Flask M3U8 下载管理器启动中...")
    print(f"下载目录: {DOWNLOAD_DIR}")

    # 初始化数据库
    init_database()

    print("访问地址: http://localhost:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)
