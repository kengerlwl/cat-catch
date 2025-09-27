# -*- coding: utf-8 -*-
"""
数据库模型定义
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import json

db = SQLAlchemy()

class DownloadRecord(db.Model):
    """下载记录模型"""
    __tablename__ = 'download_records'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    url = db.Column(db.Text, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    custom_dir = db.Column(db.String(255), default='')
    thread_count = db.Column(db.Integer, default=6)
    status = db.Column(db.String(20), default='pending', index=True)  # pending, downloading, paused, completed, failed, queued
    progress = db.Column(db.Integer, default=0)
    total_segments = db.Column(db.Integer, default=0)
    downloaded_segments = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text, default='')
    download_path = db.Column(db.String(500), default='')
    segments_path = db.Column(db.String(500), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    file_size = db.Column(db.BigInteger, default=0)  # 文件大小（字节）
    download_speed = db.Column(db.Float, default=0.0)  # 下载速度（MB/s）
    is_converted = db.Column(db.Boolean, default=False)  # 是否已转换为MP4
    converted_at = db.Column(db.DateTime, nullable=True)  # 转换完成时间

    def __init__(self, task_id, url, title="", custom_dir="", thread_count=6):
        self.task_id = task_id
        self.url = url
        self.title = title or f"task_{task_id[:8]}"
        self.custom_dir = custom_dir
        self.thread_count = thread_count
        self.status = "pending"
        self.progress = 0
        self.total_segments = 0
        self.downloaded_segments = 0
        self.error_message = ""
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'url': self.url,
            'title': self.title,
            'custom_dir': self.custom_dir,
            'thread_count': self.thread_count,
            'status': self.status,
            'progress': self.progress,
            'total_segments': self.total_segments,
            'downloaded_segments': self.downloaded_segments,
            'error_message': self.error_message,
            'download_path': self.download_path,
            'segments_path': self.segments_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'file_size': self.file_size,
            'download_speed': self.download_speed,
            'is_converted': self.is_converted,
            'converted_at': self.converted_at.isoformat() if self.converted_at else None
        }

    def update_progress(self, downloaded_segments, total_segments=None):
        """更新下载进度"""
        self.downloaded_segments = downloaded_segments
        if total_segments is not None:
            self.total_segments = total_segments

        if self.total_segments > 0:
            self.progress = int((self.downloaded_segments / self.total_segments) * 100)

        self.updated_at = datetime.utcnow()

    def mark_completed(self, download_path="", file_size=0):
        """标记为完成状态"""
        self.status = "completed"
        self.progress = 100
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        if download_path:
            self.download_path = download_path
        if file_size > 0:
            self.file_size = file_size

    def mark_failed(self, error_message=""):
        """标记为失败状态"""
        self.status = "failed"
        self.error_message = error_message
        self.updated_at = datetime.utcnow()

    def mark_paused(self):
        """标记为暂停状态"""
        self.status = "paused"
        self.updated_at = datetime.utcnow()

    def mark_downloading(self):
        """标记为下载中状态"""
        self.status = "downloading"
        self.updated_at = datetime.utcnow()

    def mark_queued(self):
        """标记为排队状态"""
        self.status = "queued"
        self.updated_at = datetime.utcnow()

    def mark_converted(self, download_path="", file_size=0):
        """标记为已转换状态"""
        self.is_converted = True
        self.converted_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        if download_path:
            self.download_path = download_path
        if file_size > 0:
            self.file_size = file_size

    @staticmethod
    def get_by_task_id(task_id):
        """根据任务ID获取记录"""
        return DownloadRecord.query.filter_by(task_id=task_id).first()

    @staticmethod
    def get_all_active():
        """获取所有活跃的任务（非完成、失败状态）"""
        return DownloadRecord.query.filter(
            DownloadRecord.status.in_(['pending', 'downloading', 'paused', 'queued'])
        ).all()

    @staticmethod
    def get_completed_tasks():
        """获取所有已完成的任务"""
        return DownloadRecord.query.filter_by(status='completed').order_by(
            DownloadRecord.completed_at.desc()
        ).all()

    @staticmethod
    def get_failed_tasks():
        """获取所有失败的任务"""
        return DownloadRecord.query.filter_by(status='failed').order_by(
            DownloadRecord.updated_at.desc()
        ).all()

    @staticmethod
    def cleanup_old_records(days=7):
        """清理指定天数前的已完成任务"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        old_records = DownloadRecord.query.filter(
            DownloadRecord.status == 'completed',
            DownloadRecord.completed_at < cutoff_date
        ).all()

        for record in old_records:
            db.session.delete(record)

        db.session.commit()
        return len(old_records)

class DownloadStatistics(db.Model):
    """下载统计模型"""
    __tablename__ = 'download_statistics'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False, index=True)
    total_downloads = db.Column(db.Integer, default=0)
    completed_downloads = db.Column(db.Integer, default=0)
    failed_downloads = db.Column(db.Integer, default=0)
    total_size = db.Column(db.BigInteger, default=0)  # 总下载大小（字节）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'total_downloads': self.total_downloads,
            'completed_downloads': self.completed_downloads,
            'failed_downloads': self.failed_downloads,
            'total_size': self.total_size,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @staticmethod
    def get_or_create_today():
        """获取或创建今天的统计记录"""
        today = datetime.utcnow().date()
        stats = DownloadStatistics.query.filter_by(date=today).first()

        if not stats:
            stats = DownloadStatistics(date=today)
            db.session.add(stats)
            db.session.commit()

        return stats

    @staticmethod
    def update_daily_stats():
        """更新每日统计"""
        today = datetime.utcnow().date()
        stats = DownloadStatistics.get_or_create_today()

        # 统计今日任务
        today_records = DownloadRecord.query.filter(
            db.func.date(DownloadRecord.created_at) == today
        ).all()

        stats.total_downloads = len(today_records)
        stats.completed_downloads = len([r for r in today_records if r.status == 'completed'])
        stats.failed_downloads = len([r for r in today_records if r.status == 'failed'])
        stats.total_size = sum([r.file_size for r in today_records if r.file_size > 0])
        stats.updated_at = datetime.utcnow()

        db.session.commit()
        return stats
