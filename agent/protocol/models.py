# -*- coding: utf-8 -*-
"""
Agent协议模块 - 模型定义

提供Agent系统所需的基础模型类：
- LLMRequest: LLM请求封装
- LLMModel: LLM模型基类
- ModelFactory: 模型工厂

这些类用于工具系统和桥接集成。
"""

# 导入类型提示
from typing import Any, Dict, List, Optional


class LLMRequest:
    """
    LLM请求模型类
    
    封装发送给LLM API的请求参数。
    
    属性说明：
    - messages: 消息列表
    - model: 模型名称
    - temperature: 温度参数（控制随机性）
    - max_tokens: 最大生成token数
    - stream: 是否流式输出
    - tools: 工具定义列表
    """
    
    def __init__(self, messages: List[Dict[str, str]] = None, model: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: Optional[int] = None, 
                 stream: bool = False, tools: Optional[List] = None, **kwargs):
        """
        初始化LLM请求
        
        Args:
            messages: 消息列表，每条消息为 {"role": "user/assistant/system", "content": "..."}
            model: 模型名称
            temperature: 温度参数（0-2），越高越随机
            max_tokens: 最大生成token数
            stream: 是否流式输出
            tools: 工具定义列表
            **kwargs: 其他额外参数
        """
        self.messages = messages or []  # 消息列表
        self.model = model  # 模型名称
        self.temperature = temperature  # 温度参数
        self.max_tokens = max_tokens  # 最大token数
        self.stream = stream  # 流式输出标志
        self.tools = tools  # 工具列表
        
        # 允许额外的属性
        for key, value in kwargs.items():
            setattr(self, key, value)


class LLMModel:
    """
    LLM模型基类
    
    所有LLM模型适配器都应该继承此类。
    定义了call和call_stream两个核心方法。
    
    子类需要实现：
    - call(): 非流式调用
    - call_stream(): 流式调用
    """
    
    def __init__(self, model: str = None, **kwargs):
        """
        初始化LLM模型
        
        Args:
            model: 模型名称
            **kwargs: 其他配置参数
        """
        self.model = model  # 模型名称
        self.config = kwargs  # 配置字典
    
    def call(self, request: LLMRequest):
        """
        非流式调用模型
        
        Args:
            request: LLMRequest请求对象
            
        Returns:
            模型的响应结果
        """
        # 占位实现，子类需要重写
        raise NotImplementedError("LLMModel.call not implemented in this context")
    
    def call_stream(self, request: LLMRequest):
        """
        流式调用模型
        
        Args:
            request: LLMRequest请求对象
            
        Yields:
            模型的流式响应块
        """
        # 占位实现，子类需要重写
        raise NotImplementedError("LLMModel.call_stream not implemented in this context")


class ModelFactory:
    """
    模型工厂类
    
    根据模型类型创建相应的模型实例。
    这是一个占位实现，实际使用由bridge层创建。
    """
    
    @staticmethod
    def create_model(model_type: str, **kwargs):
        """
        根据类型创建模型实例
        
        Args:
            model_type: 模型类型标识
            **kwargs: 创建参数
            
        Returns:
            LLMModel实例
        """
        # 占位实现
        raise NotImplementedError("ModelFactory.create_model not implemented in this context")
