# -*- coding: utf-8 -*-
"""
Agent 结果模型模块

定义Agent执行结果的数据模型：
1. AgentActionType: Agent动作类型枚举
2. ToolResult: 工具执行结果
3. AgentAction: Agent动作
4. AgentResult: Agent执行结果

这些数据结构用于记录和传递Agent的执行结果。
"""

# 导入未来注解支持（Python 3.9之前需要）
from __future__ import annotations

# 导入时间模块
import time

# 导入UUID模块
import uuid

# 导入数据类装饰器
from dataclasses import dataclass, field

# 导入枚举类型
from enum import Enum

# 导入类型提示
from typing import List, Dict, Any, Optional

# 导入任务模块
from agent.protocol.task import Task, TaskStatus


class AgentActionType(Enum):
    """
    Agent动作类型枚举
    
    定义Agent可以执行的不同类型的动作：
    - TOOL_USE: 工具调用
    - THINKING: 思考过程
    - FINAL_ANSWER: 最终答案
    """
    # 工具调用
    TOOL_USE = "tool_use"
    
    # 思考过程
    THINKING = "thinking"
    
    # 最终答案
    FINAL_ANSWER = "final_answer"


@dataclass
class ToolResult:
    """
    工具执行结果
    
    记录工具执行后的结果信息。
    
    属性：
    - tool_name: 工具名称
    - input_params: 传递给工具的参数
    - output: 工具输出
    - status: 执行状态（success/error）
    - error_message: 错误信息（如果失败）
    - execution_time: 执行时间（秒）
    """
    # 工具名称
    tool_name: str
    
    # 传递给工具的参数
    input_params: Dict[str, Any]
    
    # 工具输出
    output: Any
    
    # 执行状态
    status: str
    
    # 错误信息（如果失败）
    error_message: Optional[str] = None
    
    # 执行时间（秒）
    execution_time: float = 0.0


@dataclass
class AgentAction:
    """
    Agent动作
    
    记录Agent执行的一个动作，可以是工具调用、思考或最终答案。
    
    属性：
    - id: 动作唯一标识符
    - agent_id: 执行动作的Agent ID
    - agent_name: 执行动作的Agent名称
    - action_type: 动作类型
    - content: 动作内容
    - tool_result: 工具调用详情（如果是TOOL_USE类型）
    - timestamp: 执行时间戳
    """
    # Agent ID
    agent_id: str
    
    # Agent名称
    agent_name: str
    
    # 动作类型
    action_type: AgentActionType
    
    # 动作唯一标识符
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # 动作内容
    content: str = ""
    
    # 工具调用结果（如果是工具调用）
    tool_result: Optional[ToolResult] = None
    
    # 思考内容
    thought: Optional[str] = None
    
    # 执行时间戳
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentResult:
    """
    Agent执行结果
    
    记录Agent完整执行过程的结果。
    
    属性：
    - final_answer: Agent提供的最终答案
    - step_count: Agent执行的步数
    - status: 执行状态（success/error）
    - error_message: 错误信息（如果失败）
    """
    # 最终答案
    final_answer: str
    
    # 执行步数
    step_count: int
    
    # 执行状态
    status: str = "success"
    
    # 错误信息
    error_message: Optional[str] = None

    @classmethod
    def success(cls, final_answer: str, step_count: int) -> "AgentResult":
        """
        创建成功结果
        
        Args:
            final_answer: 最终答案
            step_count: 执行步数
            
        Returns:
            AgentResult: 成功状态的Result对象
        """
        return cls(final_answer=final_answer, step_count=step_count)

    @classmethod
    def error(cls, error_message: str, step_count: int = 0) -> "AgentResult":
        """
        创建错误结果
        
        Args:
            error_message: 错误信息
            step_count: 执行步数（默认0）
            
        Returns:
            AgentResult: 错误状态的Result对象
        """
        return cls(
            final_answer=f"Error: {error_message}",
            step_count=step_count,
            status="error",
            error_message=error_message
        )

    @property
    def is_error(self) -> bool:
        """
        检查结果是否表示错误
        
        Returns:
            如果是错误状态返回True
        """
        return self.status == "error"
