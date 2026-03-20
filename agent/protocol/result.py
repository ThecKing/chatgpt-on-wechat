# -*- coding: utf-8 -*-
"""
Agent协议模块 - 结果定义

定义Agent执行过程中的结果类型：
- AgentActionType: 动作类型枚举（工具调用/思考/最终回答）
- ToolResult: 工具执行结果
- AgentAction: Agent执行的动作
- AgentResult: Agent最终执行结果
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
from typing import List, Dict, Any, Optional

# 导入任务状态
from agent.protocol.task import Task, TaskStatus


class AgentActionType(Enum):
    """
    Agent动作类型枚举
    
    定义Agent可以执行的三种基本动作类型：
    - TOOL_USE: 工具调用 - Agent使用工具执行操作
    - THINKING: 思考 - Agent进行推理分析
    - FINAL_ANSWER: 最终回答 - Agent给出最终答案
    """
    TOOL_USE = "tool_use"        # 工具调用
    THINKING = "thinking"         # 思考过程
    FINAL_ANSWER = "final_answer" # 最终回答


@dataclass
class ToolResult:
    """
    工具执行结果数据类
    
    记录单个工具调用的完整执行信息。
    
    属性说明：
    - tool_name: 工具名称
    - input_params: 传入工具的参数
    - output: 工具返回的输出
    - status: 执行状态（success/error）
    - error_message: 错误信息（失败时）
    - execution_time: 执行耗时（秒）
    """
    tool_name: str                           # 工具名称
    input_params: Dict[str, Any]             # 输入参数字典
    output: Any                              # 输出结果（任意类型）
    status: str                              # 状态：success 或 error
    error_message: Optional[str] = None      # 错误信息（可选）
    execution_time: float = 0.0              # 执行时间（秒）


@dataclass
class AgentAction:
    """
    Agent动作数据类
    
    记录Agent执行的单个动作。
    
    属性说明：
    - id: 动作唯一标识
    - agent_id: 执行动作的Agent ID
    - agent_name: 执行动作的Agent名称
    - action_type: 动作类型
    - content: 动作内容
    - tool_result: 工具结果（如果是工具调用）
    - timestamp: 动作发生时间
    """
    agent_id: str                            # Agent ID
    agent_name: str                          # Agent名称
    action_type: AgentActionType             # 动作类型
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 自动生成UUID
    content: str = ""                        # 动作内容文本
    tool_result: Optional[ToolResult] = None # 工具结果（可选）
    thought: Optional[str] = None            # 思考内容（可选）
    timestamp: float = field(default_factory=time.time)  # 时间戳


@dataclass
class AgentResult:
    """
    Agent执行结果数据类
    
    记录Agent完成一次完整执行后的最终结果。
    
    属性说明：
    - final_answer: 最终回答内容
    - step_count: 执行步数
    - status: 执行状态（success/error）
    - error_message: 错误信息（失败时）
    """
    final_answer: str                        # 最终回答
    step_count: int                          # 执行步数
    status: str = "success"                  # 状态：默认成功
    error_message: Optional[str] = None      # 错误信息（可选）

    @classmethod
    def success(cls, final_answer: str, step_count: int) -> "AgentResult":
        """
        创建成功的结果
        
        Args:
            final_answer: 最终回答
            step_count: 执行步数
            
        Returns:
            AgentResult实例
        """
        return cls(final_answer=final_answer, step_count=step_count)

    @classmethod
    def error(cls, error_message: str, step_count: int = 0) -> "AgentResult":
        """
        创建错误的结果
        
        Args:
            error_message: 错误信息
            step_count: 执行步数（默认0）
            
        Returns:
            AgentResult实例
        """
        return cls(
            final_answer=f"Error: {error_message}",  # 回答中包含错误信息
            step_count=step_count,
            status="error",                           # 状态设为error
            error_message=error_message
        )

    @property
    def is_error(self) -> bool:
        """
        检查是否为错误结果
        
        Returns:
            True表示是错误，False表示成功
        """
        return self.status == "error"
