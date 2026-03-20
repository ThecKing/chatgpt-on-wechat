# -*- coding: utf-8 -*-
"""
Banwords插件 - 敏感词过滤插件

功能：
- 检测消息中是否包含敏感词
- 可以选择忽略消息或替换敏感词
- 也可检测AI回复中的敏感词

配置文件 (config.json)：
{
    "action": "ignore",  // 对敏感词的处理方式：ignore(忽略) 或 replace(替换)
    "reply_filter": true,  // 是否检测AI回复中的敏感词
    "reply_action": "ignore"  // 回复敏感词处理方式
}

敏感词列表 (banwords.txt)：
每行一个敏感词
"""

# 设置文件编码
# encoding:utf-8

# 导入JSON模块
import json

# 导入操作系统模块
import os

# 导入插件系统
import plugins

# 导入上下文类型
from bridge.context import ContextType

# 导入回复类和类型
from bridge.reply import Reply, ReplyType

# 导入日志模块
from common.log import logger

# 导入插件基类
from plugins import *

# 导入敏感词搜索工具
from .lib.WordsSearch import WordsSearch


# 注册插件
@plugins.register(
    name="Banwords",
    desire_priority=100,  # 较高优先级
    hidden=True,
    desc="判断消息中是否有敏感词、决定是否回复。",
    version="1.0",
    author="lanvent",
)
class Banwords(Plugin):
    """
    Banwords插件类
    
    敏感词过滤插件，用于检测消息和回复中的敏感词。
    """
    
    def __init__(self):
        """
        插件初始化
        
        加载敏感词列表，配置处理方式。
        """
        # 调用父类初始化
        super().__init__()
        
        try:
            # 加载配置
            conf = super().load_config()
            curdir = os.path.dirname(__file__)
            
            # 如果配置不存在，创建默认配置
            if not conf:
                config_path = os.path.join(curdir, "config.json")
                if not os.path.exists(config_path):
                    conf = {"action": "ignore"}
                    with open(config_path, "w") as f:
                        json.dump(conf, f, indent=4)

            # 创建敏感词搜索器
            self.searchr = WordsSearch()
            
            # 获取处理动作
            self.action = conf["action"]
            
            # 读取敏感词列表
            banwords_path = os.path.join(curdir, "banwords.txt")
            with open(banwords_path, "r", encoding="utf-8") as f:
                words = []
                for line in f:
                    word = line.strip()
                    if word:
                        words.append(word)
                        
            # 设置敏感词
            self.searchr.SetKeywords(words)
            
            # 注册事件处理函数
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            
            # 如果配置启用回复过滤
            if conf.get("reply_filter", True):
                self.handlers[Event.ON_DECORATE_REPLY] = self.on_decorate_reply
                self.reply_action = conf.get("reply_action", "ignore")
                
            logger.debug("[Banwords] inited")
            
        except Exception as e:
            logger.debug("[Banwords] init failed, ignore or see https://github.com/zhayujie/chatgpt-on-wechat/tree/master/plugins/banwords .")
            raise e

    def on_handle_context(self, e_context: EventContext):
        """
        处理消息上下文事件
        
        检测用户消息中是否包含敏感词。
        
        Args:
            e_context: 事件上下文
        """
        # 只处理文本和图片生成消息
        if e_context["context"].type not in [
            ContextType.TEXT,
            ContextType.IMAGE_CREATE,
        ]:
            return

        # 获取消息内容
        content = e_context["context"].content
        logger.debug("[Banwords] on_handle_context. content: %s" % content)
        
        # 根据配置的动作处理
        if self.action == "ignore":
            # 忽略模式：检测到敏感词则不回复
            f = self.searchr.FindFirst(content)
            if f:
                logger.info("[Banwords] %s in message" % f["Keyword"])
                e_context.action = EventAction.BREAK_PASS
                return
                
        elif self.action == "replace":
            # 替换模式：替换敏感词
            if self.searchr.ContainsAny(content):
                reply = Reply(ReplyType.INFO, "发言中包含敏感词，请重试: \n" + self.searchr.Replace(content))
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return

    def on_decorate_reply(self, e_context: EventContext):
        """
        装饰回复事件
        
        检测AI回复中是否包含敏感词。
        
        Args:
            e_context: 事件上下文
        """
        # 只处理文本回复
        if e_context["reply"].type not in [ReplyType.TEXT]:
            return

        # 获取回复内容
        reply = e_context["reply"]
        content = reply.content
        
        # 根据配置的动作处理
        if self.reply_action == "ignore":
            # 忽略模式：不发送包含敏感词的回复
            f = self.searchr.FindFirst(content)
            if f:
                logger.info("[Banwords] %s in reply" % f["Keyword"])
                e_context["reply"] = None
                e_context.action = EventAction.BREAK_PASS
                return
                
        elif self.reply_action == "replace":
            # 替换模式：替换回复中的敏感词
            if self.searchr.ContainsAny(content):
                reply = Reply(ReplyType.INFO, "已替换回复中的敏感词: \n" + self.searchr.Replace(content))
                e_context["reply"] = reply
                e_context.action = EventAction.CONTINUE
                return

    def get_help_text(self, **kwargs):
        """
        获取帮助文本
        
        Returns:
            str: 帮助信息
        """
        return "过滤消息中的敏感词。"
