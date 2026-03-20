# -*- coding: utf-8 -*-
"""
插件系统初始化模块

该模块导出插件系统的核心类和函数：
- Event: 事件类型枚举
- EventAction: 事件动作枚举
- EventContext: 事件上下文类
- Plugin: 插件基类
- PluginManager: 插件管理器
- register: 插件注册装饰器

同时创建全局唯一的PluginManager单例实例。
"""

# 导入事件相关类：Event枚举、EventAction枚举、EventContext类
from .event import *

# 导入插件基类：Plugin
from .plugin import *

# 导入插件管理器类
from .plugin_manager import PluginManager

# 创建全局唯一的PluginManager单例实例
# 这是整个插件系统的核心管理器
instance = PluginManager()

# 创建register装饰器快捷引用
# 用于插件注册：@register("插件名", 优先级)
# 等价于 instance.register
register = instance.register

# 下面是被注释掉的旧API，保持兼容性
# load_plugins = instance.load_plugins
# emit_event = instance.emit_event
