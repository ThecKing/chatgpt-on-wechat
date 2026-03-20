# -*- coding: utf-8 -*-
"""
事件系统模块

定义插件系统中的事件类型、事件动作和事件上下文类。
插件系统基于事件驱动架构，通过事件来协调各插件的处理流程。

事件流程：
1. 消息到达渠道（如微信、飞书）
2. Channel触发相应的事件（如ON_RECEIVE_MESSAGE）
3. PluginManager查找监听该事件的插件
4. 插件按优先级顺序执行
5. 插件可以修改上下文数据、拦截（BREAK）或放行（CONTINUE）

事件类型：
- ON_RECEIVE_MESSAGE: 收到消息时触发
- ON_HANDLE_CONTEXT: 处理消息前触发
- ON_DECORATE_REPLY: 得到回复后、发送前触发
- ON_SEND_REPLY: 发送回复前触发
"""

# 设置文件编码为UTF-8
# encoding:utf-8

# 导入枚举模块，定义事件类型和动作
from enum import Enum


class Event(Enum):
    """
    事件类型枚举
    
    定义插件系统支持的所有事件类型。
    每个事件在消息处理流程的不同阶段触发。
    """
    
    # 收到消息时触发
    # 触发时机：渠道收到用户消息，还未进行任何处理时
    # e_context 内容:
    #   - channel: 消息来源渠道对象
    #   - context: 本次消息的Context对象
    ON_RECEIVE_MESSAGE = 1
    
    # 处理消息前触发
    # 触发时机：即将调用AI模型生成回复之前
    # e_context 内容:
    #   - channel: 消息来源渠道对象
    #   - context: 本次消息的Context对象
    #   - reply: 目前的回复（初始为空，插件可以预设回复内容）
    ON_HANDLE_CONTEXT = 2
    
    # 得到回复后准备装饰时触发
    # 触发时机：AI生成回复后，添加@、前后缀等装饰之前
    # e_context 内容:
    #   - channel: 消息来源渠道对象
    #   - context: 本次消息的Context对象
    #   - reply: 目前的回复
    ON_DECORATE_REPLY = 3
    
    # 发送回复前触发
    # 触发时机：回复装饰完成后，即将发送给用户之前
    # e_context 内容:
    #   - channel: 消息来源渠道对象
    #   - context: 本次消息的Context对象
    #   - reply: 目前的回复
    ON_SEND_REPLY = 4
    
    # 发送回复后触发（目前已注释，未启用）
    # 触发时机：回复已发送给用户之后
    # AFTER_SEND_REPLY = 5


class EventAction(Enum):
    """
    事件动作枚举
    
    定义插件处理事件后可采取的动作。
    用于控制事件传播流程。
    """
    
    # 事件未结束，继续交给下个插件处理
    # 如果没有下个插件，则交付给默认的事件处理逻辑
    # 这是默认动作，表示插件放行让后续处理继续
    CONTINUE = 1
    
    # 事件结束，不再给下个插件处理
    # 但会交付给默认的事件处理逻辑
    # 通常用于插件处理了消息但不想让其他插件继续处理
    BREAK = 2
    
    # 事件结束，不再给下个插件处理
    # 也不交付给默认的事件处理逻辑
    # 通常用于完全拦截消息，不进行任何回复
    BREAK_PASS = 3


class EventContext:
    """
    事件上下文类
    
    封装事件相关的数据，在插件之间传递。
    继承自dict，可以像字典一样存取数据。
    
    属性说明：
    - event: 事件类型（Event枚举）
    - econtext: 事件上下文字典，存储事件相关数据
    - action: 事件动作（EventAction枚举），控制事件传播
    """
    
    def __init__(self, event, econtext=dict()):
        """
        初始化事件上下文
        
        Args:
            event: 事件类型（Event枚举值）
            econtext: 事件上下文字典，存储具体数据
        """
        # 保存事件类型
        self.event = event
        
        # 保存事件上下文字典
        self.econtext = econtext
        
        # 默认事件动作为CONTINUE（继续传播）
        self.action = EventAction.CONTINUE

    def __getitem__(self, key):
        """
        获取上下文中的值
        
        Args:
            key: 键名
            
        Returns:
            对应的值
        """
        return self.econtext[key]

    def __setitem__(self, key, value):
        """
        设置上下文中的值
        
        Args:
            key: 键名
            value: 要设置的值
        """
        self.econtext[key] = value

    def __delitem__(self, key):
        """
        删除上下文中的键值对
        
        Args:
            key: 要删除的键名
        """
        del self.econtext[key]

    def is_pass(self):
        """
        判断是否为PASS模式（拦截且不交付默认处理）
        
        当插件调用此方法返回True时，表示：
        - 事件不再传播给其他插件
        - 不会执行默认的处理逻辑
        
        Returns:
            bool: 是否为BREAK_PASS动作
        """
        return self.action == EventAction.BREAK_PASS

    def is_break(self):
        """
        判断是否为中断模式（BREAK或BREAK_PASS）
        
        当插件调用此方法返回True时，表示：
        - 事件不再传播给其他插件
        - BREAK: 会执行默认处理
        - BREAK_PASS: 不执行默认处理
        
        Returns:
            bool: 是否为BREAK或BREAK_PASS动作
        """
        return self.action == EventAction.BREAK or self.action == EventAction.BREAK_PASS
