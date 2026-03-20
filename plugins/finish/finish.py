# -*- coding: utf-8 -*-
"""
Finish插件 - 未知命令处理插件

功能：
- 当所有其他插件都不处理某指令时，最后处理
- 显示"未知插件命令"提示
- 优先级最低，确保最后执行

注意：
- 优先级设为-999，确保最后执行
- 隐藏插件，不在列表中显示
"""

# 设置文件编码
# encoding:utf-8

# 导入插件系统
import plugins

# 导入上下文类型
from bridge.context import ContextType

# 导入回复类和类型
from bridge.reply import Reply, ReplyType

# 导入日志
from common.log import logger

# 导入配置
from config import conf

# 导入插件基类
from plugins import *


# 注册插件
# 优先级设为最低，确保最后执行
@plugins.register(
    name="Finish",
    desire_priority=-999,  # 最低优先级
    hidden=True,  # 隐藏
    desc="A plugin that check unknown command",
    version="1.0",
    author="js00000",
)
class Finish(Plugin):
    """
    Finish插件类
    
    未知命令处理插件，当其他插件都不处理时显示提示。
    """
    
    def __init__(self):
        """
        插件初始化
        """
        super().__init__()
        
        # 注册事件处理
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        logger.debug("[Finish] inited")

    def on_handle_context(self, e_context: EventContext):
        """
        处理消息上下文事件
        
        检查是否是未知插件命令。
        
        Args:
            e_context: 事件上下文
        """
        # 只处理文本消息
        if e_context["context"].type != ContextType.TEXT:
            return

        # 获取消息内容
        content = e_context["context"].content
        logger.debug("[Finish] on_handle_context. content: %s" % content)
        
        # 获取触发前缀
        trigger_prefix = conf().get("plugin_trigger_prefix", "$")
        
        # 如果消息以触发前缀开头，说明是未处理的插件命令
        if content.startswith(trigger_prefix):
            # 创建错误回复
            reply = Reply()
            reply.type = ReplyType.ERROR
            reply.content = "未知插件命令\n查看插件命令列表请输入#help 插件名\n"
            
            # 设置回复
            e_context["reply"] = reply
            
            # 中断事件，不继续处理
            e_context.action = EventAction.BREAK_PASS

    def get_help_text(self, **kwargs):
        """
        获取帮助文本
        
        Returns:
            str: 帮助信息（空，因为是隐藏插件）
        """
        return ""
