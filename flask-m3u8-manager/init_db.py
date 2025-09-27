#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化脚本
用于创建数据库表和初始化数据
"""

from app import app
from models import db, DownloadRecord, DownloadStatistics

def init_database():
    """初始化数据库"""
    with app.app_context():
        print("开始初始化数据库...")

        # 删除所有表（可选，用于重新创建）
        # db.drop_all()
        # print("已删除所有表")

        # 创建所有表
        db.create_all()
        print("已创建所有数据库表")

        # 检查表是否创建成功
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"已创建的表: {tables}")

        # 创建初始统计记录
        today_stats = DownloadStatistics.get_or_create_today()
        print(f"已创建今日统计记录: {today_stats.date}")

        print("数据库初始化完成!")

if __name__ == '__main__':
    init_database()
