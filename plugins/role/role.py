# -*- coding: utf-8 -*-
"""
Role插件 - 角色扮演插件

功能：
- 为机器人设置预设角色
- 支持自定义角色设定
- 按角色类型查看角色列表
- 停止扮演

配置示例 (roles.json)：
{
    "tags": {"写作": "写作相关角色"},
    "roles": [
        {"title": "写作助理", "tags": ["写作"], "descn": "你是一个写作助理...", "remark": "帮助写作"}
    ]
}

指令：
$角色 角色名 - 设置角色
$role 角色名 - 英文设置角色
$设定扮演 角色设定 - 自定义角色
$停止扮演 - 停止角色扮演
$角色类型 - 查看角色类型
"""

# 设置文件编码
# encoding:utf-8

# 导入JSON模块
import json

# 导入操作系统模块
import os

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

# 导入日志
from common.log import logger

# 导入配置
from config import conf

# 导入插件系统
from plugins import *


class RolePlay:
    """
    角色扮演会话类
    
    管理单个用户的角色扮演会话。
    """
    
    def __init__(self, bot, sessionid, desc, wrapper=None):
        """
        初始化角色扮演会话
        
        Args:
            bot: Bot实例
            sessionid: 会话ID
            desc: 角色描述/设定
            wrapper: 用户输入包装格式
        """
        self.bot = bot
        self.sessionid = sessionid
        # 用于包装用户输入，默认 "%s"
        self.wrapper = wrapper or "%s"
        self.desc = desc
        
        # 创建会话并设置系统提示词
        self.bot.sessions.build_session(self.sessionid, system_prompt=self.desc)

    def reset(self):
        """
        重置角色扮演会话
        """
        self.bot.sessions.clear_session(self.sessionid)

    def action(self, user_action):
        """
        执行角色扮演
        
        Args:
            user_action: 用户输入
            
        Returns:
            处理后的提示词
        """
        # 获取或创建会话
        session = self.bot.sessions.build_session(self.sessionid)
        
        # 检查系统提示词是否被修改，必要时重置
        if session.system_prompt != self.desc:
            session.set_system_prompt(self.desc)
            
        # 包装用户输入
        prompt = self.wrapper % user_action
        return prompt


# 注册插件
@plugins.register(
    name="Role",
    desire_priority=0,
    namecn="角色扮演",
    desc="为你的Bot设置预设角色",
    version="1.0",
    author="lanvent",
)
class Role(Plugin):
    """
    Role插件类
    
    角色扮演插件，允许用户设置机器人的角色。
    """
    
    def __init__(self):
        """
        插件初始化
        
        加载角色配置文件。
        """
        # 调用父类初始化
        super().__init__()
        
        # 获取配置路径
        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "roles.json")
        
        try:
            # 读取角色配置
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                
            # 解析标签
            self.tags = {tag: (desc, []) for tag, desc in config["tags"].items()}
            self.roles = {}
            
            # 解析角色
            for role in config["roles"]:
                self.roles[role["title"].lower()] = role
                for tag in role["tags"]:
                    if tag not in self.tags:
                        logger.warning(f"[Role] unknown tag {tag} ")
                        self.tags[tag] = (tag, [])
                    self.tags[tag][1].append(role)
                    
            # 清理空标签
            for tag in list(self.tags.keys()):
                if len(self.tags[tag][1]) == 0:
                    logger.debug(f"[Role] no role found for tag {tag} ")
                    del self.tags[tag]

            # 检查是否有角色
            if len(self.roles) == 0:
                raise Exception("no role found")
                
            # 注册事件处理
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            self.roleplays = {}
            logger.debug("[Role] inited")
            
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                logger.warn(f"[Role] init failed, {config_path} not found, ignore or see https://github.com/zhayujie/chatgpt-on-wechat/tree/master/plugins/role .")
            else:
                logger.warn("[Role] init failed, ignore or see https://github.com/zhayujie/chatgpt-on-wechat/tree/master/plugins/role .")
            raise e

    def get_role(self, name, find_closest=True, min_sim=0.35):
        """
        获取角色
        
        Args:
            name: 角色名
            find_closest: 是否模糊匹配
            min_sim: 最小相似度
            
        Returns:
            角色名或None
        """
        name = name.lower()
        found_role = None
        
        # 精确匹配
        if name in self.roles:
            found_role = name
        # 模糊匹配
        elif find_closest:
            import difflib

            def str_simularity(a, b):
                return difflib.SequenceMatcher(None, a, b).ratio()

            max_sim = min_sim
            max_role = None
            for role in self.roles:
                sim = str_simularity(name, role)
                if sim >= max_sim:
                    max_sim = sim
                    max_role = role
            found_role = max_role
        return found_role

    def on_handle_context(self, e_context: EventContext):
        """
        处理消息上下文事件
        
        Args:
            e_context: 事件上下文
        """
        # 只处理文本消息
        if e_context["context"].type != ContextType.TEXT:
            return
            
        # 检查Bot类型是否支持
        btype = Bridge().get_bot_type("chat")
        if btype not in [const.OPEN_AI, const.OPENAI, const.CHATGPT, const.CHATGPTONAZURE, const.QWEN_DASHSCOPE, const.XUNFEI, const.BAIDU, const.ZHIPU_AI, const.MOONSHOT, const.MiniMax, const.LINKAI, const.MODELSCOPE]:
            logger.debug(f'不支持的bot: {btype}')
            return
            
        # 获取Bot
        bot = Bridge().get_bot("chat")
        
        # 获取消息内容
        content = e_context["context"].content[:]
        clist = e_context["context"].content.split(maxsplit=1)
        
        desckey = None
        customize = False
        sessionid = e_context["context"]["session_id"]
        trigger_prefix = conf().get("plugin_trigger_prefix", "$")
        
        # ========== 处理各种指令 ==========
        
        # 停止扮演
        if clist[0] == f"{trigger_prefix}停止扮演":
            if sessionid in self.roleplays:
                self.roleplays[sessionid].reset()
                del self.roleplays[sessionid]
            reply = Reply(ReplyType.INFO, "角色扮演结束!")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return
            
        # 角色指令（中文）
        elif clist[0] == f"{trigger_prefix}角色":
            desckey = "descn"
            
        # 角色指令（英文）
        elif clist[0].lower() == f"{trigger_prefix}role":
            desckey = "description"
            
        # 自定义角色设定
        elif clist[0] == f"{trigger_prefix}设定扮演":
            customize = True
            
        # 角色类型列表
        elif clist[0] == f"{trigger_prefix}角色类型":
            if len(clist) > 1:
                tag = clist[1].strip()
                help_text = "角色列表：\n"
                for key, value in self.tags.items():
                    if value[0] == tag:
                        tag = key
                        break
                if tag == "所有":
                    for role in self.roles.values():
                        help_text += f"{role['title']}: {role['remark']}\n"
                elif tag in self.tags:
                    for role in self.tags[tag][1]:
                        help_text += f"{role['title']}: {role['remark']}\n"
                else:
                    help_text = f"未知角色类型。\n"
                    help_text += "目前的角色类型有: \n"
                    help_text += "，".join([self.tags[tag][0] for tag in self.tags]) + "\n"
            else:
                help_text = f"请输入角色类型。\n"
                help_text += "目前的角色类型有: \n"
                help_text += "，".join([self.tags[tag][0] for tag in self.tags]) + "\n"
            reply = Reply(ReplyType.INFO, help_text)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return
            
        # 如果没有角色扮演会话，直接返回
        elif sessionid not in self.roleplays:
            return
            
        logger.debug("[Role] on_handle_context. content: %s" % content)
        
        # 设置角色
        if desckey is not None:
            if len(clist) == 1 or (len(clist) > 1 and clist[1].lower() in ["help", "帮助"]):
                reply = Reply(ReplyType.INFO, self.get_help_text(verbose=True))
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            role = self.get_role(clist[1])
            if role is None:
                reply = Reply(ReplyType.ERROR, "角色不存在")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            else:
                self.roleplays[sessionid] = RolePlay(
                    bot,
                    sessionid,
                    self.roles[role][desckey],
                    self.roles[role].get("wrapper", "%s"),
                )
                reply = Reply(ReplyType.INFO, f"预设角色为 {role}:\n" + self.roles[role][desckey])
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                
        # 自定义角色设定
        elif customize == True:
            self.roleplays[sessionid] = RolePlay(bot, sessionid, clist[1], "%s")
            reply = Reply(ReplyType.INFO, f"角色设定为:\n{clist[1]}")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            
        # 角色扮演对话
        else:
            e_context["context"]["generate_breaked_by"] = EventAction.BREAK
            prompt = self.roleplays[sessionid].action(content)
            e_context["context"].type = ContextType.TEXT
            e_context["context"].content = prompt
            e_context.action = EventAction.BREAK

    def get_help_text(self, verbose=False, **kwargs):
        """
        获取帮助文本
        
        Returns:
            str: 帮助信息
        """
        help_text = "让机器人扮演不同的角色。\n"
        if not verbose:
            return help_text
        trigger_prefix = conf().get("plugin_trigger_prefix", "$")
        help_text = f"使用方法:\n{trigger_prefix}角色 角色名: 设定角色为{预设角色名}。\n"
        help_text += f"{trigger_prefix}role 角色名: 同上，但使用英文设定。\n"
        help_text += f"{trigger_prefix}设定扮演 角色设定: 设定自定义角色人设为{角色设定}。\n"
        help_text += f"{trigger_prefix}停止扮演: 清除设定的角色。\n"
        help_text += f"{trigger_prefix}角色类型 角色类型: 查看某类{角色类型}的所有预设角色，为所有时输出所有预设角色。\n"
        help_text += "\n目前的角色类型有: \n"
        help_text += "，".join([self.tags[tag][0] for tag in self.tags]) + "。\n"
        help_text += f"\n命令例子: \n{trigger_prefix}角色 写作助理\n"
        help_text += f"{trigger_prefix}角色类型 所有\n"
        help_text += f"{trigger_prefix}停止扮演\n"
        return help_text
