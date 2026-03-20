# -*- coding: utf-8 -*-
"""
Agent协议模块 - 上下文定义

定义多Agent协作的上下文类型：
- TeamContext: 团队上下文（包含多个Agent的协作信息）
- AgentOutput: Agent输出记录
"""


class TeamContext:
    """
    团队上下文类
    
    用于多Agent协作场景，管理一组Agent的共同上下文信息。
    
    属性说明：
    - name: 团队名称
    - description: 团队描述
    - rule: 协作规则
    - agents: Agent列表
    - user_task: 用户任务（向后兼容）
    - task: 任务实例
    - model: LLM模型实例
    - task_short_name: 任务目录简称
    - agent_outputs: 已执行Agent的输出列表
    - current_steps: 当前执行步数
    - max_steps: 最大执行步数
    """
    
    def __init__(self, name: str, description: str, rule: str, agents: list, max_steps: int = 100):
        """
        初始化团队上下文
        
        Args:
            name: 团队名称
            description: 团队描述
            rule: 协作规则
            agents: Agent列表
            max_steps: 最大执行步数（默认100）
        """
        # 团队名称
        self.name = name
        # 团队描述
        self.description = description
        # 协作规则
        self.rule = rule
        # Agent列表
        self.agents = agents
        # 用户任务（向后兼容字段）
        self.user_task = ""
        # 任务实例（Task对象）
        self.task = None
        # LLM模型实例
        self.model = None
        # 任务目录简称
        self.task_short_name = None
        # 已执行Agent的输出列表
        self.agent_outputs: list = []
        # 当前执行步数
        self.current_steps = 0
        # 最大执行步数
        self.max_steps = max_steps


class AgentOutput:
    """
    Agent输出记录类
    
    记录单个Agent的执行输出。
    
    属性说明：
    - agent_name: Agent名称
    - output: 输出内容
    """
    
    def __init__(self, agent_name: str, output: str):
        """
        初始化Agent输出记录
        
        Args:
            agent_name: Agent名称
            output: 输出内容
        """
        # Agent名称
        self.agent_name = agent_name
        # 输出内容
        self.output = output
