# -*- coding: utf-8 -*-
"""
LinkAI插件 - 知识库、Midjourney绘画、文档摘要插件

功能：
- 集成LinkAI知识库
- Midjourney绘画支持
- 文档/网页自动摘要
- 联网搜索能力

配置：需要在LinkAI平台申请API Key并配置

指令：
$linkai open/close - 开启/关闭对话
$linkai app 应用编码 - 设置知识库应用
$linkai sum open/close - 开启/关闭摘要功能
$mj 描述词 - Midjourney绘画
"""

# 导入插件系统
import plugins

# 导入上下文类型
from bridge.context import ContextType

# 导入回复类
from bridge.reply import Reply, ReplyType

# 导入插件基类
from plugins import *

# 导入Midjourney相关
from .midjourney import MJBot

# 导入摘要功能
from .summary import LinkSummary

# 导入桥接
from bridge import bridge

# 导入过期字典
from common.expired_dict import ExpiredDict

# 导入常量
from common import const

# 导入操作系统模块
import os

# 导入工具函数
from .utils import Util

# 导入配置
from plugin_config, conf


# 注册插件
@plugins.register(
    name="linkai",
    desc="A plugin that supports knowledge base and midjourney drawing.",
    version="0.1.0",
    author="https://link-ai.tech",
    desire_priority=99
)
class LinkAI(Plugin):
    """
    LinkAI插件类
    
    集成LinkAI平台的多种能力。
    """
    
    def __init__(self):
        """
        插件初始化
        """
        super().__init__()
        
        # 注册事件处理
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        
        # 加载配置
        self.config = super().load_config()
        
        if not self.config:
            self.config = self._load_config_template()
            
        # 初始化MJ机器人
        if self.config:
            self.mj_bot = MJBot(self.config.get("midjourney"), self._fetch_group_app_code)
            
        # 摘要配置
        self.sum_config = {}
        if self.config:
            self.sum_config = self.config.get("summary")
            
        logger.debug(f"[LinkAI] inited, config={self.config}")

    def on_handle_context(self, e_context: EventContext):
        """
        处理消息上下文事件
        
        Args:
            e_context: 事件上下文
        """
        # 检查配置
        if not self.config:
            return

        context = e_context['context']
        
        # 过滤不需要处理的消息类型
        if context.type not in [ContextType.TEXT, ContextType.IMAGE, ContextType.IMAGE_CREATE, ContextType.FILE,
                                ContextType.SHARING]:
            return

        # ========== 文件处理 ==========
        if context.type in [ContextType.FILE, ContextType.IMAGE] and self._is_summary_open(context):
            context.get("msg").prepare()
            file_path = context.content
            if not LinkSummary().check_file(file_path, self.sum_config):
                return
            if context.type != ContextType.IMAGE:
                _send_info(e_context, "正在为你加速生成摘要，请稍后")
            app_code = self._fetch_app_code(context)
            res = LinkSummary().summary_file(file_path, app_code)
            if not res:
                if context.type != ContextType.IMAGE:
                    _set_reply_text("因为神秘力量无法获取内容，请稍后再试吧", e_context, level=ReplyType.TEXT)
                return
            summary_text = res.get("summary")
            if context.type != ContextType.IMAGE:
                USER_FILE_MAP[_find_user_id(context) + "-sum_id"] = res.get("summary_id")
                summary_text += "\n\n💬 发送 \"开启对话\" 可以开启与文件内容的对话"
            _set_reply_text(summary_text, e_context, level=ReplyType.TEXT)
            os.remove(file_path)
            return

        # ========== 分享链接处理 ==========
        if (context.type == ContextType.SHARING and self._is_summary_open(context)) or \
                (context.type == ContextType.TEXT and self._is_summary_open(context) and LinkSummary().check_url(context.content)):
            if not LinkSummary().check_url(context.content):
                return
            _send_info(e_context, "正在为你加速生成摘要，请稍后")
            app_code = self._fetch_app_code(context)
            res = LinkSummary().summary_url(context.content, app_code)
            if not res:
                _set_reply_text("因为神秘力量无法获取文章内容，请稍后再试吧~", e_context, level=ReplyType.TEXT)
                return
            _set_reply_text(res.get("summary") + "\n\n💬 发送 \"开启对话\" 可以开启与文章内容的对话", e_context,
                            level=ReplyType.TEXT)
            USER_FILE_MAP[_find_user_id(context) + "-sum_id"] = res.get("summary_id")
            return

        # ========== Midjourney处理 ==========
        mj_type = self.mj_bot.judge_mj_task_type(e_context)
        if mj_type:
            self.mj_bot.process_mj_task(mj_type, e_context)
            return

        # ========== 插件管理 ==========
        if context.content.startswith(f"{_get_trigger_prefix()}linkai"):
            self._process_admin_cmd(e_context)
            return

        # ========== 开启对话 ==========
        if context.type == ContextType.TEXT and context.content == "开启对话" and _find_sum_id(context):
            _send_info(e_context, "正在为你开启对话，请稍后")
            res = LinkSummary().summary_chat(_find_sum_id(context))
            if not res:
                _set_reply_text("开启对话失败，请稍后再试吧", e_context)
                return
            USER_FILE_MAP[_find_user_id(context) + "-file_id"] = res.get("file_id")
            _set_reply_text("💡你可以问我关于这篇文章的任何问题，例如：\n\n" + res.get(
                "questions") + "\n\n发送 \"退出对话\" 可以关闭与文章的对话", e_context, level=ReplyType.TEXT)
            return

        # ========== 退出对话 ==========
        if context.type == ContextType.TEXT and context.content == "退出对话" and _find_file_id(context):
            del USER_FILE_MAP[_find_user_id(context) + "-file_id"]
            bot = bridge.Bridge().find_chat_bot(const.LINKAI)
            bot.sessions.clear_session(context["session_id"])
            _set_reply_text("对话已退出", e_context, level=ReplyType.TEXT)
            return

        # ========== 文件对话 ==========
        if context.type == ContextType.TEXT and _find_file_id(context):
            bot = bridge.Bridge().find_chat_bot(const.LINKAI)
            context.kwargs["file_id"] = _find_file_id(context)
            reply = bot.reply(context.content, context)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return

        # ========== 知识库对话 ==========
        if self._is_chat_task(e_context):
            self._process_chat_task(e_context)

    # 插件管理功能
    def _process_admin_cmd(self, e_context: EventContext):
        """处理管理指令"""
        context = e_context['context']
        cmd = context.content.split()
        
        # 帮助
        if len(cmd) == 1 or (len(cmd) == 2 and cmd[1] == "help"):
            _set_reply_text(self.get_help_text(verbose=True), e_context, level=ReplyType.INFO)
            return

        # 开关对话
        if len(cmd) == 2 and (cmd[1] == "open" or cmd[1] == "close"):
            if not Util.is_admin(e_context):
                _set_reply_text("需要管理员权限执行", e_context, level=ReplyType.ERROR)
                return
            is_open = cmd[1] == "open"
            conf()["use_linkai"] = is_open
            bridge.Bridge().reset_bot()
            _set_reply_text(f"LinkAI对话功能{'开启' if is_open else '关闭'}", e_context, level=ReplyType.INFO)
            return

        # 设置应用
        if len(cmd) == 3 and cmd[1] == "app":
            if not context.kwargs.get("isgroup"):
                _set_reply_text("该指令需在群聊中使用", e_context, level=ReplyType.ERROR)
                return
            if not Util.is_admin(e_context):
                _set_reply_text("需要管理员权限执行", e_context, level=ReplyType.ERROR)
                return
            app_code = cmd[2]
            group_name = context.kwargs.get("msg").from_user_nickname
            group_mapping = self.config.get("group_app_map")
            if group_mapping:
                group_mapping[group_name] = app_code
            else:
                self.config["group_app_map"] = {group_name: app_code}
            super().save_config(self.config)
            _set_reply_text(f"应用设置成功: {app_code}", e_context, level=ReplyType.INFO)
            return

        # 摘要开关
        if len(cmd) == 3 and cmd[1] == "sum" and (cmd[2] == "open" or cmd[2] == "close"):
            if not Util.is_admin(e_context):
                _set_reply_text("需要管理员权限执行", e_context, level=ReplyType.ERROR)
                return
            is_open = cmd[2] == "open"
            if not self.sum_config:
                _set_reply_text("插件未启用summary功能", e_context, level=ReplyType.INFO)
            else:
                self.sum_config["enabled"] = is_open
                _set_reply_text(f"文章总结功能{'开启' if is_open else '关闭'}", e_context, level=ReplyType.INFO)
            return

        _set_reply_text(f"指令错误，请输入{_get_trigger_prefix()}linkai help 获取帮助", e_context, level=ReplyType.INFO)

    def _is_summary_open(self, context) -> bool:
        """检查摘要是否开启"""
        # 获取远程应用状态
        remote_enabled = False
        if context.kwargs.get("isgroup"):
            group_name = context.get("msg").from_user_nickname
            app_code = self._fetch_group_app_code(group_name)
            if app_code:
                if context.type.name in ["FILE", "SHARING"]:
                    remote_enabled = Util.fetch_app_plugin(app_code, "内容总结")
        else:
            app_code = conf().get("linkai_app_code")
            if app_code:
                if context.type.name in ["FILE", "SHARING"]:
                    remote_enabled = Util.fetch_app_plugin(app_code, "内容总结")

        # 基础条件
        base_enabled = (
                self.sum_config
                and self.sum_config.get("enabled")
                and (context.type.name in (
                    self.sum_config.get("type") or ["FILE", "SHARING"]) or context.type.name == "TEXT")
        )

        # 群聊
        if context.kwargs.get("isgroup"):
            return (base_enabled and self.sum_config.get("group_enabled")) or remote_enabled

        return base_enabled or remote_enabled

    def _is_chat_task(self, e_context: EventContext):
        """是否是知识库对话任务"""
        context = e_context['context']
        return self.config.get("group_app_map") and context.kwargs.get("isgroup")

    def _process_chat_task(self, e_context: EventContext):
        """处理知识库对话"""
        context = e_context['context']
        group_name = context.get("msg").from_user_nickname
        app_code = self._fetch_group_app_code(group_name)
        if app_code:
            context.kwargs['app_code'] = app_code

    def _fetch_group_app_code(self, group_name: str) -> str:
        """获取群对应的应用code"""
        group_mapping = self.config.get("group_app_map")
        if group_mapping:
            return group_mapping.get(group_name) or group_mapping.get("ALL_GROUP")

    def _fetch_app_code(self, context) -> str:
        """获取应用code"""
        app_code = conf().get("linkai_app_code")
        if context.kwargs.get("isgroup"):
            group_name = context.get("msg").from_user_nickname
            app_code = self._fetch_group_app_code(group_name)
        return app_code

    def get_help_text(self, verbose=False, **kwargs):
        """获取帮助文本"""
        trigger_prefix = _get_trigger_prefix()
        help_text = "用于集成 LinkAI 提供的知识库、Midjourney绘画、文档总结、联网搜索等能力。\n\n"
        if not verbose:
            return help_text
        help_text += f'📖 知识库\n - 群聊中指定应用: {trigger_prefix}linkai app 应用编码\n'
        help_text += f' - {trigger_prefix}linkai open: 开启对话\n'
        help_text += f' - {trigger_prefix}linkai close: 关闭对话\n'
        help_text += f'\n例如: \n"{trigger_prefix}linkai app Kv2fXJcH"\n\n'
        help_text += f"🎨 绘画\n - 生成: {trigger_prefix}mj 描述词1, 描述词2.. \n - 放大: {trigger_prefix}mju 图片ID 图片序号\n - 变换: {trigger_prefix}mjv 图片ID 图片序号\n - 重置: {trigger_prefix}mjr 图片ID"
        help_text += f"\n\n例如：\n\"{trigger_prefix}mj a little cat, white --ar 9:16\"\n\"{trigger_prefix}mju 11055927171882 2\""
        help_text += f"\n\"{trigger_prefix}mjv 11055927171882 2\"\n\"{trigger_prefix}mjr 11055927171882\""
        help_text += f"\n\n💡 文档总结和对话\n - 开启: {trigger_prefix}linkai sum open\n - 使用: 发送文件、公众号文章等可生成摘要，并与内容对话"
        return help_text

    def _load_config_template(self):
        """加载配置模板"""
        logger.debug("No LinkAI plugin config.json, use plugins/linkai/config.json.template")
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    plugin_conf["midjourney"]["enabled"] = False
                    plugin_conf["summary"]["enabled"] = False
                    write_plugin_config({"linkai": plugin_conf})
                    return plugin_conf
        except Exception as e:
            logger.exception(e)

    def reload(self):
        """重载配置"""
        self.config = super().load_config()


# ========== 辅助函数 ==========

def _send_info(e_context: EventContext, content: str):
    """发送信息"""
    reply = Reply(ReplyType.TEXT, content)
    channel = e_context["channel"]
    channel.send(reply, e_context["context"])


def _find_user_id(context):
    """获取用户ID"""
    if context["isgroup"]:
        return context.kwargs.get("msg").actual_user_id
    else:
        return context["receiver"]


def _set_reply_text(content: str, e_context: EventContext, level: ReplyType = ReplyType.ERROR):
    """设置回复文本"""
    reply = Reply(level, content)
    e_context["reply"] = reply
    e_context.action = EventAction.BREAK_PASS


def _get_trigger_prefix():
    """获取触发前缀"""
    return conf().get("plugin_trigger_prefix", "$")


def _find_sum_id(context):
    """获取摘要ID"""
    return USER_FILE_MAP.get(_find_user_id(context) + "-sum_id")


def _find_file_id(context):
    """获取文件对话ID"""
    user_id = _find_user_id(context)
    if user_id:
        return USER_FILE_MAP.get(user_id + "-file_id")


# 用户文件映射
USER_FILE_MAP = ExpiredDict(conf().get("expires_in_seconds") or 60 * 30)
