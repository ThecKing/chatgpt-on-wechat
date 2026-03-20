# -*- coding: utf-8 -*-
"""
Agent 协议数据模型模块

定义Agent系统中使用的数据模型：
1. LLMRequest: LLM请求模型
2. LLMModel: LLM模型基类
3. ModelFactory: 模型工厂类

这些是Agent系统与各种LLM（OpenAI、Claude、Gemini等）交互的基础数据模型。
"""

# 导入类型提示
from typing import Any, Dict, List, Optional


class LLMRequest:
    """
    LLM请求模型
    
    封装发送给LLM API的请求参数。
    """
    
    def __init__(self, messages: List[Dict[str, str]] = None, model: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: Optional[int] = None, 
                 stream: bool = False, tools: Optional[List] = None, **kwargs):
        """
        初始化LLM请求
        
        Args:
            messages: 消息列表，每条消息包含role和content
            model: 模型名称（如gpt-4、claude-3-opus等）
            temperature: 温度参数，控制随机性（0-2）
            max_tokens: 最大生成Token数
            stream: 是否流式输出
            tools: 工具定义列表（用于Function Calling）
            **kwargs: 其他额外参数
        """
        # 消息列表
        self.messages = messages or []
        
        # 模型名称
        self.model = model
        
        # 温度参数
        self.temperature = temperature
        
        # 最大Token数
        self.max_tokens = max_tokens
        
        # 是否流式输出
        self.stream = stream
        
        # 工具定义
        self.tools = tools
        
        # 允许额外属性
        for key, value in kwargs.items():
            setattr(self, key, value)


class LLMModel:
    """
    LLM模型基类
    
    所有具体LLM模型（如OpenAIModel、ClaudeModel等）都应继承此类。
    """
    
    def __init__(self, model: str = None, **kwargs):
        """
        初始化LLM模型
        
        Args:
            model: 模型名称
            **kwargs: 其他配置参数（如API密钥、base_url等）
        """
        self.model = model
        self.config = kwargs
    
    def call(self, request: LLMRequest):
        """
        调用模型（非流式）
        
        Args:
            request: LLMRequest请求对象
            
        Returns:
            模型响应
            
        Raises:
            NotImplementedError: 占位实现，子类必须实现
        """
        raise NotImplementedError("LLMModel.call not implemented in this context")
    
    def call_stream(self, request: LLMRequest):
        """
        流式调用模型
        
        Args:
            request: LLMRequest请求对象
            
        Returns:
            流式响应迭代器
            
        Raises:
            NotImplementedError: 占位实现，子类必须实现
        """
        raise NotImplementedError("LLMModel.call_stream not implemented in this context")


class ModelFactory:
    """
    模型工厂类
    
    用于根据类型创建对应的LLM模型实例。
    """
    
    @staticmethod
    def create_model(model_type: str, **kwargs):
        """
        根据类型创建模型实例
        
        Args:
            model_type: 模型类型标识（如"openai"、"claude"等）
            **kwargs: 模型配置参数
            
        Returns:
            对应的模型实例
            
        Raises:
            NotImplementedError: 占位实现
        """
        raise NotImplementedError("ModelFactory.create_model not implemented in this context")
