# -*- coding: utf-8 -*-
"""
Agent协议模块 - 包导出

导出Agent系统的核心类和接口：
- Agent: 主Agent类
- AgentStreamExecutor: 流式执行器
- Task/TaskType/TaskStatus: 任务相关类
- AgentResult/AgentAction/AgentActionType/ToolResult: 结果相关类
- LLMModel/LLMRequest/ModelFactory: 模型相关类
"""

# 从agent模块导入Agent主类
from .agent import Agent

# 从agent_stream模块导入流式执行器
from .agent_stream import AgentStreamExecutor

# 从task模块导入任务相关类
from .task import Task, TaskType, TaskStatus

# 从result模块导入结果相关类
from .result import AgentResult, AgentAction, AgentActionType, ToolResult

# 从models模块导入模型相关类
from .models import LLMModel, LLMRequest, ModelFactory

# 定义公开导出的类列表
__all__ = [
    'Agent',               # Agent主类
    'AgentStreamExecutor', # 流式执行器
    'Task',                # 任务类
    'TaskType',            # 任务类型枚举
    'TaskStatus',          # 任务状态枚举
    'AgentResult',         # Agent结果类
    'AgentAction',         # Agent动作类
    'AgentActionType',     # 动作类型枚举
    'ToolResult',          # 工具结果类
    'LLMModel',            # LLM模型基类
    'LLMRequest',          # LLM请求类
    'ModelFactory'         # 模型工厂类
]
