# -*- coding: utf-8 -*-
"""
记忆存储层 - 使用SQLite + FTS5

提供向量和关键词搜索能力。

主要组件：
- MemoryChunk: 记忆块数据类
- SearchResult: 搜索结果数据类
- MemoryStorage: SQLite存储类
"""

# 启用延迟类型注解
from __future__ import annotations

# 导入SQLite数据库模块
import sqlite3

# 导入JSON模块
import json

# 导入哈希模块
import hashlib

# 导入类型提示
from typing import List, Dict, Optional, Any

# 导入路径处理
from pathlib import Path

# 导入数据类装饰器
from dataclasses import dataclass


@dataclass
class MemoryChunk:
    """
    记忆块数据类
    
    表示一个带有文本和嵌入向量的记忆块。
    
    属性说明：
    - id: 唯一标识
    - user_id: 用户ID
    - scope: 范围（shared/user/session）
    - source: 来源（memory/session）
    - path: 文件路径
    - start_line: 起始行号
    - end_line: 结束行号
    - text: 文本内容
    - embedding: 嵌入向量
    - hash: 内容哈希
    - metadata: 元数据
    """
    id: str                                    # 唯一标识
    user_id: Optional[str]                     # 用户ID
    scope: str                                 # 范围：shared/user/session
    source: str                                # 来源：memory/session
    path: str                                  # 文件路径
    start_line: int                            # 起始行号
    end_line: int                              # 结束行号
    text: str                                  # 文本内容
    embedding: Optional[List[float]]           # 嵌入向量
    hash: str                                  # 内容哈希
    metadata: Optional[Dict[str, Any]] = None  # 元数据


@dataclass
class SearchResult:
    """
    搜索结果数据类
    
    表示一个搜索结果，包含分数和片段。
    
    属性说明：
    - path: 文件路径
    - start_line: 起始行号
    - end_line: 结束行号
    - score: 相关性分数
    - snippet: 内容片段
    - source: 来源
    - user_id: 用户ID
    """
    path: str                        # 文件路径
    start_line: int                  # 起始行号
    end_line: int                    # 结束行号
    score: float                     # 相关性分数
    snippet: str                     # 内容片段
    source: str                      # 来源
    user_id: Optional[str] = None    # 用户ID


class MemoryStorage:
    """
    基于SQLite的存储类，使用FTS5进行关键词搜索
    
    功能：
    - 存储记忆块
    - 向量相似度搜索
    - FTS5全文搜索
    - 混合搜索
    """
    
    def __init__(self, db_path: Path):
        """
        初始化存储
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path                # 数据库路径
        self.conn: Optional[sqlite3.Connection] = None  # 数据库连接
        self.fts5_available = False           # FTS5可用性标记
        self._init_db()                       # 初始化数据库
    
    def _check_fts5_support(self) -> bool:
        """
        检查SQLite是否支持FTS5
        
        Returns:
            bool: True表示支持FTS5
        """
        try:
            # 尝试创建FTS5虚拟表
            self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts5_test USING fts5(test)")
            self.conn.execute("DROP TABLE IF EXISTS fts5_test")
            return True
        except sqlite3.OperationalError as e:
            # 如果提示没有FTS5模块
            if "no such module: fts5" in str(e):
                return False
            raise
    
    def _init_db(self):
        """初始化数据库模式"""
        try:
            # 连接数据库
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            
            # 检查FTS5支持
            self.fts5_available = self._check_fts5_support()
            if not self.fts5_available:
                from common.log import logger
                logger.debug("[MemoryStorage] FTS5 not available, using LIKE-based keyword search")
            
            # 检查数据库完整性
            try:
                result = self.conn.execute("PRAGMA integrity_check").fetchone()
                if result[0] != 'ok':
                    print(f"⚠️  Database integrity check failed: {result[0]}")
                    print(f"   Recreating database...")
                    self.conn.close()
                    self.conn = None
                    # 删除损坏的数据库
                    self.db_path.unlink(missing_ok=True)
                    # 删除WAL文件
                    Path(str(self.db_path) + '-wal').unlink(missing_ok=True)
                    Path(str(self.db_path) + '-shm').unlink(missing_ok=True)
                    # 重新连接创建新数据库
                    self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
                    self.conn.row_factory = sqlite3.Row
            except sqlite3.DatabaseError:
                # 数据库损坏，重建
                print(f"⚠️  Database is corrupted, recreating...")
                if self.conn:
                    self.conn.close()
                    self.conn = None
                self.db_path.unlink(missing_ok=True)
                Path(str(self.db_path) + '-wal').unlink(missing_ok=True)
                Path(str(self.db_path) + '-shm').unlink(missing_ok=True)
