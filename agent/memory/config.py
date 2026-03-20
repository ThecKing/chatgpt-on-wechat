# -*- coding: utf-8 -*-
"""
记忆配置模块

提供全局记忆配置，简化工作区结构。

配置项：
- workspace_root: 工作区根目录（默认：~/cow）
- embedding_provider: 向量嵌入提供者（openai/local）
- embedding_model: 嵌入模型名称
- chunk_max_tokens: 分块最大token数
- max_results: 搜索最大结果数
"""

# 启用延迟类型注解
from __future__ import annotations

# 导入操作系统模块
import os

# 导入数据类装饰器
from dataclasses import dataclass, field

# 导入类型提示
from typing import Optional, List

# 导入路径处理
from pathlib import Path


def _default_workspace():
    """
    获取默认工作区路径（支持Windows）
    
    Returns:
        str: 默认工作区路径
    """
    from common.utils import expand_path
    return expand_path("~/cow")


@dataclass
class MemoryConfig:
    """
    记忆存储和搜索配置类
    
    使用数据类简化配置管理。
    支持向量嵌入、分块、搜索等多种配置。
    """
    
    # 存储路径（默认：~/cow）
    workspace_root: str = field(default_factory=_default_workspace)
    
    # 向量嵌入配置
    embedding_provider: str = "openai"  # 嵌入提供者："openai" | "local"
    embedding_model: str = "text-embedding-3-small"  # 嵌入模型名称
    embedding_dim: int = 1536  # 嵌入向量维度
    
    # 分块配置
    chunk_max_tokens: int = 500  # 每块最大token数
    chunk_overlap_tokens: int = 50  # 块之间重叠token数
    
    # 搜索配置
    max_results: int = 10  # 最大返回结果数
    min_score: float = 0.1  # 最小相关性分数阈值
    
    # 混合搜索权重
    vector_weight: float = 0.7  # 向量搜索权重
    keyword_weight: float = 0.3  # 关键词搜索权重
    
    # 记忆来源
    sources: List[str] = field(default_factory=lambda: ["memory", "session"])
    
    # 同步配置
    enable_auto_sync: bool = True  # 启用自动同步
    sync_on_search: bool = True  # 搜索时同步
    
    
    def get_workspace(self) -> Path:
        """
        获取工作区根目录
        
        Returns:
            Path: 工作区路径对象
        """
        return Path(self.workspace_root)
    
    def get_memory_dir(self) -> Path:
        """
        获取记忆文件目录
        
        Returns:
            Path: 记忆目录路径（workspace/memory）
        """
        return self.get_workspace() / "memory"
    
    def get_db_path(self) -> Path:
        """
        获取长期记忆索引的SQLite数据库路径
        
        Returns:
            Path: 数据库文件路径
        """
        # 索引存储在 memory/long-term/index.db
        index_dir = self.get_memory_dir() / "long-term"
        index_dir.mkdir(parents=True, exist_ok=True)
        return index_dir / "index.db"
    
    def get_skills_dir(self) -> Path:
        """
        获取技能目录
        
        Returns:
            Path: 技能目录路径
        """
        return self.get_workspace() / "skills"
    
    def get_agent_workspace(self, agent_name: Optional[str] = None) -> Path:
        """
        获取Agent的工作区目录
        
        Args:
            agent_name: 可选的Agent名称（当前实现未使用）
            
        Returns:
            Path: 工作区目录路径
        """
        workspace = self.get_workspace()
        # 确保工作区目录存在
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace


# 全局记忆配置实例
_global_memory_config: Optional[MemoryConfig] = None


def get_default_memory_config() -> MemoryConfig:
    """
    获取全局记忆配置
    
    如果未设置，返回默认配置。
    
    Returns:
        MemoryConfig: 记忆配置实例
    """
    global _global_memory_config
    if _global_memory_config is None:
        _global_memory_config = MemoryConfig()
    return _global_memory_config


def set_global_memory_config(config: MemoryConfig):
    """
    设置全局记忆配置
    
    应在创建任何MemoryManager实例之前调用。
    
    Args:
        config: 要使用的MemoryConfig实例
        
    Example:
        >>> from agent.memory import MemoryConfig, set_global_memory_config
        >>> config = MemoryConfig(
        ...     workspace_root="~/my_agents",
        ...     embedding_provider="openai",
        ...     vector_weight=0.8
        ... )
        >>> set_global_memory_config(config)
    """
    global _global_memory_config
    _global_memory_config = config
