# -*- coding: utf-8 -*-
"""
消息发送渠道抽象类

该类是所有消息渠道（Channel）的基类/抽象类，定义了渠道的基本接口和行为。
所有具体的渠道实现（如WebChannel、TerminalChannel、FeiShuChannel等）
都需要继承这个类并实现其中的抽象方法。

主要功能：
1. 定义渠道的基本属性（如渠道类型、不支持的回复类型）
2. 提供启动/停止生命周期管理
3. 抽象方法供子类实现：发送消息、处理消息、初始化渠道
4. 提供构建回复内容的统一入口（支持普通模式和Agent模式）
5. 提供语音识别和语音合成的统一入口
"""

# 导入桥接模块，用于调用AI模型
from bridge.bridge import Bridge

# 导入上下文模块，用于在消息处理过程中传递信息
from bridge.context import Context

# 导入回复模块，包含Reply类和ReplyType枚举
# Reply: 封装回复内容的类
# ReplyType: 回复类型的枚举（文本、语音、图片、文件等）
from bridge.reply import *

# 导入日志模块，用于记录程序运行日志
from common.log import logger

# 导入配置模块，用于获取应用配置
from config import conf


class Channel(object):
    """
    消息渠道抽象基类
    
    所有具体渠道类都应该继承这个类，并实现以下抽象方法：
    - startup(): 初始化渠道（如登录账号、启动HTTP服务等）
    - send(): 发送回复消息给用户
    - handle_text(): 处理接收到的文本消息
    
    属性说明：
    - channel_type: 渠道类型标识符，如"web"、"terminal"、"feishu"等
    - NOT_SUPPORT_REPLYTYPE: 该渠道不支持的回复类型列表
    - cloud_mode: 是否运行在云模式（由ChannelManager设置）
    - _startup_event: 线程事件，用于同步启动结果
    - _startup_error: 启动错误信息
    """
    
    # 渠道类型标识符，子类应该覆盖这个值
    channel_type = ""
    
    # 该渠道不支持的回复类型列表
    # 默认不支持语音和图片回复（某些渠道可能不支持发送这些类型的消息）
    # 子类可以通过覆盖这个列表来指定自己不支持的类型
    NOT_SUPPORT_REPLYTYPE = [ReplyType.VOICE, ReplyType.IMAGE]

    def __init__(self):
        """
        渠道对象初始化方法
        
        初始化渠道的基本状态：
        - _startup_event: 用于等待渠道启动完成的线程事件
        - _startup_error: 存储启动过程中的错误信息
        - cloud_mode: 标记是否运行在云模式（云客户端模式）
        """
        # 导入threading模块（延迟导入，避免全局导入）
        import threading
        
        # 创建线程事件对象，用于同步渠道启动完成
        # 线程事件对象可以阻塞等待，直到另一个线程调用set()方法
        self._startup_event = threading.Event()
        
        # 初始化启动错误为None，表示启动尚未出错
        self._startup_error = None
        
        # 云模式标志，默认为False
        # 当ChannelManager以云客户端模式运行时，会将此标志设为True
        # 云模式下的行为可能有所不同（如不需要登录等）
        self.cloud_mode = False

    def startup(self):
        """
        初始化渠道（抽象方法）
        
        子类必须实现此方法，进行渠道的初始化工作，例如：
        - 连接到聊天平台（登录账号）
        - 启动HTTP服务器（WebChannel）
        - 初始化WebSocket连接
        
        Raises:
            NotImplementedError: 如果子类没有实现此方法
        """
        # 抛出异常，提示子类必须实现此方法
        raise NotImplementedError

    def report_startup_success(self):
        """
        报告渠道启动成功
        
        在子类的startup()方法中调用，通知系统渠道已经成功启动。
        通常在所有初始化工作完成后调用。
        """
        # 清除错误信息
        self._startup_error = None
        
        # 设置事件为已触发状态，通知等待的线程启动已完成
        self._startup_event.set()

    def report_startup_error(self, error: str):
        """
        报告渠道启动失败
        
        在子类的startup()方法中调用，通知系统渠道启动失败。
        通常在捕获异常后调用，传入错误描述。
        
        Args:
            error: 错误描述字符串，说明启动失败的原因
        """
        # 保存错误信息，供后续查询
        self._startup_error = error
        
        # 设置事件为已触发状态（即使失败也通知等待的线程）
        self._startup_event.set()

    def wait_startup(self, timeout: float = 3) -> (bool, str):
        """
        等待渠道启动结果
        
        调用者使用此方法等待渠道启动完成或失败。
        通常在启动渠道后调用，检查启动是否成功。
        
        Args:
            timeout: 超时时间，单位为秒。默认3秒。
            
        Returns:
            tuple: (success, error_msg)
                - success: bool, 是否成功启动
                - error_msg: str, 如果失败，返回错误信息；成功时为空字符串
        """
        # 等待启动事件触发，最多等待timeout秒
        # 如果超时，ready返回False
        ready = self._startup_event.wait(timeout=timeout)
        
        # 如果等待超时（渠道没有在规定时间内启动完成）
        if not ready:
            # 超时情况下返回成功（可能是异步启动）
            return True, ""  # TODO 这里应该是返回False啊，因为启动超时了啊
        
        # 如果有启动错误信息
        if self._startup_error:
            # 返回失败，并附带错误信息
            return False, self._startup_error
        
        # 启动成功，无错误
        return True, ""

    def stop(self):
        """
        优雅地停止渠道（准备重启）
        
        在应用重启渠道前调用，用于清理资源、关闭连接等。
        子类可以覆盖此方法实现自己的清理逻辑。
        
        默认实现为空（pass），即什么都不做。
        """
        # 占位语句，子类可以覆盖此方法进行清理工作
        pass

    def handle_text(self, msg):
        """
        处理接收到的消息（抽象方法）
        
        子类必须实现此方法，处理从渠道接收到的消息。
        例如：收到微信消息、飞书消息后如何处理。
        
        Args:
            msg: 消息对象，包含消息内容、发送者、接收者等信息
            
        Raises:
            NotImplementedError: 如果子类没有实现此方法
        """
        # 抛出异常，提示子类必须实现此方法
        raise NotImplementedError

    def send(self, reply: Reply, context: Context):
        """
        发送回复消息给用户（抽象方法）
        
        子类必须实现此方法，根据回复类型（文本、语音、图片等）
        调用对应的API或协议发送到用户端。
        
        Args:
            reply: Reply对象，包含回复类型和内容
                - reply.type: ReplyType枚举，表示回复类型
                - reply.content: 回复的实际内容
            context: Context对象，包含上下文信息
                - context['session_id']: 会话ID
                - context['receiver']: 接收者ID
                - 等等
                
        Raises:
            NotImplementedError: 如果子类没有实现此方法
            
        Note:
            这是统一的发送接口，Channel子类根据reply的type字段
            发送不同类型的消息。某些渠道可能不支持某些类型，
            可以通过NOT_SUPPORT_REPLYTYPE属性声明。
        """
        # 抛出异常，提示子类必须实现此方法
        raise NotImplementedError

    def build_reply_content(self, query, context: Context = None) -> Reply:
        """
        构建回复内容（统一入口）
        
        这是生成AI回复内容的核心方法，会根据配置决定使用哪种模式：
        1. Agent模式：如果配置中agent=True，使用Agent进行推理
        2. 普通模式：直接调用AI模型生成回复
        
        Args:
            query: 用户输入的查询/消息内容
            context: 上下文对象，包含会话信息等
            
        Returns:
            Reply: 构建好的回复对象，包含type和content
        """
        # 检查是否启用了Agent模式
        # conf().get("agent") 读取配置中的agent字段，默认返回False
        use_agent = conf().get("agent", False)

        if use_agent:
            # ========== Agent模式 ==========
            try:
                # 记录日志，表明使用Agent模式
                logger.info("[Channel] Using agent mode")

                # 如果context存在且没有设置channel_type，添加渠道类型
                # 这样Agent就知道消息来自哪个渠道
                if context and "channel_type" not in context:  # Note 因为Context实现了__contains__方法，所以能用in语法
                    context["channel_type"] = self.channel_type 

                # 从context中获取on_event回调函数
                # 这是由渠道注入的回调，用于处理流式事件（如SSE）
                # 例如WebChannel会注入SSE回调来处理流式输出
                on_event = context.get("on_event") if context else None

                # 调用Bridge的Agent桥接方法来处理查询
                # 参数说明：
                # - query: 用户输入
                # - context: 上下文信息
                # - on_event: 事件回调函数（用于流式输出）
                # - clear_history: 是否清除历史记录，这里默认False保留会话历史
                return Bridge().fetch_agent_reply(
                    query=query,
                    context=context,
                    on_event=on_event,
                    clear_history=False
                )
            except Exception as e:
                # 如果Agent模式执行失败，记录错误并回退到普通模式
                logger.error(f"[Channel] Agent mode failed, fallback to normal mode: {e}")
                # 回退到普通模式调用AI
                return Bridge().fetch_reply_content(query, context)
        else:
            # ========== 普通模式 ==========
            # 直接调用Bridge获取AI回复（不使用Agent）
            return Bridge().fetch_reply_content(query, context)

    def build_voice_to_text(self, voice_file) -> Reply:
        """
        语音识别：将语音文件转换为文本
        
        统一调用入口，内部通过Bridge调用语音识别模型。
        
        Args:
            voice_file: 语音文件路径，支持多种格式
            
        Returns:
            Reply: 回复对象，类型为TEXT，内容为识别出的文字
        """
        # 调用Bridge的语音转文字方法
        return Bridge().fetch_voice_to_text(voice_file)

    def build_text_to_voice(self, text) -> Reply:
        """
        语音合成：将文本转换为语音
        
        统一调用入口，内部通过Bridge调用语音合成模型。
        
        Args:
            text: 要转换为语音的文本内容
            
        Returns:
            Reply: 回复对象，类型为VOICE，内容为音频文件路径
        """
        # 调用Bridge的文字转语音方法
        return Bridge().fetch_text_to_voice(text)
