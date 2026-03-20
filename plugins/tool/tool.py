# -*- coding: utf-8 -*-
"""
Tool插件 - 工具扩展插件

功能：
- 为ChatGPT集成各种工具
- 支持搜索、数学运算、联网等功能
- 丰富机器人的扩展能力

配置示例 (config.json)：
{
    "tools": ["arxiv", "bing-search", "google-search", ...],
    "kwargs": {
        "debug": false,
        "model_name": "gpt-3.5-turbo",
        ...
    }
}

指令：
$tool - 查看工具帮助
$tool reset - 重置工具
$tool <工具名> <命令> - 使用指定工具
$tool <命令> - 使用所有工具尽力回答
"""

# 导入chatgpt_tool_hub库
from chatgpt_tool_hub.apps import AppFactory
from chatgpt_tool_hub.apps.app import App
from chatgpt_tool_hub.tools.tool_register import main_tool_register

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

# 导入配置
from config import conf, get_appdata_dir

# 导入插件系统
from plugins import *


# 注册插件
@plugins.register(
    name="tool",
    desc="Arming your ChatGPT bot with various tools",
    version="0.5",
    author="goldfishh",
    desire_priority=0,
)
class Tool(Plugin):
    """
    Tool插件类
    
    工具扩展插件，为机器人集成各种工具。
    """
    
    def __init__(self):
        """
        插件初始化
        
        加载工具配置，创建App实例。
        """
        # 调用父类初始化
        super().__init__()
        
        # 注册事件处理
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        
        # 重置App
        self.app = self._reset_app()
        
        # 检查配置
        if not self.tool_config.get("tools"):
            logger.warn("[tool] init failed, ignore ")
            raise Exception("config.json not found")
            
        logger.info("[tool] inited")


    def get_help_text(self, verbose=False, **kwargs):
        """
        获取帮助文本
        
        Returns:
            str: 帮助信息
        """
        help_text = "这是一个能让chatgpt联网，搜索，数字运算的插件，将赋予强大且丰富的扩展能力。"
        trigger_prefix = conf().get("plugin_trigger_prefix", "$")
        if not verbose:
            return help_text
        help_text += "\n使用说明：\n"
        help_text += f"{trigger_prefix}tool " + "命令: 根据给出的{命令}模型来选择使用哪些工具尽力为你得到结果。\n"
        help_text += f"{trigger_prefix}tool 工具名 " + "命令: 根据给出的{命令}使用指定工具尽力为你得到结果。\n"
        help_text += f"{trigger_prefix}tool reset: 重置工具。\n\n"

        help_text += f"已加载工具列表: \n"
        for idx, tool in enumerate(main_tool_register.get_registered_tool_names()):
            if idx != 0:
                help_text += ", "
            help_text += f"{tool}"
        return help_text

    def on_handle_context(self, e_context: EventContext):
        """
        处理消息上下文事件
        
        Args:
            e_context: 事件上下文
        """
        # 只处理文本消息
        if e_context["context"].type != ContextType.TEXT:
            return

        # 暂时不支持某些Bot
        if Bridge().get_bot_type("chat") not in (
            const.OPENAI,
            const.CHATGPT,
            const.OPEN_AI,
            const.CHATGPTONAZURE,
            const.LINKAI,
        ):
            return

        # 获取消息内容
        content = e_context["context"].content
        content_list = e_context["context"].content.split(maxsplit=1)

        if not content or len(content_list) < 1:
            e_context.action = EventAction.CONTINUE
            return

        logger.debug("[tool] on_handle_context. content: %s" % content)
        reply = Reply()
        reply.type = ReplyType.TEXT
        trigger_prefix = conf().get("plugin_trigger_prefix", "$")
        
        # ========== 处理tool指令 ==========
        if content.startswith(f"{trigger_prefix}tool"):
            # 查看帮助
            if len(content_list) == 1:
                logger.debug("[tool]: get help")
                reply.content = self.get_help_text()
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            elif len(content_list) > 1:
                # 重置工具
                if content_list[1].strip() == "reset":
                    logger.debug("[tool]: reset config")
                    self.app = self._reset_app()
                    reply.content = "重置工具成功"
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return
                # 提醒用户
                elif content_list[1].startswith("reset"):
                    logger.debug("[tool]: remind")
                    e_context["context"].content = "请你随机用一种聊天风格，提醒用户：如果想重置tool插件，reset之后不要加任何字符"
                    e_context.action = EventAction.BREAK
                    return
                    
                query = content_list[1].strip()
                
                # 检查是否指定了工具
                use_one_tool = False
                for tool_name in main_tool_register.get_registered_tool_names():
                    if query.startswith(tool_name):
                        use_one_tool = True
                        query = query[len(tool_name):]
                        break

                # 获取会话
                all_sessions = Bridge().get_bot("chat").sessions
                user_session = all_sessions.session_query(query, e_context["context"]["session_id"]).messages

                logger.debug("[tool]: just-go")
                try:
                    if use_one_tool:
                        # 使用指定工具
                        _func, _ = main_tool_register.get_registered_tool()[tool_name]
                        tool = _func(**self.app_kwargs)
                        _reply = tool.run(query)
                    else:
                        # 使用所有工具
                        _reply = self.app.ask(query, user_session)
                    e_context.action = EventAction.BREAK_PASS
                    all_sessions.session_reply(_reply, e_context["context"]["session_id"])
                except Exception as e:
                    logger.exception(e)
                    logger.error(str(e))
                    e_context["context"].content = "请你随机用一种聊天风格，提醒用户：这个问题tool插件暂时无法处理"
                    reply.type = ReplyType.ERROR
                    e_context.action = EventAction.BREAK
                    return

                reply.content = _reply
                e_context["reply"] = reply
        return

    def _read_json(self) -> dict:
        """
        读取配置
        
        Returns:
            dict: 配置字典
        """
        default_config = {"tools": [], "kwargs": {}}
        return super().load_config() or default_config

    def _build_tool_kwargs(self, kwargs: dict):
        """
        构建工具参数
        
        Args:
            kwargs: 配置中的参数
            
        Returns:
            dict: 完整的工具参数
        """
        tool_model_name = kwargs.get("model_name")
        request_timeout = kwargs.get("request_timeout")

        return {
            # 全局配置
            "log": False,
            "debug": kwargs.get("debug", False),
            "no_default": kwargs.get("no_default", False),
            "think_depth": kwargs.get("think_depth", 2),
            "proxy": conf().get("proxy", ""),
            "request_timeout": request_timeout if request_timeout else conf().get("request_timeout", 120),
            "temperature": kwargs.get("temperature", 0),
            # LLM配置
            "llm_api_key": conf().get("open_ai_api_key", ""),
            "llm_api_base_url": conf().get("open_ai_api_base", "https://api.openai.com/v1"),
            "deployment_id": conf().get("azure_deployment_id", ""),
            "model_name": tool_model_name if tool_model_name else conf().get("model", const.GPT35),
            # 工具配置...（省略详细注释）
        }

    def _filter_tool_list(self, tool_list: list):
        """
        过滤无效的工具名
        
        Args:
            tool_list: 工具列表
            
        Returns:
            list: 有效的工具列表
        """
        valid_list = []
        for tool in tool_list:
            if tool in main_tool_register.get_registered_tool_names():
                valid_list.append(tool)
            else:
                logger.warning("[tool] filter invalid tool: " + repr(tool))
        return valid_list

    def _reset_app(self) -> App:
        """
        重置App实例
        
        Returns:
            App: 新的App实例
        """
        self.tool_config = self._read_json()
        self.app_kwargs = self._build_tool_kwargs(self.tool_config.get("kwargs", {}))

        app = AppFactory()
        app.init_env(**self.app_kwargs)
        # 过滤不支持的工具
        tool_list = self._filter_tool_list(self.tool_config.get("tools", []))

        return app.create_app(tools_list=tool_list, **self.app_kwargs)
