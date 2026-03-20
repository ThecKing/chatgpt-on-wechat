# -*- coding: utf-8 -*-
"""
Dungeon插件 - 文字冒险游戏插件

功能：
- 和机器人一起玩文字冒险游戏
- 支持自定义故事背景
- 会话过期自动结束

指令：
$开始冒险 [背景故事] - 开始冒险游戏
$停止冒险 - 结束冒险游戏
"""

# 设置文件编码
# encoding:utf-8

# 导入插件系统
import plugins

# 导入桥接模块
from bridge.bridge import Bridge

# 导入上下文类型
from bridge.context import ContextType

# 导入回复类和类型
from bridge.reply import Reply, ReplyType

# 导入常量
from common import const

# 导入过期字典
from common.expired_dict import ExpiredDict

# 导入日志
from common.log import logger

# 导入配置
from config import conf

# 导入插件基类
from plugins import *


# 故事讲述者类
# https://github.com/bupticybee/ChineseAiDungeonChatGPT
class StoryTeller:
    """
    故事讲述者类
    
    管理单个用户的文字冒险游戏会话。
    """
    
    def __init__(self, bot, sessionid, story):
        """
        初始化故事讲述者
        
        Args:
            bot: Bot实例
            sessionid: 会话ID
            story: 故事背景
        """
        self.bot = bot
        self.sessionid = sessionid
        
        # 清除会话历史
        bot.sessions.clear_session(sessionid)
        
        # 是否是首次交互
        self.first_interact = True
        
        # 故事背景
        self.story = story

    def reset(self):
        """
        重置游戏
        """
        self.bot.sessions.clear_session(self.sessionid)
        self.first_interact = True

    def action(self, user_action):
        """
        执行游戏动作
        
        Args:
            user_action: 用户输入
            
        Returns:
            处理后的提示词
        """
        # 补全句号
        if user_action[-1] != "。":
            user_action = user_action + "。"
            
        # 首次交互
        if self.first_interact:
            prompt = (
                """现在来充当一个文字冒险游戏，描述时候注意节奏，不要太快，仔细描述各个人物的心情和周边环境。一次只需写四到六句话。
            开头是，"""
                + self.story
                + " "
                + user_action
            )
            self.first_interact = False
        else:
            # 后续交互
            prompt = """继续，一次只需要续写四到六句话，总共就只讲5分钟内发生的事情。""" + user_action
        return prompt


# 注册插件
@plugins.register(
    name="Dungeon",
    desire_priority=0,
    namecn="文字冒险",
    desc="A plugin to play dungeon game",
    version="1.0",
    author="lanvent",
)
class Dungeon(Plugin):
    """
    Dungeon插件类
    
    文字冒险游戏插件。
    """
    
    def __init__(self):
        """
        插件初始化
        """
        super().__init__()
        
        # 注册事件处理
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        logger.debug("[Dungeon] inited")
        
        # 游戏会话存储
        if conf().get("expires_in_seconds"):
            self.games = ExpiredDict(conf().get("expires_in_seconds"))
        else:
            self.games = dict()

    def on_handle_context(self, e_context: EventContext):
        """
        处理消息上下文事件
        
        Args:
            e_context: 事件上下文
        """
        # 只处理文本消息
        if e_context["context"].type != ContextType.TEXT:
            return
            
        # 检查Bot类型
        bottype = Bridge().get_bot_type("chat")
        if bottype not in [const.OPEN_AI, const.OPENAI, const.CHATGPT, const.CHATGPTONAZURE, const.LINKAI]:
            return
            
        # 获取Bot
        bot = Bridge().get_bot("chat")
        
        # 获取消息内容
        content = e_context["context"].content[:]
        clist = e_context["context"].content.split(maxsplit=1)
        sessionid = e_context["context"]["session_id"]
        
        logger.debug("[Dungeon] on_handle_context. content: %s" % clist)
        
        trigger_prefix = conf().get("plugin_trigger_prefix", "$")
        
        # ========== 停止冒险 ==========
        if clist[0] == f"{trigger_prefix}停止冒险":
            if sessionid in self.games:
                self.games[sessionid].reset()
                del self.games[sessionid]
                reply = Reply(ReplyType.INFO, "冒险结束!")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                
        # ========== 开始冒险 或 继续冒险 ==========
        elif clist[0] == f"{trigger_prefix}开始冒险" or sessionid in self.games:
            # 第一次开始或重新开始
            if sessionid not in self.games or clist[0] == f"{trigger_prefix}开始冒险":
                # 获取故事背景
                if len(clist) > 1:
                    story = clist[1]
                else:
                    story = "你在树林里冒险，指不定会从哪里蹦出来一些奇怪的东西，你握紧手上的手枪，希望这次冒险能够找到一些值钱的东西，你往树林深处走去。"
                    
                # 创建游戏
                self.games[sessionid] = StoryTeller(bot, sessionid, story)
                reply = Reply(ReplyType.INFO, "冒险开始，你可以输入任意内容，让故事继续下去。故事背景是：" + story)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                # 继续冒险
                prompt = self.games[sessionid].action(content)
                e_context["context"].type = ContextType.TEXT
                e_context["context"].content = prompt
                e_context.action = EventAction.BREAK

    def get_help_text(self, **kwargs):
        """
        获取帮助文本
        
        Returns:
            str: 帮助信息
        """
        help_text = "可以和机器人一起玩文字冒险游戏。\n"
        if kwargs.get("verbose") != True:
            return help_text
        trigger_prefix = conf().get("plugin_trigger_prefix", "$")
        help_text = f"{trigger_prefix}开始冒险 " + "背景故事: 开始一个基于{背景故事}的文字冒险，之后你的所有消息会协助完善这个故事。\n"
        help_text += f"{trigger_prefix}停止冒险: 结束游戏。\n"
        if kwargs.get("verbose") == True:
            help_text += f"\n命令例子: '{trigger_prefix}开始冒险 你在树林里冒险，指不定会从哪里蹦出来一些奇怪的东西，你握紧手上的手枪，希望这次冒险能够找到一些值钱的东西，你往树林深处走去。'"
        return help_text
