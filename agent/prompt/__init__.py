# -*- coding: utf-8 -*-
"""
Agent提示词模块 - 系统提示词构建模块

提供模块化的系统提示词构建功能：
- PromptBuilder: 提示词构建器类
- build_agent_system_prompt: 构建系统提示词函数
- ensure_workspace: 确保工作区存在
- load_context_files: 加载上下文文件
"""

# 导入提示词构建器
from .builder import PromptBuilder, build_agent_system_prompt

# 导入工作区工具
from .workspace import ensure_workspace, load_context_files

# 公开导出的类和函数
__all__ = [
    'PromptBuilder',            # 提示词构建器类
    'build_agent_system_prompt', # 构建系统提示词函数
    'ensure_workspace',         # 确保工作区存在
    'load_context_files',       # 加载上下文文件
]
