# -*- coding: utf-8 -*-
"""
插件基类模块

定义所有插件的基类Plugin。
插件开发者需要继承此类并实现相应的事件处理方法。

主要功能：
1. 加载插件配置（支持全局配置和插件私有配置）
2. 保存插件配置
3. 获取帮助文本
4. 定义事件处理方法（由子类实现）

配置加载优先级：
1. plugins/config.json（全局配置）
2. 插件目录下的config.json（私有配置）
"""

# 导入操作系统模块，用于文件路径操作
import os

# 导入JSON模块，用于读写配置文件
import json

# 导入配置相关函数：
# pconf(): 获取插件配置
# plugin_config(): 获取插件配置字典
# conf(): 获取全局配置
# write_plugin_config(): 写入插件配置
from config import pconf, plugin_config, conf, write_plugin_config

# 导入日志模块
from common.log import logger


class Plugin:
    """
    插件基类
    
    所有插件都应该继承这个类。
    插件可以监听和处理各种事件来介入消息处理流程。
    
    属性（由PluginManager在注册时设置）：
    - name: 插件名称
    - priority: 插件优先级
    - desc: 插件描述
    - author: 插件作者
    - path: 插件路径
    - version: 插件版本
    - namecn: 插件中文名
    - hidden: 是否隐藏
    - enabled: 是否启用
    
    子类需要实现的方法：
    - on_receive_message(): 收到消息时调用
    - on_handle_context(): 处理消息前调用
    - on_decorate_reply(): 装饰回复前调用
    - on_send_reply(): 发送回复前调用
    """
    
    def __init__(self):
        """
        插件初始化方法
        
        子类应该调用super().__init__()
        初始化handlers字典用于注册事件处理函数
        """
        # 初始化事件处理函数字典
        # key: 事件类型(Event枚举), value: 处理函数
        self.handlers = {}

    def load_config(self) -> dict:
        """
        加载当前插件配置
        
        配置加载优先级：
        1. plugins/config.json 中的全局配置
        2. 插件目录下的 config.json
        
        Returns:
            dict: 插件配置字典
        """
        # 优先从全局配置中获取插件配置
        # pconf() 函数会先查找 plugins/config.json
        plugin_conf = pconf(self.name)
        
        # 如果全局配置不存在
        if not plugin_conf:
            # 查找插件目录下的私有配置文件
            plugin_config_path = os.path.join(self.path, "config.json")
            
            # 检查配置文件是否存在
            if os.path.exists(plugin_config_path):
                # 读取私有配置
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)

                # 将私有配置写入全局配置内存
                # 这样后续可以直接从pconf()获取
                write_plugin_config({self.name: plugin_conf})
                
        return plugin_conf

    def save_config(self, config: dict):
        """
        保存插件配置
        
        会同时写入两个位置：
        1. plugins/config.json（全局配置）
        2. 插件目录下的 config.json（私有配置）
        
        Args:
            config: 要保存的配置字典
        """
        try:
            # 写入全局配置内存
            write_plugin_config({self.name: config})
            
            # 写入全局配置文件
            global_config_path = "./plugins/config.json"
            if os.path.exists(global_config_path):
                with open(global_config_path, "w", encoding='utf-8') as f:
                    # plugin_config 是全局配置字典
                    json.dump(plugin_config, f, indent=4, ensure_ascii=False)
                    
            # 写入插件私有配置文件
            plugin_config_path = os.path.join(self.path, "config.json")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "w", encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)

        except Exception as e:
            # 保存配置失败，记录警告日志
            logger.warn("save plugin config failed: {}".format(e))

    def get_help_text(self, **kwargs):
        """
        获取插件帮助文本
        
        当用户发送帮助命令时显示。
        子类可以覆盖此方法提供自定义帮助信息。
        
        Args:
            **kwargs: 额外参数，可用于定制化输出
            
        Returns:
            str: 帮助文本
        """
        # 默认返回的提示信息
        return "暂无帮助信息"

    def reload(self):
        """
        插件重载回调
        
        当插件被重载时调用。
        子类可以覆盖此方法实现重载时的清理或初始化工作。
        """
        # 默认空实现
        pass
