# -*- coding: utf-8 -*-
"""
Agent协议模块 - 任务定义

定义Agent处理的任务类型：
- TaskType: 任务类型枚举（文本/图片/视频/音频/文件/混合）
- TaskStatus: 任务状态枚举（初始化/处理中/完成/失败）
- Task: 任务数据类
"""

# 启用延迟类型注解
from __future__ import annotations

# 导入时间模块
import time

# 导入UUID生成模块
import uuid

# 导入数据类装饰器
from dataclasses import dataclass, field

# 导入枚举类
from enum import Enum

# 导入类型提示
from typing import Dict, Any, List


class TaskType(Enum):
    """
    任务类型枚举
    
    定义Agent可以处理的不同类型任务：
    - TEXT: 纯文本任务
    - IMAGE: 图片任务
    - VIDEO: 视频任务
    - AUDIO: 音频任务
    - FILE: 文件任务
    - MIXED: 混合内容任务
    """
    TEXT = "text"      # 文本类型
    IMAGE = "image"    # 图片类型
    VIDEO = "video"    # 视频类型
    AUDIO = "audio"    # 音频类型
    FILE = "file"      # 文件类型
    MIXED = "mixed"    # 混合类型


class TaskStatus(Enum):
    """
    任务状态枚举
    
    定义任务的生命周期状态：
    - INIT: 初始化状态
    - PROCESSING: 处理中
    - COMPLETED: 已完成
    - FAILED: 已失败
    """
    INIT = "init"              # 初始状态
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 已失败


@dataclass
class Task:
    """
    任务数据类
    
    表示Agent需要处理的一个任务，包含任务内容和元数据。
    
    属性说明：
    - id: 任务唯一标识
    - content: 主要文本内容
    - type: 任务类型
    - status: 当前状态
    - created_at: 创建时间戳
    - updated_at: 更新时间戳
    - metadata: 额外元数据
    - images: 图片列表（URL或base64）
    - videos: 视频列表
    - audios: 音频列表
    - files: 文件列表
    """
    # 任务ID（自动生成UUID）
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # 任务文本内容
    content: str = ""
    # 任务类型（默认文本）
    type: TaskType = TaskType.TEXT
    # 任务状态（默认初始化）
    status: TaskStatus = TaskStatus.INIT
    # 创建时间
    created_at: float = field(default_factory=time.time)
    # 更新时间
    updated_at: float = field(default_factory=time.time)
    # 元数据字典
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 媒体内容列表
    images: List[str] = field(default_factory=list)  # 图片列表
    videos: List[str] = field(default_factory=list)  # 视频列表
    audios: List[str] = field(default_factory=list)  # 音频列表
    files: List[str] = field(default_factory=list)   # 文件列表

    def __init__(self, content: str = "", **kwargs):
        """
        初始化任务
        
        Args:
            content: 任务的文本内容
            **kwargs: 其他可选属性
        """
        # 设置任务ID（从参数获取或生成新的）
        self.id = kwargs.get('id', str(uuid.uuid4()))
        # 设置任务内容
        self.content = content
        # 设置任务类型
        self.type = kwargs.get('type', TaskType.TEXT)
        # 设置任务状态
        self.status = kwargs.get('status', TaskStatus.INIT)
        # 设置创建时间
        self.created_at = kwargs.get('created_at', time.time())
        # 设置更新时间
        self.updated_at = kwargs.get('updated_at', time.time())
        # 设置元数据
        self.metadata = kwargs.get('metadata', {})
        # 设置图片列表
        self.images = kwargs.get('images', [])
        # 设置视频列表
        self.videos = kwargs.get('videos', [])
        # 设置音频列表
        self.audios = kwargs.get('audios', [])
        # 设置文件列表
        self.files = kwargs.get('files', [])

    def get_text(self) -> str:
        """
        获取任务的文本内容
        
        Returns:
            任务的文本内容字符串
        """
        return self.content

    def update_status(self, status: TaskStatus) -> None:
        """
        更新任务状态
        
        Args:
            status: 新的任务状态
        """
        # 设置新状态
        self.status = status
        # 更新修改时间
        self.updated_at = time.time()
