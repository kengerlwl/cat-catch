# -*- coding: utf-8 -*-
"""
Flask M3U8 下载管理器配置文件
"""

import os
import platform
import sys

def get_app_data_dir():
    """获取应用数据目录"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe
        app_dir = os.path.dirname(sys.executable)
    else:
        # 如果是开发环境
        app_dir = os.path.dirname(__file__)
    return app_dir

class Config:
    """基础配置"""
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(get_app_data_dir(), 'downloads.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 服务器配置
    HOST = '0.0.0.0'
    PORT = 5000
    DEBUG = False

    # 下载配置
    DOWNLOAD_DIR = os.path.join(get_app_data_dir(), 'downloads')
    SEGMENTS_DIR = os.path.join(DOWNLOAD_DIR, 'segments')
    CONVERTED_DIR = os.path.join(DOWNLOAD_DIR, 'converted')

    # 下载参数
    DEFAULT_THREAD_COUNT = 6          # 默认线程数
    MAX_THREAD_COUNT = 16             # 最大线程数
    MIN_THREAD_COUNT = 1              # 最小线程数
    DOWNLOAD_TIMEOUT = 30             # 下载超时时间
    MAX_RETRY_COUNT = 3               # 最大重试次数

    # 并发任务控制
    DEFAULT_MAX_CONCURRENT_TASKS = 2  # 默认最大并发任务数
    MAX_CONCURRENT_TASKS = 10         # 最大并发任务数限制
    MIN_CONCURRENT_TASKS = 1          # 最小并发任务数

    # 高级下载设置
    CHUNK_SIZE = 8192                 # 下载块大小
    CONNECTION_POOL_SIZE = 10         # 连接池大小
    MAX_CONNECTIONS_PER_HOST = 5      # 每个主机最大连接数

    # 任务队列设置
    QUEUE_CHECK_INTERVAL = 1          # 队列检查间隔(秒)
    TASK_CLEANUP_INTERVAL = 300       # 任务清理间隔(秒)

    # FFmpeg配置
    # 自动检测操作系统并设置FFmpeg路径
    @staticmethod
    def get_ffmpeg_path():
        """根据操作系统自动选择FFmpeg路径"""
        if platform.system() == 'Windows':
            # 检查是否为 PyInstaller 打包的可执行文件
            if hasattr(sys, '_MEIPASS'):
                # 在打包后的可执行文件中，ffmpeg 位于临时目录的 bin 子目录
                packaged_ffmpeg = os.path.join(sys._MEIPASS, 'bin', 'ffmpeg.exe')
                if os.path.exists(packaged_ffmpeg):
                    return packaged_ffmpeg

            # Windows环境下优先使用项目内置的ffmpeg.exe
            local_ffmpeg = os.path.join(os.path.dirname(__file__), 'bin', 'ffmpeg.exe')
            if os.path.exists(local_ffmpeg):
                return local_ffmpeg
            # 如果本地不存在，则尝试系统PATH中的ffmpeg.exe
            return 'ffmpeg.exe'
        else:
            # Linux/macOS环境下使用系统PATH中的ffmpeg
            return 'ffmpeg'

    FFMPEG_PATH = get_ffmpeg_path()   # 自动检测FFmpeg路径
    FFMPEG_THREADS = 4                # FFmpeg转换线程数

    # 任务清理配置
    AUTO_CLEANUP_DAYS = 7             # 自动清理7天前的已完成任务
    MAX_COMPLETED_TASKS = 100         # 最多保留100个已完成任务

    # 用户可配置的设置（可通过API修改）
    USER_CONFIGURABLE = {
        'thread_count': DEFAULT_THREAD_COUNT,
        'max_concurrent_tasks': DEFAULT_MAX_CONCURRENT_TASKS,
        'download_timeout': DOWNLOAD_TIMEOUT,
        'max_retry_count': MAX_RETRY_COUNT,
        'ffmpeg_threads': FFMPEG_THREADS,
        'auto_cleanup_days': AUTO_CLEANUP_DAYS,
        'enable_ai_naming': False
    }

class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True

class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False

    # 生产环境建议修改这些配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'please-change-this-secret-key'

# 配置字典
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
