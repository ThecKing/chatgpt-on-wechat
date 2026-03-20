# -*- coding: utf-8 -*-
"""
Godcmd插件 - 超级指令插件

这是一个超级管理员插件，提供完整的指令控制系统：

功能：
1. 用户指令：帮助、认证、模型管理、API Key管理、会话重置等
2. 管理员指令：服务控制、插件管理、日志控制等
3. 临时口令：未设置口令时生成临时口令用于认证

指令前缀：#

使用示例：
#help - 显示帮助
#auth 1234 - 认证为管理员
#model gpt-4 - 设置模型
#plist - 查看插件列表
"""

# 设置文件编码
# encoding:utf-8

# 导入JSON模块
import json

# 导入操作系统模块
import os

# 导入随机模块
import random

# 导入字符串模块
import string

# 导入日志模块
import logging

# 导入类型提示
from typing import Tuple

# 导入桥接模块
import bridge.bridge

# 导入插件模块
import plugins

# 导入Bridge类
from bridge.bridge import Bridge

# 导入上下文类型
from bridge.context import ContextType

# 导入回复类和类型
from bridge.reply import Reply, ReplyType

# 导入常量
from common import const

# 导入配置模块
from config import conf, load_config, global_config

# 导入插件系统
from plugins import *


# ==================== 指令定义 ====================

# 普通用户指令集
# key: 指令名, value: {alias: 别名列表, args: 参数列表, desc: 描述}
COMMANDS = {
    # 帮助指令
    "help": {
        "alias": ["help", "帮助"],
        "desc": "回复此帮助",
    },
    # 插件帮助指令
    "helpp": {
        "alias": ["help", "帮助"],  # 与help指令共用别名，根据参数数量区分
        "args": ["插件名"],
        "desc": "回复指定插件的详细帮助",
    },
    # 认证指令
    "auth": {
        "alias": ["auth", "认证"],
        "args": ["口令"],
        "desc": "管理员认证",
    },
    # 模型指令
    "model": {
        "alias": ["model", "模型"],
        "desc": "查看和设置全局模型",
    },
    # 设置API Key指令
    "set_openai_api_key": {
        "alias": ["set_openai_api_key"],
        "args": ["api_key"],
        "desc": "设置你的OpenAI私有api_key",
    },
    # 重置API Key指令
    "reset_openai_api_key": {
        "alias": ["reset_openai_api_key"],
        "desc": "重置为默认的api_key",
    },
    # 设置模型指令
    "set_gpt_model": {
        "alias": ["set_gpt_model"],
        "desc": "设置你的私有模型",
    },
    # 重置模型指令
    "reset_gpt_model": {
        "alias": ["reset_gpt_model"],
        "desc": "重置你的私有模型",
    },
    # 查询模型指令
    "gpt_model": {
        "alias": ["gpt_model"],
        "desc": "查询你使用的模型",
    },
    # 获取ID指令
    "id": {
        "alias": ["id", "用户"],
        "desc": "获取用户id",
    },
    # 重置会话指令
    "reset": {
        "alias": ["reset", "重置会话"],
        "desc": "重置会话",
    },
}

# 管理员指令集
ADMIN_COMMANDS = {
    # 恢复服务
    "resume": {
        "alias": ["resume", "恢复服务"],
        "desc": "恢复服务",
    },
    # 暂停服务
    "stop": {
        "alias": ["stop", "暂停服务"],
        "desc": "暂停服务",
    },
    # 重载配置
    "reconf": {
        "alias": ["reconf", "重载配置"],
        "desc": "重载配置(不包含插件配置)",
    },
    # 重置所有会话
    "resetall": {
        "alias": ["resetall", "重置所有会话"],
        "desc": "重置所有会话",
    },
    # 扫描插件
    "scanp": {
        "alias": ["scanp", "扫描插件"],
        "desc": "扫描插件目录是否有新插件",
    },
    # 插件列表
    "plist": {
        "alias": ["plist", "插件"],
        "desc": "打印当前插件列表",
    },
    # 设置插件优先级
    "setpri": {
        "alias": ["setpri", "设置插件优先级"],
        "args": ["插件名", "优先级"],
        "desc": "设置指定插件的优先级，越大越优先",
    },
    # 重载插件
    "reloadp": {
        "alias": ["reloadp", "重载插件"],
        "args": ["插件名"],
        "desc": "重载指定插件配置",
    },
    # 启用插件
    "enablep": {
        "alias": ["enablep", "启用插件"],
        "args": ["插件名"],
        "desc": "启用指定插件",
    },
    # 禁用插件
    "disablep": {
        "alias": ["disablep", "禁用插件"],
        "args": ["插件名"],
        "desc": "禁用指定插件",
    },
    # 安装插件
    "installp": {
        "alias": ["installp", "安装插件"],
        "args": ["仓库地址或插件名"],
        "desc": "安装指定插件",
    },
    # 卸载插件
    "uninstallp": {
        "alias": ["uninstallp", "卸载插件"],
        "args": ["插件名"],
        "desc": "卸载指定插件",
    },
    # 更新插件
    "updatep": {
        "alias": ["updatep", "更新插件"],
        "args": ["插件名"],
        "desc": "更新指定插件",
    },
    # 调试模式
    "debug": {
        "alias": ["debug", "调试模式", "DEBUG"],
        "desc": "开启机器调试日志",
    },
}


# ==================== 帮助函数 ====================

def get_help_text(isadmin, isgroup):
    """
    获取帮助文本
    
    生成并返回帮助信息，包含普通指令和可用插件列表。
    
    Args:
        isadmin: 是否为管理员
        isgroup: 是否在群聊中
        
    Returns:
        str: 帮助文本
    """
    help_text = "通用指令\n"
    
    # 遍历普通指令
    for cmd, info in COMMANDS.items():
        # 跳过认证相关指令（不显示在帮助中）
        if cmd in ["auth", "set_openai_api_key", "reset_openai_api_key", "set_gpt_model", "reset_gpt_model", "gpt_model"]:
            continue
            
        # 获取渠道类型
        raw_ct = conf().get("channel_type", "web")
        active_channels = raw_ct if isinstance(raw_ct, list) else [c.strip() for c in str(raw_ct).split(",")]
        
        # 跳过ID指令（某些渠道不支持）
        if cmd == "id" and not any(c in ["wxy", "wechatmp"] for c in active_channels):
            continue
            
        # 格式化指令别名
        alias = ["#" + a for a in info["alias"][:1]]
        help_text += f"{','.join(alias)} "
        
        # 添加参数
        if "args" in info:
            args = [a for a in info["args"]]
            help_text += f"{' '.join(args)}"
            
        help_text += f": {info['desc']}\n"

    # 添加可用插件列表
    plugins = PluginManager().list_plugins()
    help_text += "\n可用插件"
    for plugin in plugins:
        if plugins[plugin].enabled and not plugins[plugin].hidden:
            namecn = plugins[plugin].namecn
            help_text += "\n%s: " % namecn
            help_text += PluginManager().instances[plugin].get_help_text(verbose=False).strip()

    # 添加管理员指令
    if ADMIN_COMMANDS and isadmin:
        help_text += "\n\n管理员指令：\n"
        for cmd, info in ADMIN_COMMANDS.items():
            alias = ["#" + a for a in info["alias"][:1]]
            help_text += f"{','.join(alias)} "
            if "args" in info:
                args = [a for a in info["args"]]
                help_text += f"{' '.join(args)}"
            help_text += f": {info['desc']}\n"
            
    return help_text


# ==================== 插件注册 ====================

@plugins.register(
    name="Godcmd",
    desire_priority=999,  # 最高优先级
    hidden=True,  # 隐藏
    desc="为你的机器人添加指令集，有用户和管理员两种角色，加载顺序请放在首位，初次运行后插件目录会生成配置文件, 填充管理员密码后即可认证",
    version="1.0",
    author="lanvent",
)
class Godcmd(Plugin):
    """
    Godcmd插件类
    
    超级指令插件，处理所有以#开头的指令。
    支持用户指令和管理员指令。
    """
    
    def __init__(self):
        """
        插件初始化
        
        加载配置，设置口令，注册事件处理函数。
        """
        # 调用父类初始化
        super().__init__()

        # 配置文件路径
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        
        # 加载配置
        gconf = super().load_config()
        
        # 如果配置为空
        if not gconf:
            # 检查配置文件是否存在
            if not os.path.exists(config_path):
                # 创建默认配置
                gconf = {"password": "", "admin_users": []}
                with open(config_path, "w") as f:
                    json.dump(gconf, f, indent=4)
                    
        # 如果未设置口令
        if gconf["password"] == "":
            # 生成4位临时口令
            self.temp_password = "".join(random.sample(string.digits, 4))
            logger.info("[Godcmd] 因未设置口令，本次的临时口令为%s。" % self.temp_password)
        else:
            self.temp_password = None
            
        # 添加自定义清除记忆指令
        custom_commands = conf().get("clear_memory_commands", [])
        for custom_command in custom_commands:
            if custom_command and custom_command.startswith("#"):
                custom_command = custom_command[1:]
                if custom_command and custom_command not in COMMANDS["reset"]["alias"]:
                    COMMANDS["reset"]["alias"].append(custom_command)

        # 保存配置
        self.password = gconf["password"]
        self.admin_users = gconf["admin_users"]
        global_config["admin_users"] = self.admin_users
        
        # 机器人运行状态
        self.isrunning = True

        # 注册事件处理函数
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        logger.debug("[Godcmd] inited")

    def on_handle_context(self, e_context: EventContext):
        """
        处理消息上下文事件
        
        解析并执行指令。
        
        Args:
            e_context: 事件上下文
        """
        # 获取上下文类型
        context_type = e_context["context"].type
        
        # 只处理文本消息
        if context_type != ContextType.TEXT:
            # 如果服务暂停，拦截消息
            if not self.isrunning:
                e_context.action = EventAction.BREAK_PASS
            return

        # 获取消息内容
        content = e_context["context"].content
        logger.debug("[Godcmd] on_handle_context. content: %s" % content)
        
        # 检查是否是指令（以#开头）
        if content.startswith("#"):
            # 空指令
            if len(content) == 1:
                reply = Reply()
                reply.type = ReplyType.ERROR
                reply.content = f"空指令，输入#help查看指令列表\n"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 获取消息相关对象
            channel = e_context["channel"]
            user = e_context["context"]["receiver"]
            session_id = e_context["context"]["session_id"]
            isgroup = e_context["context"].get("isgroup", False)
            bottype = Bridge().get_bot_type("chat")
            bot = Bridge().get_bot("chat")
            
            # 解析命令和参数
            command_parts = content[1:].strip().split()
            cmd = command_parts[0]
            args = command_parts[1:]
            
            # 检查是否为管理员
            isadmin = False
            if user in self.admin_users:
                isadmin = True
                
            ok = False
            result = "string"
            
            # ========== 处理普通指令 ==========
            if any(cmd in info["alias"] for info in COMMANDS.values()):
                # 找到实际指令名
                cmd = next(c for c, info in COMMANDS.items() if cmd in info["alias"])
                
                # 认证指令
                if cmd == "auth":
                    ok, result = self.authenticate(user, args, isadmin, isgroup)
                    
                # 帮助指令
                elif cmd == "help" or cmd == "helpp":
                    if len(args) == 0:
                        ok, result = True, get_help_text(isadmin, isgroup)
                    else:
                        # 查找插件帮助
                        plugins = PluginManager().list_plugins()
                        query_name = args[0].upper()
                        for name, plugincls in plugins.items():
                            if not plugincls.enabled:
                                continue
                            if query_name == name or query_name == plugincls.namecn:
                                ok, result = True, PluginManager().instances[name].get_help_text(isgroup=isgroup, isadmin=isadmin, verbose=True)
                                break
                        if not ok:
                            result = "插件不存在或未启用"
                            
                # 模型指令
                elif cmd == "model":
                    if not isadmin and not self.is_admin_in_group(e_context["context"]):
                        ok, result = False, "需要管理员权限执行"
                    elif len(args) == 0:
                        model = conf().get("model") or const.GPT35
                        ok, result = True, "当前模型为: " + str(model)
                    elif len(args) == 1:
                        if args[0] not in const.MODEL_LIST:
                            ok, result = False, "模型名称不存在"
                        else:
                            conf()["model"] = self.model_mapping(args[0])
                            Bridge().reset_bot()
                            model = conf().get("model") or const.GPT35
                            ok, result = True, "模型设置为: " + str(model)
                            
                # ID指令
                elif cmd == "id":
                    ok, result = True, user
                    
                # 设置API Key指令
                elif cmd == "set_openai_api_key":
                    if len(args) == 1:
                        user_data = conf().get_user_data(user)
                        user_data["openai_api_key"] = args[0]
                        ok, result = True, "你的OpenAI私有api_key已设置为" + args[0]
                    else:
                        ok, result = False, "请提供一个api_key"
                        
                # 重置API Key指令
                elif cmd == "reset_openai_api_key":
                    try:
                        user_data = conf().get_user_data(user)
                        user_data.pop("openai_api_key")
                        ok, result = True, "你的OpenAI私有api_key已清除"
                    except Exception as e:
                        ok, result = False, "你没有设置私有api_key"
                        
                # 设置模型指令
                elif cmd == "set_gpt_model":
                    if len(args) == 1:
                        user_data = conf().get_user_data(user)
                        user_data["gpt_model"] = args[0]
                        ok, result = True, "你的GPT模型已设置为" + args[0]
                    else:
                        ok, result = False, "请提供一个GPT模型"
                        
                # 查询模型指令
                elif cmd == "gpt_model":
                    user_data = conf().get_user_data(user)
                    model = conf().get("model")
                    if "gpt_model" in user_data:
                        model = user_data["gpt_model"]
                    ok, result = True, "你的GPT模型为" + str(model)
                    
                # 重置模型指令
                elif cmd == "reset_gpt_model":
                    try:
                        user_data = conf().get_user_data(user)
                        user_data.pop("gpt_model")
                        ok, result = True, "你的GPT模型已重置"
                    except Exception as e:
                        ok, result = False, "你没有设置私有GPT模型"
                        
                # 重置会话指令
                elif cmd == "reset":
                    if bottype in [const.OPEN_AI, const.OPENAI, const.CHATGPT, const.CHATGPTONAZURE, const.LINKAI, const.BAIDU, const.XUNFEI, const.QWEN, const.GEMINI, const.ZHIPU_AI, const.CLAUDEAPI]:
                        bot.sessions.clear_session(session_id)
                        if Bridge().chat_bots.get(bottype):
                            Bridge().chat_bots.get(bottype).sessions.clear_session(session_id)
                        channel.cancel_session(session_id)
                        ok, result = True, "会话已重置"
                    else:
                        ok, result = False, "当前对话机器人不支持重置会话"
                        
                logger.debug("[Godcmd] command: %s by %s" % (cmd, user))
                
            # ========== 处理管理员指令 ==========
            elif any(cmd in info["alias"] for info in ADMIN_COMMANDS.values()):
                if isadmin:
                    if isgroup:
                        ok, result = False, "群聊不可执行管理员指令"
                    else:
                        cmd = next(c for c, info in ADMIN_COMMANDS.items() if cmd in info["alias"])
                        
                        # 暂停服务
                        if cmd == "stop":
                            self.isrunning = False
                            ok, result = True, "服务已暂停"
                            
                        # 恢复服务
                        elif cmd == "resume":
                            self.isrunning = True
                            ok, result = True, "服务已恢复"
                            
                        # 重载配置
                        elif cmd == "reconf":
                            load_config()
                            ok, result = True, "配置已重载"
                            
                        # 重置所有会话
                        elif cmd == "resetall":
                            if bottype in [const.OPEN_AI, const.OPENAI, const.CHATGPT, const.CHATGPTONAZURE, const.LINKAI,
                                           const.BAIDU, const.XUNFEI, const.QWEN, const.GEMINI, const.ZHIPU_AI, const.MOONSHOT,
                                           const.MODELSCOPE]:
                                channel.cancel_all_session()
                                bot.sessions.clear_all_session()
                                ok, result = True, "重置所有会话成功"
                            else:
                                ok, result = False, "当前对话机器人不支持重置会话"
                                
                        # 调试模式
                        elif cmd == "debug":
                            if logger.getEffectiveLevel() == logging.DEBUG:
                                logger.setLevel(logging.INFO)
                                ok, result = True, "DEBUG模式已关闭"
                            else:
                                logger.setLevel(logging.DEBUG)
                                ok, result = True, "DEBUG模式已开启"
                                
                        # 插件列表
                        elif cmd == "plist":
                            plugins = PluginManager().list_plugins()
                            ok = True
                            result = "插件列表：\n"
                            for name, plugincls in plugins.items():
                                result += f"{plugincls.name}_v{plugincls.version} {plugincls.priority} - "
                                if plugincls.enabled:
                                    result += "已启用\n"
                                else:
                                    result += "未启用\n"
                                    
                        # 扫描插件
                        elif cmd == "scanp":
                            new_plugins = PluginManager().scan_plugins()
                            ok, result = True, "插件扫描完成"
                            PluginManager().activate_plugins()
                            if len(new_plugins) > 0:
                                result += "\n发现新插件：\n"
                                result += "\n".join([f"{p.name}_v{p.version}" for p in new_plugins])
                            else:
                                result += ", 未发现新插件"
                                
                        # 设置优先级
                        elif cmd == "setpri":
                            if len(args) != 2:
                                ok, result = False, "请提供插件名和优先级"
                            else:
                                ok = PluginManager().set_plugin_priority(args[0], int(args[1]))
                                if ok:
                                    result = "插件" + args[0] + "优先级已设置为" + args[1]
                                else:
                                    result = "插件不存在"
                                    
                        # 重载插件
                        elif cmd == "reloadp":
                            if len(args) != 1:
                                ok, result = False, "请提供插件名"
                            else:
                                ok = PluginManager().reload_plugin(args[0])
                                if ok:
                                    result = "插件配置已重载"
                                else:
                                    result = "插件不存在"
                                    
                        # 启用插件
                        elif cmd == "enablep":
                            if len(args) != 1:
                                ok, result = False, "请提供插件名"
                            else:
                                ok, result = PluginManager().enable_plugin(args[0])
                                
                        # 禁用插件
                        elif cmd == "disablep":
                            if len(args) != 1:
                                ok, result = False, "请提供插件名"
                            else:
                                ok = PluginManager().disable_plugin(args[0])
                                if ok:
                                    result = "插件已禁用"
                                else:
                                    result = "插件不存在"
                                    
                        # 安装插件
                        elif cmd == "installp":
                            if len(args) != 1:
                                ok, result = False, "请提供插件名或.git结尾的仓库地址"
                            else:
                                ok, result = PluginManager().install_plugin(args[0])
                                
                        # 卸载插件
                        elif cmd == "uninstallp":
                            if len(args) != 1:
                                ok, result = False, "请提供插件名"
                            else:
                                ok, result = PluginManager().uninstall_plugin(args[0])
                                
                        # 更新插件
                        elif cmd == "updatep":
                            if len(args) != 1:
                                ok, result = False, "请提供插件名"
                            else:
                                ok, result = PluginManager().update_plugin(args[0])
                                
                        logger.debug("[Godcmd] admin command: %s by %s" % (cmd, user))
                else:
                    ok, result = False, "需要管理员权限才能执行该指令"
                    
            # ========== 未知指令 ==========
            else:
                trigger_prefix = conf().get("plugin_trigger_prefix", "$")
                if trigger_prefix == "#":
                    return
                ok, result = False, f"未知指令：{cmd}\n查看指令列表请输入#help \n"

            # 构建回复
            reply = Reply()
            if ok:
                reply.type = ReplyType.INFO
            else:
                reply.type = ReplyType.ERROR
            reply.content = result
            e_context["reply"] = reply

            # 中断事件
            e_context.action = EventAction.BREAK_PASS
            
        # 如果服务暂停且不是指令，拦截消息
        elif not self.isrunning:
            e_context.action = EventAction.BREAK_PASS

    def authenticate(self, userid, args, isadmin, isgroup) -> Tuple[bool, str]:
        """
        认证用户为管理员
        
        Args:
            userid: 用户ID
            args: 参数（口令）
            isadmin: 是否已是管理员
            isgroup: 是否在群聊
            
        Returns:
            tuple: (是否成功, 消息)
        """
        if isgroup:
            return False, "请勿在群聊中认证"

        if isadmin:
            return False, "管理员账号无需认证"

        if len(args) != 1:
            return False, "请提供口令"

        password = args[0]
        if password == self.password:
            self.admin_users.append(userid)
            global_config["admin_users"].append(userid)
            return True, "认证成功"
        elif password == self.temp_password:
            self.admin_users.append(userid)
            global_config["admin_users"].append(userid)
            return True, "认证成功，请尽快设置口令"
        else:
            return False, "认证失败"

    def get_help_text(self, isadmin=False, isgroup=False, **kwargs):
        """
        获取帮助文本
        
        Returns:
            str: 帮助信息
        """
        return get_help_text(isadmin, isgroup)

    def is_admin_in_group(self, context):
        """
        检查用户在群中是否为管理员
        
        Args:
            context: 上下文
            
        Returns:
            bool: 是否为管理员
        """
        if context["isgroup"]:
            return context.kwargs.get("msg").actual_user_id in global_config["admin_users"]
        return False

    def model_mapping(self, model) -> str:
        """
        模型名称映射
        
        Args:
            model: 原始模型名
            
        Returns:
            str: 映射后的模型名
        """
        if model == "gpt-4-turbo":
            return const.GPT4_TURBO_PREVIEW
        return model

    def reload(self):
        """
        重载配置
        """
        gconf = pconf(self.name)
        if gconf:
            if gconf.get("password"):
                self.password = gconf["password"]
            if gconf.get("admin_users"):
                self.admin_users = gconf["admin_users"]
