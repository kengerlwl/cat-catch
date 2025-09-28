#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本 - 添加转换状态字段
"""

import os
import sqlite3
from datetime import datetime

def migrate_database():
    """迁移数据库，添加转换状态字段"""
    db_path = os.path.join(os.path.dirname(__file__), 'downloads.db')

    if not os.path.exists(db_path):
        print("数据库文件不存在，无需迁移")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查是否已经存在新字段
        cursor.execute("PRAGMA table_info(download_records)")
        columns = [column[1] for column in cursor.fetchall()]

        needs_migration = False

        # 检查是否需要添加 is_converted 字段
        if 'is_converted' not in columns:
            print("添加 is_converted 字段...")
            cursor.execute("ALTER TABLE download_records ADD COLUMN is_converted BOOLEAN DEFAULT 0")
            needs_migration = True

        # 检查是否需要添加 converted_at 字段
        if 'converted_at' not in columns:
            print("添加 converted_at 字段...")
            cursor.execute("ALTER TABLE download_records ADD COLUMN converted_at DATETIME")
            needs_migration = True

        # 检查是否需要创建 config 表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'")
        config_table_exists = cursor.fetchone() is not None

        if not config_table_exists:
            print("创建 config 表...")
            cursor.execute("""
                CREATE TABLE config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key VARCHAR(100) NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    value_type VARCHAR(20) DEFAULT 'str',
                    description VARCHAR(255) DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX idx_config_key ON config (key)")
            needs_migration = True

        if needs_migration:
            # 更新已有的转换记录
            print("更新现有记录的转换状态...")
            cursor.execute("""
                UPDATE download_records
                SET is_converted = 1, converted_at = updated_at
                WHERE status = 'completed' AND download_path != '' AND download_path IS NOT NULL
            """)

            conn.commit()
            print(f"数据库迁移完成！更新了 {cursor.rowcount} 条记录")
        else:
            print("数据库已是最新版本，无需迁移")

        conn.close()

    except Exception as e:
        print(f"数据库迁移失败: {e}")
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("🔄 开始数据库迁移...")
    migrate_database()
    print("✅ 迁移完成！")
