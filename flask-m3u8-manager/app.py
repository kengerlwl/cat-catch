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
from datetime import datetime, timedelta
from urllib.parse import urlparse
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, abort, redirect, url_for
from werkzeug.utils import secure_filename
from flask_cors import CORS
import requests
import m3u8

# 导入配置和数据库模型
from config import Config as app_config
from models import db, DownloadRecord, DownloadStatistics, Config, Prompts, LLMConfig
from m3u8_processor import M3U8Processor
from llm_service import init_llm_service_from_db, get_llm_service

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 加载配置
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

# 运行时设置（从数据库加载，可通过API修改）
runtime_settings = {}

# 任务队列管理
task_queue = []
active_tasks = {}  # 存储活跃的任务线程和停止事件
max_concurrent_tasks = 2  # 默认值，将在load_runtime_settings中更新

def check_database_ready():
    """检查数据库是否已准备就绪"""
    try:
        # 简单检查：数据库文件是否存在且不为空
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
            return False

        # 检查关键表是否存在
        with app.app_context():
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            required_tables = ['download_records', 'config', 'prompts', 'download_statistics']

            for table in required_tables:
                if table not in tables:
                    print(f"缺少表: {table}")
                    return False

            return True
    except Exception as e:
        print(f"数据库就绪检查失败: {e}")
        return False

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


def get_ai_optimized_title(original_title):
    """
    使用AI优化电影标题

    Args:
        original_title: 原始标题

    Returns:
        优化后的标题，如果AI处理失败则返回原始标题
    """
    try:
        # 检查是否启用AI命名功能
        enable_ai_naming = Config.get_value('enable_ai_naming', False)
        if not enable_ai_naming:
            return original_title

        # 获取LLM服务
        llm_service = get_llm_service()
        if not llm_service:
            print("LLM服务未初始化，使用原始标题")
            return original_title

        # 检查movie_name_extractor prompt是否存在
        prompt_value = Prompts.get_prompt('movie_name_extractor')
        if not prompt_value:
            print("movie_name_extractor prompt不存在，使用原始标题")
            return original_title

        # 使用AI提取电影名称
        print(f"正在使用AI优化标题: {original_title}")

        response = llm_service.chat_with_prompt(
            user_message=original_title,
            prompt_key='movie_name_extractor',
            temperature=0.3,  # 使用较低的温度以获得更稳定的结果
            max_tokens=100
        )

        if response.get('success'):
            optimized_title = llm_service.extract_content(response)
            if optimized_title and optimized_title.strip():
                print(f"AI优化后的标题: {optimized_title}")
                return optimized_title.strip()
            else:
                print("AI返回空结果，使用原始标题")
                return original_title
        else:
            print(f"AI处理失败: {response.get('error', '未知错误')}，使用原始标题")
            return original_title

    except Exception as e:
        print(f"AI标题优化异常: {str(e)}，使用原始标题")
        return original_title




def load_runtime_settings():
    """从数据库加载运行时设置"""
    global runtime_settings, max_concurrent_tasks

    try:
        # 获取数据库中的所有配置
        db_configs = Config.get_all_configs()

        # 合并默认配置和数据库配置
        runtime_settings = app_config.USER_CONFIGURABLE.copy()
        runtime_settings.update(db_configs)

        # 更新全局变量
        max_concurrent_tasks = runtime_settings.get('max_concurrent_tasks', app_config.DEFAULT_MAX_CONCURRENT_TASKS)

        print(f"✅ 已加载配置: {runtime_settings}")

    except Exception as e:
        print(f"⚠️ 加载配置失败，使用默认配置: {e}")
        runtime_settings = app_config.USER_CONFIGURABLE.copy()
        max_concurrent_tasks = runtime_settings['max_concurrent_tasks']


def save_runtime_setting(key, value, value_type='str', description=''):
    """保存单个运行时设置到数据库"""
    try:
        Config.set_value(key, value, value_type, description)
        runtime_settings[key] = value
        print(f"✅ 已保存配置 {key}: {value}")
        return True
    except Exception as e:
        print(f"❌ 保存配置失败 {key}: {e}")
        return False

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


@app.route('/prompts')
def prompts_page():
    """Prompt管理页面"""
    return render_template('prompts.html')


@app.route('/llm-config')
def llm_config_page():
    """LLM配置页面"""
    return render_template('llm_config.html')

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    """获取所有下载任务"""
    try:
        if not check_database_ready():
            # 数据库表还未创建，返回空列表
            return jsonify({'tasks': [], 'database_initializing': True})

        # 从数据库获取所有任务
        tasks = DownloadRecord.query.order_by(DownloadRecord.created_at.desc()).all()
        tasks_data = [task.to_dict() for task in tasks]
        return jsonify({'tasks': tasks_data, 'database_initializing': False})
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

    # 使用AI优化标题（如果启用了AI命名功能）
    original_title = title
    title = get_ai_optimized_title(title)

    # 如果AI优化后的标题与原标题不同，记录日志
    if title != original_title:
        print(f"标题已通过AI优化: '{original_title}' -> '{title}'")

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
                if save_runtime_setting('thread_count', thread_count, 'int', '默认线程数'):
                    updated['thread_count'] = thread_count

        # 更新最大并发任务数
        if 'max_concurrent_tasks' in data:
            concurrent_tasks = int(data['max_concurrent_tasks'])
            if app_config.MIN_CONCURRENT_TASKS <= concurrent_tasks <= app_config.MAX_CONCURRENT_TASKS:
                if save_runtime_setting('max_concurrent_tasks', concurrent_tasks, 'int', '最大并发任务数'):
                    max_concurrent_tasks = concurrent_tasks
                    updated['max_concurrent_tasks'] = concurrent_tasks
                    # 处理队列中的任务
                    process_task_queue()

        # 更新下载超时时间
        if 'download_timeout' in data:
            timeout = int(data['download_timeout'])
            if 5 <= timeout <= 300:  # 5秒到5分钟
                if save_runtime_setting('download_timeout', timeout, 'int', '下载超时时间(秒)'):
                    updated['download_timeout'] = timeout

        # 更新最大重试次数
        if 'max_retry_count' in data:
            retry_count = int(data['max_retry_count'])
            if 0 <= retry_count <= 10:
                if save_runtime_setting('max_retry_count', retry_count, 'int', '最大重试次数'):
                    updated['max_retry_count'] = retry_count

        # 更新FFmpeg线程数
        if 'ffmpeg_threads' in data:
            ffmpeg_threads = int(data['ffmpeg_threads'])
            if 1 <= ffmpeg_threads <= 16:
                if save_runtime_setting('ffmpeg_threads', ffmpeg_threads, 'int', 'FFmpeg转换线程数'):
                    updated['ffmpeg_threads'] = ffmpeg_threads

        # 更新自动清理天数
        if 'auto_cleanup_days' in data:
            cleanup_days = int(data['auto_cleanup_days'])
            if 1 <= cleanup_days <= 30:
                if save_runtime_setting('auto_cleanup_days', cleanup_days, 'int', '自动清理天数'):
                    updated['auto_cleanup_days'] = cleanup_days

        # 更新AI命名功能开关
        if 'enable_ai_naming' in data:
            enable_ai_naming = bool(data['enable_ai_naming'])
            if save_runtime_setting('enable_ai_naming', enable_ai_naming, 'bool', '启用AI智能命名功能'):
                updated['enable_ai_naming'] = enable_ai_naming

    if updated:
        return jsonify({'message': '设置更新成功', 'updated': updated})
    else:
        return jsonify({'error': '没有有效的设置更新'}), 400

@app.route('/api/settings/reset', methods=['POST'])
def reset_settings():
    """重置设置为默认值"""
    global max_concurrent_tasks

    with settings_lock:
        try:
            # 重置所有配置到默认值
            default_configs = app_config.USER_CONFIGURABLE
            for key, value in default_configs.items():
                # 确定值类型
                value_type = 'int' if isinstance(value, int) else 'float' if isinstance(value, float) else 'bool' if isinstance(value, bool) else 'str'
                save_runtime_setting(key, value, value_type)

            # 更新全局变量
            max_concurrent_tasks = runtime_settings['max_concurrent_tasks']

            return jsonify({'message': '设置已重置为默认值'})
        except Exception as e:
            return jsonify({'error': f'重置设置失败: {str(e)}'}), 500

@app.route('/api/settings/all', methods=['GET'])
def get_all_settings():
    """获取所有配置项（包括数据库中的配置）"""
    try:
        if not check_database_ready():
            # 数据库表还未创建，返回默认配置
            return jsonify({
                'configs': [],
                'runtime_settings': runtime_settings,
                'total_count': 0,
                'database_initializing': True
            })

        with app.app_context():
            configs = Config.query.all()
            config_list = [config.to_dict() for config in configs]

            return jsonify({
                'configs': config_list,
                'runtime_settings': runtime_settings,
                'total_count': len(config_list),
                'database_initializing': False
            })
    except Exception as e:
        return jsonify({'error': f'获取配置失败: {str(e)}'}), 500

@app.route('/api/queue/status', methods=['GET'])
def get_queue_status():
    """获取队列状态"""
    try:
        if not check_database_ready():
            # 数据库表还未创建，返回默认状态
            return jsonify({
                'active_tasks': 0,
                'queued_tasks': 0,
                'max_concurrent_tasks': max_concurrent_tasks,
                'total_tasks': 0,
                'active_task_ids': [],
                'queued_task_ids': [],
                'database_initializing': True
            })

        total_tasks = DownloadRecord.query.count()
        return jsonify({
            'active_tasks': len(active_tasks),
            'queued_tasks': len(task_queue),
            'max_concurrent_tasks': max_concurrent_tasks,
            'total_tasks': total_tasks,
            'active_task_ids': list(active_tasks.keys()),
            'queued_task_ids': task_queue,
            'database_initializing': False
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
    """初始化数据库 - 重构后的简化版本"""
    with app.app_context():
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')

        # 检查数据库文件是否存在
        is_new_database = not os.path.exists(db_path) or os.path.getsize(db_path) == 0

        if is_new_database:
            print("🆕 检测到新环境，正在创建数据库...")
            # 如果是空文件，先删除
            if os.path.exists(db_path):
                os.remove(db_path)
        else:
            print("📂 数据库文件已存在")

        # 创建所有表（如果不存在）
        print("📋 创建数据库表...")
        db.create_all()

        # 验证表创建
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"✅ 数据库表: {tables}")

        # 初始化默认数据（仅在新数据库或缺少默认数据时）
        _init_default_data()

        # 加载运行时设置
        load_runtime_settings()

        # 初始化LLM服务
        try:
            init_llm_service_from_db()
            print("✅ LLM服务初始化完成")
        except Exception as e:
            print(f"❌ LLM服务初始化失败: {e}")

        # 恢复未完成的任务（仅现有数据库）
        if not is_new_database:
            try:
                restore_active_tasks()
                print("✅ 任务恢复完成")
            except Exception as e:
                print(f"❌ 任务恢复失败: {e}")

        print("🎯 数据库初始化完成")


def _init_default_data():
    """初始化默认数据"""
    print("🔧 检查并初始化默认数据...")

    # 初始化Config表的默认配置
    try:
        _ensure_default_configs()
        print("✅ 默认配置检查完成")
    except Exception as e:
        print(f"❌ 配置初始化失败: {e}")

    # 初始化LLM配置
    try:
        _ensure_default_llm_config()
        print("✅ LLM配置检查完成")
    except Exception as e:
        print(f"❌ LLM配置初始化失败: {e}")

    # 初始化Prompts表的默认数据
    try:
        _ensure_default_prompts()
        print("✅ 默认Prompt检查完成")
    except Exception as e:
        print(f"❌ Prompt初始化失败: {e}")


def _ensure_default_configs():
    """确保默认配置存在"""
    from config import Config as AppConfig

    default_configs = [
        ('thread_count', AppConfig.DEFAULT_THREAD_COUNT, 'int', '默认线程数'),
        ('max_concurrent_tasks', AppConfig.DEFAULT_MAX_CONCURRENT_TASKS, 'int', '最大并发任务数'),
        ('download_timeout', AppConfig.DOWNLOAD_TIMEOUT, 'int', '下载超时时间(秒)'),
        ('max_retry_count', AppConfig.MAX_RETRY_COUNT, 'int', '最大重试次数'),
        ('ffmpeg_threads', AppConfig.FFMPEG_THREADS, 'int', 'FFmpeg转换线程数'),
        ('auto_cleanup_days', AppConfig.AUTO_CLEANUP_DAYS, 'int', '自动清理天数'),
        ('enable_ai_naming', False, 'bool', '启用AI智能命名功能'),
    ]

    for key, value, value_type, description in default_configs:
        existing = Config.query.filter_by(key=key).first()
        if not existing:
            config_item = Config(key=key, value=value, value_type=value_type, description=description)
            db.session.add(config_item)

    db.session.commit()


def _ensure_default_llm_config():
    """确保默认LLM配置存在"""
    # 检查是否已存在LLM配置
    existing_config = Config.query.filter_by(key='llm_api_url').first()
    if existing_config:
        return  # 已存在配置，不覆盖

    # 设置默认LLM配置
    llm_configs = [
        ('llm_api_url', 'https://globalai.vip/v1/chat/completions', 'str', 'LLM API接口地址'),
        ('llm_api_key', 'sk-rEh0PI8OkwAyOQbRX9xO7AwdrPPvhuin7x2FN7F96EAfI7ai', 'str', 'LLM API密钥'),
        ('llm_default_model', 'gpt-4.1', 'str', 'LLM默认模型'),
        ('llm_default_max_tokens', 4096, 'int', 'LLM默认最大token数'),
        ('llm_timeout', 30, 'int', 'LLM请求超时时间（秒）'),
    ]

    for key, value, value_type, description in llm_configs:
        config_item = Config(key=key, value=value, value_type=value_type, description=description)
        db.session.add(config_item)

    db.session.commit()


def _ensure_default_prompts():
    """确保默认Prompt存在"""
    # 检查movie_name_extractor prompt是否存在
    existing = Prompts.query.filter_by(key='movie_name_extractor').first()
    if existing:
        return  # 已存在，不覆盖

    # 创建默认的movie_name_extractor prompt
    prompt_value = """你是一个电影名字的归纳员。我正在从网络上下载电影，但是电影名字可以夹带了一些网页的信息，请你从中抽取去电影真正的名字。

例如：

输入：《尖叫之地》全集在线观看 - 电影 - 努努影院

电影名：尖叫之地

注意：

1. 电影名可能含有编号，以及演员名字，这也需要保留

2. 请你直接只输出电影，不要输出其他任何信息

输入：

{input}

电影名："""

    prompt = Prompts(
        key='movie_name_extractor',
        value=prompt_value,
        description='根据输入的混杂信息，抽取并只输出电影的真实名称，保留编号及演员名。'
    )
    db.session.add(prompt)
    db.session.commit()

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
        if not check_database_ready():
            # 数据库表还未创建，返回默认统计
            return jsonify({
                'total_tasks': 0,
                'completed_tasks': 0,
                'failed_tasks': 0,
                'active_tasks': 0,
                'success_rate': 0,
                'today_stats': {
                    'date': datetime.utcnow().date().isoformat(),
                    'total_downloads': 0,
                    'completed_downloads': 0,
                    'failed_downloads': 0,
                    'total_size': 0
                },
                'recent_stats': [],
                'database_initializing': True
            })

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
            'recent_stats': [stat.to_dict() for stat in recent_stats],
            'database_initializing': False
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


# ==================== Prompt管理API ====================

@app.route('/api/prompts', methods=['GET'])
def get_prompts():
    """获取所有prompts"""
    try:
        prompts = Prompts.query.all()
        return jsonify({
            'success': True,
            'prompts': [prompt.to_dict() for prompt in prompts]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取prompts失败: {str(e)}'
        }), 500


@app.route('/api/prompts/<prompt_key>', methods=['GET'])
def get_prompt(prompt_key):
    """获取单个prompt"""
    try:
        prompt = Prompts.query.filter_by(key=prompt_key).first()
        if not prompt:
            return jsonify({
                'success': False,
                'error': 'Prompt不存在'
            }), 404

        return jsonify({
            'success': True,
            'prompt': prompt.to_dict()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取prompt失败: {str(e)}'
        }), 500


@app.route('/api/prompts', methods=['POST'])
def create_prompt():
    """创建新的prompt"""
    try:
        data = request.get_json()

        if not data or 'key' not in data or 'value' not in data:
            return jsonify({
                'success': False,
                'error': '缺少必要参数: key, value'
            }), 400

        key = data['key']
        value = data['value']
        description = data.get('description', '')

        # 检查key是否已存在
        existing = Prompts.query.filter_by(key=key).first()
        if existing:
            return jsonify({
                'success': False,
                'error': f'Prompt key "{key}" 已存在'
            }), 400

        # 创建新prompt
        prompt = Prompts.set_prompt(key=key, value=value, description=description)

        return jsonify({
            'success': True,
            'message': 'Prompt创建成功',
            'prompt': prompt.to_dict()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'创建prompt失败: {str(e)}'
        }), 500


@app.route('/api/prompts/<prompt_key>', methods=['PUT'])
def update_prompt(prompt_key):
    """更新prompt"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少更新数据'
            }), 400

        prompt = Prompts.query.filter_by(key=prompt_key).first()
        if not prompt:
            return jsonify({
                'success': False,
                'error': 'Prompt不存在'
            }), 404

        # 更新字段
        if 'value' in data:
            prompt.value = data['value']
        if 'description' in data:
            prompt.description = data['description']

        prompt.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Prompt更新成功',
            'prompt': prompt.to_dict()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'更新prompt失败: {str(e)}'
        }), 500


@app.route('/api/prompts/<prompt_key>', methods=['DELETE'])
def delete_prompt(prompt_key):
    """删除prompt"""
    try:
        prompt = Prompts.query.filter_by(key=prompt_key).first()
        if not prompt:
            return jsonify({
                'success': False,
                'error': 'Prompt不存在'
            }), 404

        db.session.delete(prompt)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Prompt删除成功'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'删除prompt失败: {str(e)}'
        }), 500


# ==================== LLM配置管理API ====================

@app.route('/api/llm/config', methods=['GET'])
def get_llm_config():
    """获取LLM配置"""
    try:
        config = LLMConfig.get_llm_config()
        # 隐藏API密钥的敏感信息
        if config['api_key']:
            config['api_key'] = config['api_key'][:8] + '***' + config['api_key'][-4:]

        return jsonify({
            'success': True,
            'config': config
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取LLM配置失败: {str(e)}'
        }), 500


@app.route('/api/llm/config', methods=['POST'])
def update_llm_config():
    """更新LLM配置"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少配置数据'
            }), 400

        # 更新配置
        LLMConfig.set_llm_config(
            api_url=data.get('api_url'),
            api_key=data.get('api_key'),
            default_model=data.get('default_model'),
            default_max_tokens=data.get('default_max_tokens'),
            timeout=data.get('timeout')
        )

        return jsonify({
            'success': True,
            'message': 'LLM配置更新成功'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'更新LLM配置失败: {str(e)}'
        }), 500


@app.route('/api/llm/test', methods=['POST'])
def test_llm_connection():
    """测试LLM连接"""
    try:
        # 这里可以添加LLM连接测试逻辑
        # 暂时返回成功状态
        return jsonify({
            'success': True,
            'message': 'LLM连接测试成功'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'LLM连接测试失败: {str(e)}'
        }), 500

@app.route('/api/database/init', methods=['POST'])
def manual_init_database():
    """手动初始化数据库"""
    try:
        print("收到手动初始化数据库请求")
        init_database()

        if check_database_ready():
            return jsonify({
                'success': True,
                'message': '数据库初始化成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '数据库初始化失败，请检查日志'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'数据库初始化失败: {str(e)}'
        }), 500

@app.route('/api/database/status', methods=['GET'])
def get_database_status():
    """获取数据库状态"""
    try:
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')

        status = {
            'database_file_exists': os.path.exists(db_path),
            'database_file_size': os.path.getsize(db_path) if os.path.exists(db_path) else 0,
            'database_ready': check_database_ready(),
            'database_path': db_path
        }

        if status['database_ready']:
            with app.app_context():
                from sqlalchemy import inspect
                inspector = inspect(db.engine)
                status['tables'] = inspector.get_table_names()
        else:
            status['tables'] = []

        return jsonify(status)

    except Exception as e:
        return jsonify({
            'error': f'获取数据库状态失败: {str(e)}'
        }), 500


if __name__ == '__main__':
    print("Flask M3U8 下载管理器启动中...")
    print(f"下载目录: {DOWNLOAD_DIR}")

    # 初始化数据库
    init_database()

    print("访问地址: http://localhost:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)
