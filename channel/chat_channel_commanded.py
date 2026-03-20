# -*- coding: utf-8 -*-
"""
聊天频道抽象类

该类继承自Channel，是所有聊天渠道的通用处理基类。
它封装了与具体消息通道（如微信、飞书、web等）无关的通用处理逻辑，
包括：
- 消息上下文（Context）构造
- 消息处理流程：生成回复 → 装饰回复 → 发送回复
- 会话管理：消息队列、生产者-消费者模式
- 插件事件系统集成
- 语音识别和图片处理

具体渠道（如WebChannel、TerminalChannel等）应该继承这个类，
复用其通用的聊天处理逻辑，只需要实现渠道特定的发送和接收方法。
"""

# 导入操作系统模块，用于文件路径处理、文件删除等操作
import os

# 导入正则表达式模块，用于匹配消息前缀、关键词、提取URL等
import re

# 导入线程模块，用于创建消费者线程、管理线程锁等
import threading

# 导入时间模块，用于延迟、休眠等
import time

# 导入异步取消异常，用于线程池回调处理
from asyncio import CancelledError

# 导入并发执行模块，用于创建线程池处理消息
from concurrent.futures import Future, ThreadPoolExecutor

# 导入桥接模块的上下文相关类
# Context: 消息上下文类，封装消息内容和元数据
# ContextType: 上下文类型枚举（文本、语音、图片等）
from bridge.context import *

# 导入桥接模块的回复相关类
# Reply: 回复类，封装回复类型和内容
# ReplyType: 回复类型枚举（文本、语音、图片、错误等）
from bridge.reply import *

# 导入渠道基类，ChatChannel继承自Channel
from channel.channel import Channel

# 导入双端队列，用于消息队列（支持高效的头尾操作）
from common.dequeue import Dequeue

# 导入内存模块，用于缓存用户图片等临时数据
from common import memory

# 导入插件模块，用于插件管理和事件触发
from plugins import *

# 尝试导入音频转换模块，用于将各种音频格式转换为wav格式（语音识别需要wav格式）
try:
    from voice.audio_convert import any_to_wav
# 如果导入失败（如未安装相关依赖），捕获异常并继续（语音功能将不可用）
except Exception as e:
    pass

# 创建全局线程池，最多同时处理8个消息
# 这是消息处理的核心，所有渠道的消息都会提交到这个线程池执行
handler_pool = ThreadPoolExecutor(max_workers=8)


# 抽象类：聊天频道
# 继承自Channel，封装了与具体消息通道无关的通用聊天处理逻辑
# 所有具体的聊天渠道都应该继承这个类
class ChatChannel(Channel):
    """
    聊天频道抽象类
    
    继承自Channel，提供了通用的聊天处理框架：
    - 消息队列管理（生产者-消费者模式）
    - 会话管理（每个用户/群独立的消息队列）
    - 消息处理流水线：上下文构造 → 回复生成 → 回复装饰 → 回复发送
    - 插件系统集成
    - 语音识别和图片处理
    
    子类需要实现的方法：
    - startup(): 渠道初始化
    - send(): 发送回复
    - handle_text(): 处理接收到的消息
    """
    
    # 登录的用户名（如微信号、飞书企业号等）
    # 部分渠道可能没有这个概念，设为None
    name = None
    
    # 登录的用户ID
    # 用于标识当前登录的账号，过滤自己发送的消息
    user_id = None  # TODO 这个登录的账号和消息来源有啥区别呢？

    def __init__(self):
        """
        ChatChannel初始化方法
        
        调用父类初始化，然后创建自己独立的会话管理数据结构。
        重要：这里使用实例级别属性而非类级别属性，确保不同渠道的数据隔离。
        之前使用类级别属性会导致不同渠道（如飞书和web）的消息互相混淆。
        """
        # 调用父类Channel的__init__方法
        super().__init__()
        
        # ========== 实例级别属性，确保每个渠道实例有独立的数据结构 ==========
        
        # 存储异步任务Future对象的字典
        # key: session_id, value: Future列表
        # 用于跟踪每个会话的待处理任务
        self.futures = {}
        
        # 存储会话消息队列的字典
        # key: session_id, value: [消息队列, 信号量]
        # 每个用户/群组有独立的消息队列，实现消息隔离
        self.sessions = {}
        
        # 线程锁，用于保护sessions和futures的并发访问
        # 确保多线程操作时的数据一致性
        self.lock = threading.Lock()
        
        # 创建消费者线程，持续从消息队列中取出消息并处理
        # 这是一个后台守护线程，随着Channel对象创建而启动
        _thread = threading.Thread(target=self.consume)
        
        # 设置为守护线程，主程序退出时自动终止
        _thread.setDaemon(True)
        
        # 启动消费者线程
        _thread.start()

    def _compose_context(self, ctype: ContextType, content, **kwargs):
        """
        根据消息构造上下文（Context）
        
        这是消息处理的第一步，将原始消息封装为标准化的Context对象。
        主要完成以下工作：
        1. 设置基本的上下文类型和内容
        2. 设置渠道类型
        3. 首次进入时设置session_id和receiver（用户/群ID）
        4. 检查群聊白名单、关键词匹配
        5. 检查黑名单、过滤引用消息
        6. 处理@消息、移除@前缀
        7. 处理图片生成前缀
        8. 触发ON_RECEIVE_MESSAGE插件事件
        
        Args:
            ctype: ContextType枚举，消息类型（TEXT、VOICE、IMAGE等）
            content: 消息内容
            **kwargs: 额外参数，如msg（消息对象）、isgroup（是否群聊）等
            
        Returns:
            Context对象，或None（如果消息被过滤不应回复）
        """
        # 创建Context对象，封装消息类型和内容
        context = Context(ctype, content)
        
        # 将额外参数存储到kwargs中
        context.kwargs = kwargs
        
        # 如果context中没有渠道类型，设置当前渠道的类型
        if "channel_type" not in context:
            context["channel_type"] = self.channel_type
        
        # 如果context中没有原始消息类型，设置当前消息类型
        if "origin_ctype" not in context:
            context["origin_ctype"] = ctype
        
        # 判断是否是首次处理该会话的消息
        # 首次传入时receiver字段不存在，需要初始化session_id和receiver
        first_in = "receiver" not in context
        
        # 如果是首次处理，进行会话初始化
        if first_in:
            # 获取配置对象
            config = conf()
            
            # 从context中获取消息对象
            cmsg = context["msg"]  # TODO 这里是不是声明一下类型会比较好呢
            
            # 获取该用户/群组的自定义数据（可能有自定义API Key、模型等）
            user_data = conf().get_user_data(cmsg.from_user_id) # TODO 这里会保存用户的自定义配置？
            
            # 将用户自定义的API Key和模型设置到context中
            # 这样可以支持每个用户使用不同的API Key
            context["openai_api_key"] = user_data.get("openai_api_key")  # TODO 这会不会和我配置文件中的配置产生重复呢？
            context["gpt_model"] = user_data.get("gpt_model")
            
            # ========== 群聊处理 ==========
            if context.get("isgroup", False):
                # 获取群名称和群ID
                group_name = cmsg.other_user_nickname
                group_id = cmsg.other_user_id

                # 获取群白名单配置
                group_name_white_list = config.get("group_name_white_list", [])  # TODO 目前没有看到这两个的显式配置
                group_name_keyword_white_list = config.get("group_name_keyword_white_list", [])
                
                # 检查群名是否在白名单中，或者匹配关键词白名单
                # any(...) 返回True如果满足任一条件
                if any(
                    [
                        group_name in group_name_white_list,  # 群名精确匹配
                        "ALL_GROUP" in group_name_white_list,  # 允许所有群
                        check_contain(group_name, group_name_keyword_white_list),  # 群名包含关键词
                    ]
                ):
                    # 检查是否启用全局群共享会话配置
                    # True: 整个群共享一个会话（所有成员对话历史在一起）
                    # False: 每个成员有独立的会话
                    group_shared_session = conf().get("group_shared_session", True)  # TODO 目前也没有查看这个的显式配置
                    if group_shared_session:
                        # 群共享会话：所有用户使用同一个session_id（群ID）
                        session_id = group_id
                    else:
                        # 检查是否配置了特定的群共享会话（遗留配置）
                        group_chat_in_one_session = conf().get("group_chat_in_one_session", [])
                        
                        # 初始设为个人session_id
                        session_id = cmsg.actual_user_id
                        
                        # 如果这个群配置了共享会话，则使用群ID
                        if any(
                            [
                                group_name in group_chat_in_one_session,
                                "ALL_GROUP" in group_chat_in_one_session,
                            ]
                        ):
                            session_id = group_id
                            
                else:
                    # 群名不在白名单中，不回复该群的消息
                    logger.debug(f"No need reply, groupName not in whitelist, group_name={group_name}")
                    return None
                    
                # 设置session_id和receiver为群ID
                context["session_id"] = session_id
                context["receiver"] = group_id
                
            # ========== 私聊处理 ==========
            else:
                # 私聊：session_id和receiver都设为对方用户ID
                context["session_id"] = cmsg.other_user_id
                context["receiver"] = cmsg.other_user_id
                
            # 触发插件事件：ON_RECEIVE_MESSAGE
            # 允许插件在消息被正式处理前进行拦截或修改
            e_context = PluginManager().emit_event(EventContext(Event.ON_RECEIVE_MESSAGE, {"channel": self, "context": context}))
            
            # 获取处理后的context
            context = e_context["context"]
            
            # 如果插件标记为"通过"（不继续处理）或context被清空，直接返回
            if e_context.is_pass() or context is None:
                return context
            
            # 如果是自己发送的消息且配置不允许自己触发自己（这里的自己指的是机器人），跳过
            if cmsg.from_user_id == self.user_id and not config.get("trigger_by_self", True):
                logger.debug("[chat_channel]self message skipped")
                return None

        # ========== 消息内容处理 ==========
        # 根据消息类型进行处理
        if ctype == ContextType.TEXT:
            # 首次匹配且是引用消息时过滤
            # 微信等平台转发消息时会有这种格式："」\n- - - - - - -"
            if first_in and "」\n- - - - - - -" in content:
                logger.debug(content)
                logger.debug("[chat_channel]reference query skipped")
                return None  # TODO 这里为啥就直接返回None了呢？

            # 获取昵称黑名单配置
            nick_name_black_list = conf().get("nick_name_black_list", [])
            
            # ========== 群聊消息处理 ==========
            if context.get("isgroup", False):
                # 校验触发关键字
                # group_chat_prefix: 群聊触发前缀（如"@"）
                match_prefix = check_prefix(content, conf().get("group_chat_prefix"))
                # group_chat_keyword: 群聊关键词（消息包含关键词即触发）
                match_contain = check_contain(content, conf().get("group_chat_keyword"))
                
                # flag用于标记是否需要回复
                flag = False
                
                # 如果消息是发给机器人的（to_user_id != actual_user_id说明是@机器人）
                if context["msg"].to_user_id != context["msg"].actual_user_id:
                    # 前缀匹配或关键词匹配，标记需要回复
                    if match_prefix is not None or match_contain is not None:
                        flag = True
                        # 移除前缀
                        if match_prefix:
                            content = content.replace(match_prefix, "", 1).strip()
                            
                    # 如果被@了
                    if context["msg"].is_at:
                        # 获取发送者昵称
                        nick_name = context["msg"].actual_user_nickname
                        
                        # 检查黑名单
                        if nick_name and nick_name in nick_name_black_list:
                            logger.warning(f"[chat_channel] Nickname {nick_name} in In BlackList, ignore")
                            return None

                        logger.info("[chat_channel]receive group at")
                        
                        # 如果没有关闭@触发开关
                        if not conf().get("group_at_off", False):
                            flag = True
                            
                        # 移除@提及（兼容多种空格格式）
                        self.name = self.name if self.name is not None else ""
                        pattern = f"@{re.escape(self.name)}(\u2005|\u0020)"
                        subtract_res = re.sub(pattern, r"", content)
                        
                        # 也移除其他人的@提及
                        if isinstance(context["msg"].at_list, list):
                            for at in context["msg"].at_list:
                                pattern = f"@{re.escape(at)}(\u2005|\u0020)"
                                subtract_res = re.sub(pattern, r"", subtract_res)
                                
                        # 如果前缀移除后没有变化，尝试使用群昵称移除
                        if subtract_res == content and context["msg"].self_display_name:
                            pattern = f"@{re.escape(context['msg'].self_display_name)}(\u2005|\u0020)"
                            subtract_res = re.sub(pattern, r"", content)
                            
                        content = subtract_res
                        
                # flag仍为False，不需要回复
                if not flag:
                    # 如果是语音消息但没有匹配前缀，记录日志
                    if context["origin_ctype"] == ContextType.VOICE:
                        logger.info("[chat_channel]receive group voice, but checkprefix didn't match")
                    return None
                    
            # ========== 私聊消息处理 ==========
            else:
                # 获取发送者昵称
                nick_name = context["msg"].from_user_nickname
                
                # 黑名单检查
                if nick_name and nick_name in nick_name_black_list:
                    logger.warning(f"[chat_channel] Nickname '{nick_name}' in In BlackList, ignore")
                    return None

                # 检查私聊触发前缀
                # single_chat_prefix: 私聊触发前缀列表
                match_prefix = check_prefix(content, conf().get("single_chat_prefix", [""]))
                
                # 如果匹配到自定义前缀，返回过滤掉前缀后的内容
                if match_prefix is not None:
                    content = content.replace(match_prefix, "", 1).strip()
                # 如果是私聊的语音消息，允许不匹配前缀（放宽条件）
                elif context["origin_ctype"] == ContextType.VOICE:
                    pass
                else:
                    logger.info("[chat_channel]receive single chat msg, but checkprefix didn't match")
                    return None
                    
        # 清理内容，去除首尾空白
        content = content.strip()
        
        # 检查图片生成前缀（如"画"、"生成图片"等）
        img_match_prefix = check_prefix(content, conf().get("image_create_prefix",[""]))
        
        # 如果匹配到图片生成前缀
        if img_match_prefix:
            content = content.replace(img_match_prefix, "", 1)
            context.type = ContextType.IMAGE_CREATE  # 改为图片生成类型
        else:
            context.type = ContextType.TEXT  # 设为普通文本类型
            
        # 更新context的内容
        context.content = content.strip()
        
        # 如果没有设置期望回复类型，且配置了always_reply_voice（总是用语音回复）
        # 且该渠道支持语音回复
        if "desire_rtype" not in context and conf().get("always_reply_voice") and ReplyType.VOICE not in self.NOT_SUPPORT_REPLYTYPE:
            context["desire_rtype"] = ReplyType.VOICE
            
        # ========== 语音消息处理 ==========
        elif context.type == ContextType.VOICE:
            # 如果没有设置期望回复类型，且配置了voice_reply_voice（语音回复语音）
            # 且该渠道支持语音
            if "desire_rtype" not in context and conf().get("voice_reply_voice") and ReplyType.VOICE not in self.NOT_SUPPORT_REPLYTYPE:
                context["desire_rtype"] = ReplyType.VOICE
                
        return context

    def _handle(self, context: Context):
        """
        消息处理主函数
        
        这是消息处理的核心流程，分为三个阶段：
        1. _generate_reply(): 生成AI回复
        2. _decorate_reply(): 装饰回复（添加@、前后缀等）
        3. _send_reply(): 发送回复给用户
        
        Args:
            context: 消息上下文对象
        """
        # 空消息或无内容，直接跳过
        if context is None or not context.content:
            return
            
        logger.debug("[chat_channel] handling context: {}".format(context))
        
        # 第一阶段：生成回复
        reply = self._generate_reply(context)

        logger.debug("[chat_channel] decorating reply: {}".format(reply))

        # 第二阶段：装饰回复（如果有有效回复）
        if reply and reply.content:
            reply = self._decorate_reply(context, reply)

            # 第三阶段：发送回复
            self._send_reply(context, reply)

    def _generate_reply(self, context: Context, reply: Reply = Reply()) -> Reply:
        """
        生成AI回复
        
        根据消息类型调用不同的处理逻辑：
        - TEXT/IMAGE_CREATE: 调用AI模型生成文字回复
        - VOICE: 语音识别后生成文字回复
        - IMAGE: 缓存图片信息
        - 其他: 暂不处理
        
        同时触发ON_HANDLE_CONTEXT插件事件，允许插件拦截或修改回复。
        
        Args:
            context: 消息上下文
            reply: 初始的Reply对象（可被插件修改）
            
        Returns:
            Reply: 生成的回复对象
        """
        # 触发插件事件：ON_HANDLE_CONTEXT
        # 允许插件在生成回复前进行拦截或修改
        e_context = PluginManager().emit_event(
            EventContext(
                Event.ON_HANDLE_CONTEXT,
                {"channel": self, "context": context, "reply": reply},
            )
        )
        
        # 获取处理后的回复
        reply = e_context["reply"]
        
        # 如果插件没有标记"通过"，继续默认处理流程
        if not e_context.is_pass():
            logger.debug("[chat_channel] type={}, content={}".format(context.type, context.content))
            
            # ========== 文本消息或图片生成 ==========
            if context.type == ContextType.TEXT or context.type == ContextType.IMAGE_CREATE:
                # 设置渠道引用
                context["channel"] = e_context["channel"]
                # 调用父类的build_reply_content（会调用AI模型）
                reply = super().build_reply_content(context.content, context)
                
            # ========== 语音消息 ==========
            elif context.type == ContextType.VOICE:
                cmsg = context["msg"]
                
                # 准备音频文件（下载等）
                cmsg.prepare()
                
                # 获取音频文件路径
                file_path = context.content
                
                # 生成wav格式路径（语音识别需要wav格式）
                wav_path = os.path.splitext(file_path)[0] + ".wav"
                
                # 尝试转换为wav格式
                try:
                    any_to_wav(file_path, wav_path)
                except Exception as e:
                    # 转换失败，直接使用原文件（某些API也支持mp3）
                    logger.warning("[chat_channel]any to wav error, use raw path. " + str(e))
                    wav_path = file_path
                    
                # 调用语音识别API，将语音转为文字
                reply = super().build_voice_to_text(wav_path)
                
                # 删除临时文件
                try:
                    os.remove(file_path)
                    if wav_path != file_path:
                        os.remove(wav_path)
                except Exception as e:
                    pass
                    
                # 如果识别成功（返回文本类型）
                if reply.type == ReplyType.TEXT:
                    # 构造新的上下文，用识别出的文字继续处理
                    new_context = self._compose_context(ContextType.TEXT, reply.content, **context.kwargs)
                    if new_context:
                        # 递归调用生成回复
                        reply = self._generate_reply(new_context)
                    else:
                        return
                        
            # ========== 图片消息 ==========
            elif context.type == ContextType.IMAGE:
                # 缓存图片信息，供后续处理（如Vision API）
                memory.USER_IMAGE_CACHE[context["session_id"]] = {
                    "path": context.content,
                    "msg": context.get("msg")
                }
                
            # ========== 分享消息 ==========
            elif context.type == ContextType.SHARING:
                pass  # 暂不处理
                
            # ========== 文件消息或函数调用 ==========
            elif context.type == ContextType.FUNCTION or context.type == ContextType.FILE:
                pass  # 暂不处理
                
            # ========== 未知类型 ==========
            else:
                logger.warning("[chat_channel] unknown context type: {}".format(context.type))
                return
                
        return reply

    def _decorate_reply(self, context: Context, reply: Reply) -> Reply:
        """
        装饰回复
        
        在发送前对回复进行装饰处理：
        1. 触发ON_DECORATE_REPLY插件事件
        2. 处理不支持的回复类型（转为错误）
        3. 文字转语音（如需要）
        4. 群聊添加@和前后缀
        5. 私聊添加前后缀
        6. 错误/信息类型添加标识
        
        Args:
            context: 消息上下文
            reply: 待装饰的回复
            
        Returns:
            Reply: 装饰后的回复
        """
        # 有回复且有类型
        if reply and reply.type:
            # 触发插件事件：ON_DECORATE_REPLY
            e_context = PluginManager().emit_event(
                EventContext(
                    Event.ON_DECORATE_REPLY,
                    {"channel": self, "context": context, "reply": reply},
                )
            )
            
            # 获取处理后的回复
            reply = e_context["reply"]
            
            # 获取期望的回复类型（如语音）
            desire_rtype = context.get("desire_rtype")
            
            # 如果插件没有拦截，且有有效回复
            if not e_context.is_pass() and reply and reply.type:
                # ========== 检查是否支持该回复类型 ==========
                if reply.type in self.NOT_SUPPORT_REPLYTYPE:
                    logger.error("[chat_channel]reply type not support: " + str(reply.type))
                    reply.type = ReplyType.ERROR
                    reply.content = "不支持发送的消息类型: " + str(reply.type)

                # ========== 文本回复处理 ==========
                if reply.type == ReplyType.TEXT:
                    reply_text = reply.content
                    
                    # 需要转语音
                    if desire_rtype == ReplyType.VOICE and ReplyType.VOICE not in self.NOT_SUPPORT_REPLYTYPE:
                        # 调用语音合成API
                        reply = super().build_text_to_voice(reply.content)
                        # 递归装饰（因为类型变了）
                        return self._decorate_reply(context, reply)
                        
                    # 群聊：添加@和前后缀
                    if context.get("isgroup", False):
                        # 如果需要@用户
                        if not context.get("no_need_at", False):
                            reply_text = "@" + context["msg"].actual_user_nickname + "\n" + reply_text.strip()
                        # 添加群聊前后缀
                        reply_text = conf().get("group_chat_reply_prefix", "") + reply_text + conf().get("group_chat_reply_suffix", "")
                    # 私聊：添加前后缀
                    else:
                        reply_text = conf().get("single_chat_reply_prefix", "") + reply_text + conf().get("single_chat_reply_suffix", "")
                        
                    reply.content = reply_text
                    
                # ========== 错误或信息类型 ==========
                elif reply.type == ReplyType.ERROR or reply.type == ReplyType.INFO:
                    reply.content = "[" + str(reply.type) + "]\n" + reply.content
                    
                # ========== 媒体类型（图片、语音、视频、文件）==========
                elif reply.type == ReplyType.IMAGE_URL or reply.type == ReplyType.VOICE or reply.type == ReplyType.IMAGE or reply.type == ReplyType.FILE or reply.type == ReplyType.VIDEO or reply.type == ReplyType.VIDEO_URL:
                    pass  # 不需要装饰
                    
                # ========== 未知类型 ==========
                else:
                    logger.error("[chat_channel] unknown reply type: {}".format(reply.type))
                    return
                    
            # 警告：期望类型与实际类型不符
            if desire_rtype and desire_rtype != reply.type and reply.type not in [ReplyType.ERROR, ReplyType.INFO]:
                logger.warning("[chat_channel] desire_rtype: {}, but reply type: {}".format(context.get("desire_rtype"), reply.type))
                
            return reply

    def _send_reply(self, context: Context, reply: Reply):
        """
        发送回复
        
        发送回复给用户，触发ON_SEND_REPLY插件事件。
        特殊处理：
        - 文本回复中提取图片/视频URL并单独发送
        - 图片回复带文本内容时，先发文本再发图片
        
        Args:
            context: 消息上下文
            reply: 要发送的回复
        """
        if reply and reply.type:
            # 触发插件事件：ON_SEND_REPLY
            e_context = PluginManager().emit_event(
                EventContext(
                    Event.ON_SEND_REPLY,
                    {"channel": self, "context": context, "reply": reply},
                )
            )
            
            # 获取处理后的回复
            reply = e_context["reply"]
            
            # 插件没有拦截，且有有效回复
            if not e_context.is_pass() and reply and reply.type:
                logger.debug("[chat_channel] sending reply: {}, context: {}".format(reply, context))
                
                # 如果是文本回复，尝试提取并发送图片
                if reply.type == ReplyType.TEXT:
                    self._extract_and_send_images(reply, context)
                # 如果是图片回复但带有文本内容，先发文本再发图片
                elif reply.type == ReplyType.IMAGE_URL and hasattr(reply, 'text_content') and reply.text_content:
                    # 先发送文本
                    text_reply = Reply(ReplyType.TEXT, reply.text_content)
                    self._send(text_reply, context)
                    # 短暂延迟后发送图片
                    time.sleep(0.3)
                    self._send(reply, context)
                else:
                    self._send(reply, context)
    
    def _extract_and_send_images(self, reply: Reply, context: Context):
        """
        从文本回复中提取图片/视频URL并单独发送
        
        支持的格式：
        - [图片: /path/to/image.png]
        - [视频: /path/to/video.mp4]
        - ![](url) - Markdown图片语法
        - <img src="url"> - HTML图片标签
        - <video src="url"> - HTML视频标签
        - 直接的图片/视频URL
        
        最多发送5个媒体文件。
        
        Args:
            reply: 文本回复
            context: 消息上下文
        """
        # 获取文本内容
        content = reply.content
        
        # 存储提取的媒体项列表 [(url, type), ...]
        media_items = []
        
        # 定义各种正则匹配模式
        patterns = [
            (r'\[图片:\s*([^\]]+)\]', 'image'),   # [图片: /path/to/image.png]
            (r'\[视频:\s*([^\]]+)\]', 'video'),   # [视频: /path/to/video.mp4]
            (r'!\[.*?\]\(([^\)]+)\)', 'image'),   # ![alt](url) - 默认图片
            (r'<img[^>]+src=["\']([^"\']+)["\']', 'image'),  # <img src="url">
            (r'<video[^>]+src=["\']([^"\']+)["\']', 'video'),  # <video src="url">
            (r'https?://[^\s]+\.(?:jpg|jpeg|png|gif|webp)', 'image'),  # 直接的图片URL
            (r'https?://[^\s]+\.(?:mp4|avi|mov|wmv|flv)', 'video'),  # 直接的视频URL
        ]
        
        # 遍历每种模式，提取媒体URL
        for pattern, media_type in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                media_items.append((match, media_type))
        
        # 去重（保持顺序）并限制最多5个
        seen = set()
        unique_items = []
        for url, mtype in media_items:
            if url not in seen:
                seen.add(url)
                unique_items.append((url, mtype))
        media_items = unique_items[:5]
        
        # 如果有媒体文件
        if media_items:
            logger.info(f"[chat_channel] Extracted {len(media_items)} media item(s) from reply")
            
            # 先发送文本内容
            logger.info(f"[chat_channel] Sending text content before media: {reply.content[:100]}...")
            self._send(reply, context)
            logger.info(f"[chat_channel] Text sent, now sending {len(media_items)} media item(s)")
            
            # 然后逐个发送媒体文件
            for i, (url, media_type) in enumerate(media_items):
                try:
                    # 判断是本地文件还是网络URL
                    if url.startswith(('http://', 'https://')):
                        # 网络资源
                        if media_type == 'video':
                            # 视频使用 FILE 类型发送
                            media_reply = Reply(ReplyType.FILE, url)
                            media_reply.file_name = os.path.basename(url)
                        else:
                            # 图片使用 IMAGE_URL 类型
                            media_reply = Reply(ReplyType.IMAGE_URL, url)
                    elif os.path.exists(url):
                        # 本地文件
                        if media_type == 'video':
                            # 视频使用 FILE 类型，转换为 file:// URL
                            media_reply = Reply(ReplyType.FILE, f"file://{url}")
                            media_reply.file_name = os.path.basename(url)
                        else:
                            # 图片使用 IMAGE_URL 类型，转换为 file:// URL
                            media_reply = Reply(ReplyType.IMAGE_URL, f"file://{url}")
                    else:
                        logger.warning(f"[chat_channel] Media file not found or invalid URL: {url}")
                        continue
                    
                    # 发送媒体文件（添加小延迟避免频率限制）
                    if i > 0:
                        time.sleep(0.5)
                    self._send(media_reply, context)
                    logger.info(f"[chat_channel] Sent {media_type} {i+1}/{len(media_items)}: {url[:50]}...")
                    
                except Exception as e:
                    logger.error(f"[chat_channel] Failed to send {media_type} {url}: {e}")
        else:
            # 没有媒体文件，正常发送文本
            self._send(reply, context)

    def _send(self, reply: Reply, context: Context, retry_cnt=0):
        """
        实际发送回复
        
        调用子类的send方法发送回复。
        包含重试机制：最多重试2次，失败后等待递增的时间再重试。
        
        Args:
            reply: 要发送的回复
            context: 消息上下文
            retry_cnt: 当前重试次数
        """
        try:
            # 调用子类的send方法（如WebChannel.send、TerminalChannel.send等）
            self.send(reply, context)
        except Exception as e:
            logger.error("[chat_channel] sendMsg error: {}".format(str(e)))
            
            # 如果是NotImplementedError（子类未实现send），直接返回
            if isinstance(e, NotImplementedError):
                return
                
            # 打印完整异常堆栈
            logger.exception(e)
            
            # 重试机制：最多重试2次
            if retry_cnt < 2:
                # 递增等待时间：3秒、6秒
                time.sleep(3 + 3 * retry_cnt)
                # 递归重试
                self._send(reply, context, retry_cnt + 1)

    def _success_callback(self, session_id, **kwargs):
        """
        线程正常结束时的回调函数
        
        当消息处理线程成功完成时调用，记录日志。
        
        Args:
            session_id: 会话ID
            **kwargs: 额外参数
        """
        logger.debug("Worker return success, session_id = {}".format(session_id))

    def _fail_callback(self, session_id, exception, **kwargs):
        """
        线程异常结束时的回调函数
        
        当消息处理线程抛出异常时调用，记录异常堆栈。
        
        Args:
            session_id: 会话ID
            exception: 异常对象
            **kwargs: 额外参数
        """
        logger.exception("Worker return exception: {}".format(exception))

    def _thread_pool_callback(self, session_id, **kwargs):
        """
        线程池任务完成回调
        
        这是一个高阶函数，返回一个回调函数。
        用于在消息处理完成后：
        1. 检查是否有异常
        2. 调用成功/失败回调
        3. 释放信号量（允许处理下一个消息）
        
        Args:
            session_id: 会话ID
            **kwargs: 额外参数
            
        Returns:
            回调函数
        """
        def func(worker: Future):
            try:
                # 获取线程抛出的异常（如果有）
                worker_exception = worker.exception()
                if worker_exception:
                    # 有异常，调用失败回调
                    self._fail_callback(session_id, exception=worker_exception, **kwargs)
                else:
                    # 无异常，调用成功回调
                    self._success_callback(session_id, **kwargs)
            except CancelledError as e:
                # 任务被取消
                logger.info("Worker cancelled, session_id = {}".format(session_id))
            except Exception as e:
                # 其他异常
                logger.exception("Worker raise exception: {}".format(e))
            finally:
                # 释放信号量，允许处理下一个消息
                with self.lock:
                    self.sessions[session_id][1].release()

        return func

    def produce(self, context: Context):
        """
        生产者：将消息放入会话队列
        
        这是消息处理流水线的入口。
        每个消息根据session_id放入对应的队列，由消费者线程异步处理。
        
        Args:
            context: 消息上下文
        """
        # 获取会话ID
        session_id = context["session_id"]
        
        # 加锁保护sessions字典
        with self.lock:
            # 如果会话不存在，创建新的消息队列
            if session_id not in self.sessions:
                # Dequeue: 双端队列，支持高效的头尾操作
                # BoundedSemaphore: 有界信号量，限制并发数
                # concurrency_in_session: 每个会话的最大并发数
                self.sessions[session_id] = [
                    Dequeue(),
                    threading.BoundedSemaphore(conf().get("concurrency_in_session", 1)),
                ]
            
            # 如果是文本消息且以#开头（管理命令），插队到队列头部优先处理
            if context.type == ContextType.TEXT and context.content.startswith("#"):
                self.sessions[session_id][0].putleft(context)
            # 普通消息，加入队尾
            else:
                self.sessions[session_id][0].put(context)

    def consume(self):
        """
        消费者：持续从消息队列中取出消息并处理
        
        这是一个无限循环的后台线程，持续执行：
        1. 遍历所有会话
        2. 尝试获取信号量（非阻塞）
        3. 从队列中取出消息，提交到线程池处理
        4. 如果队列空且无待处理任务，清理会话
        """
        while True:
            # 获取所有会话ID
            with self.lock:
                session_ids = list(self.sessions.keys())
                
            # 遍历每个会话
            for session_id in session_ids:
                with self.lock:
                    # 获取该会话的队列和信号量
                    context_queue, semaphore = self.sessions[session_id]
                    
                # 尝试获取信号量（非阻塞）
                if semaphore.acquire(blocking=False):
                    # 获取成功，队列非空则处理消息
                    if not context_queue.empty():
                        # 取出消息
                        context = context_queue.get()
                        logger.debug("[chat_channel] consume context: {}".format(context))
                        
                        # 提交到线程池处理
                        future: Future = handler_pool.submit(self._handle, context)
                        
                        # 添加完成回调
                        future.add_done_callback(self._thread_pool_callback(session_id, context=context))
                        
                        # 记录Future
                        with self.lock:
                            if session_id not in self.futures:
                                self.futures[session_id] = []
                            self.futures[session_id].append(future)
                            
                    # 队列空，检查是否可以清理会话
                    elif semaphore._initial_value == semaphore._value + 1:
                        # 除了当前任务，没有其他任务能获取信号量
                        # 说明所有任务都处理完毕，可以清理会话
                        with self.lock:
                            # 清理已完成的Future
                            self.futures[session_id] = [t for t in self.futures[session_id] if not t.done()]
                            assert len(self.futures[session_id]) == 0, "thread pool error"
                            # 删除会话
                            del self.sessions[session_id]
                    else:
                        # 有等待中的任务，释放信号量
