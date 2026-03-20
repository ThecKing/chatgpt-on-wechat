# -*- coding: utf-8 -*-
"""
Hello插件 - 简单的问候插件

这是一个简单的示例插件，功能包括：
1. 用户发送"Hello"时，回复欢迎消息
2. 用户发送"Hi"时，回复"Hi"
3. 用户发送"End"时，生成一张图片
4. 新用户入群时，发送欢迎消息
5. 用户退群时，发送告别消息
6. 用户"拍了拍"时，发送提示消息

这是一个很好的插件开发示例，展示 了如何：
- 注册插件
- 监听事件
- 修改回复内容
- 修改上下文类型
"""

# 设置文件编码
# encoding:utf-8

# 导入插件系统模块
import plugins

# 导入上下文类型枚举
from bridge.context import ContextType

# 导入回复类和回复类型
from bridge.reply import Reply, ReplyType

# 导入聊天消息类
from channel.chat_message import ChatMessage

# 导入日志模块
from common.log import logger

# 导入插件系统（用于注册）
from plugins import *

# 导入配置模块
from config import conf


# 使用装饰器注册插件
# name: 插件名称
# desire_priority: 优先级，数值越大越先执行，-1表示较低优先级
# hidden: 是否隐藏（不在插件列表中显示）
# desc: 插件描述
# version: 插件版本
# author: 插件作者
@plugins.register(
    name="Hello",
    desire_priority=-1,
    hidden=True,
    desc="A simple plugin that says hello",
    version="0.1",
    author="lanvent",
)
class Hello(Plugin):
    """
    Hello插件类
    
    处理简单的问候命令和群事件。
    """
    
    # 群欢迎消息的提示词模板
    # {nickname} 会被替换为新用户的昵称
    group_welc_prompt = "请你随机使用一种风格说一句问候语来欢迎新用户\"{nickname}\"加入群聊。"
    
    # 退群消息的提示词模板
    group_exit_prompt = "请你随机使用一种风格介绍你自己，并告诉用户输入#help可以查看帮助信息。"
    
    # 拍了拍的提示词模板
    patpat_prompt = "请你随机使用一种风格跟其他群用户说他违反规则\"{nickname}\"退出群聊。"

    def __init__(self):
        """
        插件初始化
        
        加载配置，注册事件处理函数。
        """
        # 调用父类初始化
        super().__init__()
        
        try:
            # 加载插件配置
            self.config = super().load_config()
            
            # 如果配置为空，加载模板配置
            if not self.config:
                self.config = self._load_config_template()
                
            # 获取配置的固定欢迎消息（每个群不同）
            self.group_welc_fixed_msg = self.config.get("group_welc_fixed_msg", {})
            
            # 获取欢迎消息提示词（可自定义）
            self.group_welc_prompt = self.config.get("group_welc_prompt", self.group_welc_prompt)
            
            # 获取退群消息提示词
            self.group_exit_prompt = self.config.get("group_exit_prompt", self.group_exit_prompt)
            
            # 获取拍了拍消息提示词
            self.patpat_prompt = self.config.get("patpat_prompt", self.patpat_prompt)
            
            # 记录调试日志
            logger.debug("[Hello] inited")
            
            # 注册事件处理函数
            # 监听 ON_HANDLE_CONTEXT 事件
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            
        except Exception as e:
            # 初始化失败，记录错误并抛出异常
            logger.error(f"[Hello]初始化异常：{e}")
            raise "[Hello] init failed, ignore "

    def on_handle_context(self, e_context: EventContext):
        """
        处理消息上下文事件
        
        这是插件的核心处理函数，在消息处理前被调用。
        可以修改回复内容、拦截消息等。
        
        Args:
            e_context: 事件上下文对象
        """
        # 获取上下文中的消息类型
        context_type = e_context["context"].type
        
        # 只处理特定类型的消息
        if context_type not in [
            ContextType.TEXT,      # 文本消息
            ContextType.JOIN_GROUP,  # 入群消息
            ContextType.PATPAT,      # 拍了拍消息
            ContextType.EXIT_GROUP   # 退群消息
        ]:
            return
            
        # 获取消息对象
        msg: ChatMessage = e_context["context"]["msg"]
        
        # 获取群名称
        group_name = msg.from_user_nickname
        
        # ========== 处理入群事件 ==========
        if context_type == ContextType.JOIN_GROUP:
            # 检查是否有固定欢迎消息（全局或针对此群）
            if "group_welcome_msg" in conf() or group_name in self.group_welc_fixed_msg:
                # 创建回复对象
                reply = Reply()
                reply.type = ReplyType.TEXT
                
                # 优先使用群专属消息，否则使用全局消息
                if group_name in self.group_welc_fixed_msg:
                    reply.content = self.group_welc_fixed_msg.get(group_name, "")
                else:
                    reply.content = conf().get("group_welcome_msg", "")
                    
                # 设置回复
                e_context["reply"] = reply
                
                # BREAK_PASS: 事件结束，跳过默认处理逻辑
                # 这意味着不会调用AI生成回复，直接发送固定消息
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 没有固定消息，将上下文改为文本类型，使用AI生成欢迎
            e_context["context"].type = ContextType.TEXT
            e_context["context"].content = self.group_welc_prompt.format(nickname=msg.actual_user_nickname)
            
            # BREAK: 事件结束，进入默认处理逻辑（调用AI生成回复）
            e_context.action = EventAction.BREAK
            
            # 如果配置不使用角色描述，设置生成中断标记
            if not self.config or not self.config.get("use_character_desc"):
                e_context["context"]["generate_breaked_by"] = EventAction.BREAK
            return
        
        # ========== 处理退群事件 ==========
        if context_type == ContextType.EXIT_GROUP:
            # 检查是否启用退群消息
            if conf().get("group_chat_exit_group"):
                e_context["context"].type = ContextType.TEXT
                e_context["context"].content = self.group_exit_prompt.format(nickname=msg.actual_user_nickname)
                # 进入默认处理逻辑
                e_context.action = EventAction.BREAK
                return
            # 禁用退群消息，直接中断
            e_context.action = EventAction.BREAK
            return
            
        # ========== 处理拍了拍事件 ==========
        if context_type == ContextType.PATPAT:
            e_context["context"].type = ContextType.TEXT
            e_context["context"].content = self.patpat_prompt
            # 进入默认处理逻辑
            e_context.action = EventAction.BREAK
            
            if not self.config or not self.config.get("use_character_desc"):
                e_context["context"]["generate_breaked_by"] = EventAction.BREAK
            return

        # ========== 处理文本消息 ==========
        # 获取消息内容
        content = e_context["context"].content
        
        logger.debug("[Hello] on_handle_context. content: %s" % content)
        
        # 处理 "Hello" 命令
        if content == "Hello":
            # 创建回复对象
            reply = Reply()
            reply.type = ReplyType.TEXT
            
            # 群聊和私聊回复不同
            if e_context["context"]["isgroup"]:
                # 群聊：显示发送者和群名称
                reply.content = f"Hello, {msg.actual_user_nickname} from {msg.from_user_nickname}"
            else:
                # 私聊：只显示发送者名称
                reply.content = f"Hello, {msg.from_user_nickname}"
                
            # 设置回复
            e_context["reply"] = reply
            
            # BREAK_PASS: 跳过默认处理，直接发送回复
            e_context.action = EventAction.BREAK_PASS

        # 处理 "Hi" 命令
        if content == "Hi":
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = "Hi"
            e_context["reply"] = reply
            # BREAK: 进入默认处理逻辑（可能被其他插件覆盖）
            e_context.action = EventAction.BREAK

        # 处理 "End" 命令 - 生成图片
        if content == "End":
            # 将消息类型改为图片生成
            e_context["context"].type = ContextType.IMAGE_CREATE
            content = "The World"
            # CONTINUE: 继续传播，让后续插件或默认逻辑处理
            e_context.action = EventAction.CONTINUE

    def get_help_text(self, **kwargs):
        """
        获取插件帮助文本
        
        Returns:
            str: 帮助信息
        """
        help_text = "输入Hello，我会回复你的名字\n输入End，我会回复你世界的图片\n"
        return help_text

    def _load_config_template(self):
        """
        加载配置模板
        
        如果没有配置文件，使用模板文件。
        
        Returns:
            dict: 配置字典
        """
        logger.debug("No Hello plugin config.json, use plugins/hello/config.json.template")
        try:
            # 获取模板文件路径
            plugin_config_path = os.path.join(self.path, "config.json.template")
            
            # 检查模板文件是否存在
            if os.path.exists(plugin_config_path):
                # 读取模板配置
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    return plugin_conf
        except Exception as e:
            # 记录异常
            logger.exception(e)
