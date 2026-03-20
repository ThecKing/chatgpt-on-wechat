# -*- coding: utf-8 -*-
"""
Agent记忆模块

提供长期记忆（向量/关键词搜索）和短期对话历史持久化（SQLite）。

主要组件：
- MemoryManager: 记忆管理器
- MemoryConfig: 记忆配置
- ConversationStore: 对话存储
- EmbeddingProvider: 向量嵌入提供者
"""

# 导入记忆管理器
from agent.memory.manager import MemoryManager

# 导入记忆配置
from agent.memory.config import MemoryConfig, get_default_memory_config, set_global_memory_config

# 导入向量嵌入提供者
from agent.memory.embedding import create_embedding_provider

# 导入对话存储
from agent.memory.conversation_store import ConversationStore, get_conversation_store

# 导入记忆文件确保函数
from agent.memory.summarizer import ensure_daily_memory_file

# 公开导出的类和函数
__all__ = [
    'MemoryManager',              # 记忆管理器
    'MemoryConfig',               # 记忆配置类
    'get_default_memory_config',  # 获取默认配置
    'set_global_memory_config',   # 设置全局配置
    'create_embedding_provider',  # 创建嵌入提供者
    'ConversationStore',          # 对话存储类
    'get_conversation_store',     # 获取对话存储实例
    'ensure_daily_memory_file',   # 确保每日记忆文件存在
]
