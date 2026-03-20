# -*- coding: utf-8 -*-
"""
Keyword插件 - 关键词自动回复插件

功能：
- 配置关键词及对应的回复内容
- 支持文本、图片、文件、视频等多种回复类型
- 当用户消息匹配关键词时，返回预设的回复

配置示例 (config.json)：
{
    "keyword": {
        "hello": "你好！",
        "图片": "https://example.com/image.jpg",
        "文件": "https://example.com/document.pdf"
    }
}
"""

# 设置文件编码
# encoding:utf-8

# 导入JSON模块，用于读写配置文件
import json

# 导入操作系统模块，用于文件路径操作
import os

# 导入HTTP请求模块，用于下载文件
import requests

# 导入插件系统模块
import plugins

# 导入上下文类型枚举
from bridge.context import ContextType

# 导入回复类和回复类型
from bridge.reply import Reply, ReplyType

# 导入日志模块
from common.log import logger

# 导入插件系统
from plugins import *


# 注册插件
# name: 插件名称
# desire_priority: 优先级，900表示较高优先级
# hidden: 隐藏，不在插件列表显示
# desc: 插件描述
# version: 版本
# author: 作者
@plugins.register(
    name="Keyword",
    desire_priority=900,
    hidden=True,
    desc="关键词匹配过滤",
    version="0.1",
    author="fengyege.top",
)
class Keyword(Plugin):
    """
    Keyword插件类
    
    监听消息，当消息匹配到配置的关键词时，返回预设的回复。
    """

    def __init__(self):
        """
        插件初始化
        
        加载关键词配置文件。
        """
        # 调用父类初始化
        super().__init__()
        
        try:
            # 获取当前插件目录
            curdir = os.path.dirname(__file__)
            
            # 配置文件路径
            config_path = os.path.join(curdir, "config.json")
            
            # 初始化配置
            conf = None
            
            # 如果配置文件不存在，创建默认配置
            if not os.path.exists(config_path):
                logger.debug(f"[keyword]不存在配置文件{config_path}")
                conf = {"keyword": {}}
                # 创建默认配置文件
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(conf, f, indent=4)
            else:
                # 加载配置文件
                logger.debug(f"[keyword]加载配置文件{config_path}")
                with open(config_path, "r", encoding="utf-8") as f:
                    conf = json.load(f)
                    
            # 提取关键词配置
            self.keyword = conf["keyword"]

            # 记录调试日志
            logger.debug("[keyword] {}".format(self.keyword))
            
            # 注册事件处理函数
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            logger.debug("[keyword] inited.")
            
        except Exception as e:
            # 初始化失败，记录警告
            logger.warn("[keyword] init failed, ignore or see https://github.com/zhayujie/chatgpt-on-wechat/tree/master/plugins/keyword .")
            raise e

    def on_handle_context(self, e_context: EventContext):
        """
        处理消息上下文事件
        
        检查消息内容是否匹配关键词，如果匹配则返回预设回复。
        
        Args:
            e_context: 事件上下文
        """
        # 只处理文本消息
        if e_context["context"].type != ContextType.TEXT:
            return

        # 获取消息内容并去除首尾空白
        content = e_context["context"].content.strip()
        
        logger.debug("[keyword] on_handle_context. content: %s" % content)
        
        # 检查是否匹配关键词
        if content in self.keyword:
            logger.info(f"[keyword] 匹配到关键字【{content}】")
            
            # 获取预设的回复内容
            reply_text = self.keyword[content]

            # ========== 判断回复类型 ==========
            
            # 判断是否为图片URL
            # 条件：以http://或https://开头，以图片扩展名结尾
            if (reply_text.startswith("http://") or reply_text.startswith("https://")) and any(reply_text.endswith(ext) for ext in [".jpg", ".webp", ".jpeg", ".png", ".gif", ".img"]):
                # 创建图片回复
                reply = Reply()
                reply.type = ReplyType.IMAGE_URL
                reply.content = reply_text
                
            # 判断是否为文件URL
            # 条件：以http://或https://开头，以文件扩展名结尾
            elif (reply_text.startswith("http://") or reply_text.startswith("https://")) and any(reply_text.endswith(ext) for ext in [".pdf", ".doc", ".docx", ".xls", "xlsx",".zip", ".rar"]):
                # 创建临时目录
                file_path = "tmp"
                if not os.path.exists(file_path):
                    os.makedirs(file_path)
                    
                # 从URL中提取文件名
                file_name = reply_text.split("/")[-1]
                file_path = os.path.join(file_path, file_name)
                
                # 下载文件
                response = requests.get(reply_text)
                with open(file_path, "wb") as f:
                    f.write(response.content)
                    
                # 创建文件回复
                reply = Reply()
                reply.type = ReplyType.FILE
                reply.content = file_path
            
            # 判断是否为视频URL
            # 条件：以http://或https://开头，以.mp4结尾
            elif (reply_text.startswith("http://") or reply_text.startswith("https://")) and any(reply_text.endswith(ext) for ext in [".mp4"]):
                # 创建视频回复
                reply = Reply()
                reply.type = ReplyType.VIDEO_URL
                reply.content = reply_text
                
            # 默认：文本回复
            else:
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = reply_text
            
            # 设置回复到上下文
            e_context["reply"] = reply
            
            # BREAK_PASS: 事件结束，跳过默认处理逻辑
            # 直接发送预设的回复，不调用AI
            e_context.action = EventAction.BREAK_PASS
            
    def get_help_text(self, **kwargs):
        """
        获取帮助文本
        
        Returns:
            str: 帮助信息
        """
        help_text = "关键词过滤"
        return help_text
