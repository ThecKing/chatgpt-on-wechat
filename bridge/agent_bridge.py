# -*- coding: utf-8 -*-
"""
Agent桥接模块 - 将Agent系统与现有COW桥接集成

该模块是Agent模式的核心，负责：
1. 集成Agent系统与COW现有的Bot基础设施
2. 管理每个会话（session）的Agent实例，实现会话隔离
3. 处理Agent的事件回调和消息持久化
4. 支持工具调用（Tool Calling）功能
5. 管理技能（Skills）和条件工具的动态刷新

主要类：
- AgentBridge: Agent桥接主类，管理Agent生命周期
- AgentLLMModel: LLM模型适配器，使用COW的Bot基础设施
- add_openai_compatible_support(): 动态增强Bot的工具调用能力
"""

"""
Agent Bridge - Integrates Agent system with existing COW bridge

Agent桥接模块，将超级Agent系统与COW现有的桥接系统集成。
实现多会话隔离、工具调用、事件处理等功能。
"""

# 导入操作系统模块，用于文件路径处理等
import os

# 导入类型提示模块
from typing import Optional, List

# 导入Agent协议相关类
# Agent: Agent主类
# LLMModel: LLM模型抽象类
# LLMRequest: LLM请求封装
from agent.protocol import Agent, LLMModel, LLMRequest

# 导入Agent事件处理器，处理Agent执行过程中的事件回调
from bridge.agent_event_handler import AgentEventHandler

# 导入Agent初始化器，用于创建Agent实例
from bridge.agent_initializer import AgentInitializer

# 导入COW的桥接类，用于调用AI模型
from bridge.bridge import Bridge

# 导入上下文类，包含消息上下文
from bridge.context import Context

# 导入回复类，包含回复类型和内容
# Reply: 回复封装类
# ReplyType: 回复类型枚举
from bridge.reply import Reply, ReplyType

# 导入常量定义
from common import const

# 导入日志模块
from common.log import logger

# 导入工具函数，用于路径展开等
from common.utils import expand_path

# 导入OpenAI兼容Bot基类，用于动态增强Bot的工具调用能力
from models.openai_compatible_bot import OpenAICompatibleBot


def add_openai_compatible_support(bot_instance):
    """
    动态为Bot实例添加OpenAI兼容的工具调用支持
    
    这是一个非常重要的函数，它允许任何使用OpenAI兼容API格式的Bot
    获得工具调用（Tool Calling）能力，而无需修改Bot本身的代码。
    
    例如：GPT模型本身不支持工具调用，通过这个函数可以动态增强。
    
    注意：某些Bot如ZHIPUAIBot原生支持工具调用，不需要增强。
    
    Args:
        bot_instance: 要增强的Bot实例
        
    Returns:
        增强后的Bot实例
    """
    # 检查Bot是否已有工具调用支持
    if hasattr(bot_instance, 'call_with_tools'):
        # Bot已经有工具调用能力（如ZHIPUAIBot）
        logger.debug(f"[AgentBridge] {type(bot_instance).__name__} already has native tool calling support")
        return bot_instance

    # 创建一个动态增强的混合类
    # 同时继承原Bot类和OpenAICompatibleBot
    class EnhancedBot(bot_instance.__class__, OpenAICompatibleBot):
        """
        动态增强的Bot类，结合了原Bot和OpenAI兼容工具调用能力
        """

        def get_api_config(self):
            """
            从常见配置模式推断API配置
            大多数OpenAI兼容的Bot使用类似的配置方式
            """
            # 导入配置
            from config import conf

            # 返回API配置字典
            return {
                'api_key': conf().get("open_ai_api_key"),  # API密钥
                'api_base': conf().get("open_ai_api_base"),  # API地址
                'model': conf().get("model", "gpt-3.5-turbo"),  # 模型名称
                'default_temperature': conf().get("temperature", 0.9),  # 温度参数
                'default_top_p': conf().get("top_p", 1.0),  # top_p参数
                'default_frequency_penalty': conf().get("frequency_penalty", 0.0),  # 频率惩罚
                'default_presence_penalty': conf().get("presence_penalty", 0.0),  # 存在惩罚
            }

    # 动态修改Bot实例的类为增强版本
    bot_instance.__class__ = EnhancedBot
    
    # 记录日志
    logger.info(
        f"[AgentBridge] Enhanced {bot_instance.__class__.__bases__[0].__name__} with OpenAI-compatible tool calling")

    return bot_instance


class AgentLLMModel(LLMModel):
    """
    LLM模型适配器，使用COW现有的Bot基础设施
    
    这个类充当Agent系统与COW Bot系统之间的桥梁：
    - Agent系统调用AgentLLMModel进行推理
    - AgentLLMModel内部调用COW的Bot（如ChatGPTBot、BaiduWenxinBot等）
    - 支持工具调用（Tool Calling）功能
    
    属性：
    - bridge: COW的Bridge实例
    - bot_type: Bot类型标识
    - _bot: 缓存的Bot实例
    - _bot_model: 当前Bot使用的模型（用于检测模型变化）
    """

    # 模型名到Bot类型的映射表
    _MODEL_BOT_TYPE_MAP = {
        "wenxin": const.BAIDU, "wenxin-4": const.BAIDU,  # 文心一言
        "xunfei": const.XUNFEI,  # 讯飞星火
        const.QWEN: const.QWEN,  # 通义千问
        const.MODELSCOPE: const.MODELSCOPE,  # ModelScope
    }
    
    # 模型前缀到Bot类型的映射列表（按顺序匹配）
    _MODEL_PREFIX_MAP = [
        ("qwen", const.QWEN_DASHSCOPE), ("qwq", const.QWEN_DASHSCOPE), ("qvq", const.QWEN_DASHSCOPE),  # 通义千问系列
        ("gemini", const.GEMINI),  # Google Gemini
        ("glm", const.ZHIPU_AI),  # 智谱GLM
        ("claude", const.CLAUDEAPI),  # Anthropic Claude
        ("moonshot", const.MOONSHOT), ("kimi", const.MOONSHOT),  # Moonshot/Kimi
        ("doubao", const.DOUBAO),  # 字节豆包
    ]

    def __init__(self, bridge: Bridge, bot_type: str = "chat"):
        """
        初始化AgentLLMModel
        
        Args:
            bridge: COW的Bridge实例
            bot_type: Bot类型，默认为"chat"
        """
        # 导入配置
        from config import conf
        
        # 调用父类初始化，设置默认模型
        super().__init__(model=conf().get("model", const.GPT_41))
        
        # 保存Bridge引用
        self.bridge = bridge
        
        # 保存Bot类型
        self.bot_type = bot_type
        
        # 初始化Bot实例为None（懒加载）
        self._bot = None
        
        # 记录当前Bot使用的模型
        self._bot_model = None

    @property
    def model(self):
        """
        获取当前模型名称（属性 getter）
        
        Returns:
            str: 模型名称
        """
        from config import conf
        return conf().get("model", const.GPT_41)

    @model.setter
    def model(self, value):
        """
        设置模型名称（属性 setter）
        
        这里什么都不做，模型更改通过重新创建Bot实例实现
        """
        pass

    def _resolve_bot_type(self, model_name: str) -> str:
        """
        从模型名解析Bot类型，逻辑与Bridge.__init__一致
        
        根据模型名称推断应该使用哪个Bot进行推理。
        支持多种模型映射规则。
        
        Args:
            model_name: 模型名称
            
        Returns:
            str: Bot类型标识
        """
        from config import conf

        # 优先检查LinkAI配置
        if conf().get("use_linkai", False) and conf().get("linkai_api_key"):
            return const.LINKAI
            
        # 检查自定义Bot类型配置
        configured_bot_type = conf().get("bot_type")
        if configured_bot_type:
            return configured_bot_type
       
        # 模型名为空或无效，默认使用OpenAI
        if not model_name or not isinstance(model_name, str):
            return const.OPENAI
            
        # 直接匹配
        if model_name in self._MODEL_BOT_TYPE_MAP:
            return self._MODEL_BOT_TYPE_MAP[model_name]
            
        # MiniMax模型匹配
        if model_name.lower().startswith("minimax") or model_name in ["abab6.5-chat"]:
            return const.MiniMax
            
        # 通义千问特定模型
        if model_name in [const.QWEN_TURBO, const.QWEN_PLUS, const.QWEN_MAX]:
            return const.QWEN_DASHSCOPE
            
        # Moonshot特定模型
        if model_name in [const.MOONSHOT, "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]:
            return const.MOONSHOT
            
        # DeepSeek模型
        if model_name in [const.DEEPSEEK_CHAT, const.DEEPSEEK_REASONER]:
            return const.OPENAI
            
        # 前缀匹配
        for prefix, btype in self._MODEL_PREFIX_MAP:
            if model_name.startswith(prefix):
                return btype
                
        # 默认使用OpenAI
        return const.OPENAI

    @property
    def bot(self):
        """
        懒加载Bot实例，当模型变化时重新创建
        
        这是一个延迟初始化机制：
        - 首次访问时创建Bot
        - 当模型变化时重新创建Bot
        
        Returns:
            Bot实例
        """
        from models.bot_factory import create_bot
        
        # 获取当前模型
        cur_model = self.model
        
        # 判断是否需要创建/重新创建Bot
        if self._bot is None or self._bot_model != cur_model:
            # 解析Bot类型
            bot_type = self._resolve_bot_type(cur_model)
            
            # 创建Bot实例
            self._bot = create_bot(bot_type)
            
            # 动态增强工具调用能力
            self._bot = add_openai_compatible_support(self._bot)
            
            # 记录当前模型
            self._bot_model = cur_model
            
        return self._bot

    def call(self, request: LLMRequest):
        """
        调用模型（非流式）
        
        使用COW的Bot基础设施进行非流式推理。
        
        Args:
            request: LLMRequest请求对象
            
        Returns:
            格式化后的响应
        """
        try:
            # 检查Bot是否支持工具调用
            if hasattr(self.bot, 'call_with_tools'):
                # 使用工具调用
                kwargs = {
                    'messages': request.messages,  # 消息历史
                    'tools': getattr(request, 'tools', None),  # 工具定义
                    'stream': False,  # 非流式
                    'model': self.model  # 模型名称
                }
                
                # 只在明确设置时传递max_tokens
                if request.max_tokens is not None:
                    kwargs['max_tokens'] = request.max_tokens
                
                # 提取系统提示词
                system_prompt = getattr(request, 'system', None)
                if system_prompt:
                    kwargs['system'] = system_prompt
                
                # 调用Bot
                response = self.bot.call_with_tools(**kwargs)
                return self._format_response(response)
            else:
                # 回退实现（尚未实现）
                raise NotImplementedError("Regular call not implemented yet")
                
        except Exception as e:
            logger.error(f"AgentLLMModel call error: {e}")
            raise
    
    def call_stream(self, request: LLMRequest):
        """
        调用模型（流式）
        
        使用COW的Bot基础设施进行流式推理。
        这是Agent模式的主要推理方式。
        
        Args:
            request: LLMRequest请求对象
            
        Yields:
            格式化后的流式响应块
        """
        try:
            # 检查Bot是否支持工具调用
            if hasattr(self.bot, 'call_with_tools'):
                # 提取系统提示词
                system_prompt = getattr(request, 'system', None)

                # 构建调用参数
                kwargs = {
                    'messages': request.messages,
                    'tools': getattr(request, 'tools', None),
                    'stream': True,  # 流式
                    'model': self.model
                }

                # 只在明确设置时传递max_tokens
                if request.max_tokens is not None:
                    kwargs['max_tokens'] = request.max_tokens

                # 添加系统提示词
                if system_prompt:
                    kwargs['system'] = system_prompt

                # 传递channel_type用于LinkAI追踪
                channel_type = getattr(self, 'channel_type', None)
                if channel_type:
                    kwargs['channel_type'] = channel_type

                # 获取流式响应
                stream = self.bot.call_with_tools(**kwargs)
                
                # 转换流格式并yield
                for chunk in stream:
                    yield self._format_stream_chunk(chunk)
            else:
                bot_type = type(self.bot).__name__
                raise NotImplementedError(f"Bot {bot_type} does not support call_with_tools. Please add the method.")
                
        except Exception as e:
            logger.error(f"AgentLLMModel call_stream error: {e}", exc_info=True)
            raise
    
    def _format_response(self, response):
        """
        格式化响应
        
        用于将Claude等模型的响应格式转换为标准格式。
        
        Args:
            response: 原始响应
            
        Returns:
            格式化后的响应
        """
        # 目前直接返回，可能需要根据具体模型实现格式化逻辑
        return response
    
    def _format_stream_chunk(self, chunk):
        """
        格式化流式响应块
        
        用于将Claude等模型的流式响应块转换为标准格式。
        
        Args:
            chunk: 原始流块
            
        Returns:
            格式化后的流块
        """
        # 目前直接返回，可能需要根据具体模型实现格式化逻辑
        return chunk


class AgentBridge:
    """
    Agent桥接类，将超级Agent系统与COW集成
    
    核心功能：
    - 管理多个Agent实例（每个会话一个），实现会话隔离
    - 处理Agent与COW其他组件的交互
    - 处理事件回调和消息持久化
    - 支持工具调用和技能系统
    
    属性：
    - bridge: COW的Bridge实例
    - agents: 会话ID到Agent实例的映射
    - default_agent: 默认Agent实例（向后兼容）
    - agent: 当前Agent实例
    - scheduler_initialized: 调度器是否已初始化
    - initializer: Agent初始化器
    """
    
    def __init__(self, bridge: Bridge):
        """
        初始化AgentBridge
        
        Args:
            bridge: COW的Bridge实例
        """
        # 保存Bridge引用
        self.bridge = bridge
        
        # 存储Agent实例的字典：session_id -> Agent实例
        self.agents = {}
        
        # 默认Agent实例（用于向后兼容，无session_id时使用）
        self.default_agent = None
        
        # 当前Agent实例
        self.agent: Optional[Agent] = None
        
        # 调度器初始化标志
        self.scheduler_initialized = False
        
        # 创建初始化器实例
        self.initializer = AgentInitializer(bridge, self)
        
    def create_agent(self, system_prompt: str, tools: List = None, **kwargs) -> Agent:
        """
        创建超级Agent实例
        
        这是创建Agent的核心方法，会：
        1. 创建使用COW Bot基础设施的LLM模型
        2. 加载工具（如果未提供）
        3. 创建Agent实例并配置各种参数
        
        Args:
            system_prompt: 系统提示词
            tools: 工具列表（可选）
            **kwargs: 额外参数，如description、max_steps、output_mode等
            
        Returns:
            Agent实例
        """
        # 使用COW的Bot基础设施创建LLM模型
        model = AgentLLMModel(self.bridge)
        
        # 如果没有提供工具，加载所有可用工具
        if tools is None:
            # 使用ToolManager加载所有可用工具
            from agent.tools import ToolManager
            tool_manager = ToolManager()
            tool_manager.load_tools()
            
            # 创建工具实例列表
            tools = []
            for tool_name in tool_manager.tool_classes.keys():
                try:
                    # 创建工具实例
                    tool = tool_manager.create_tool(tool_name)
                    if tool:
                        tools.append(tool)
                except Exception as e:
                    logger.warning(f"[AgentBridge] Failed to load tool {tool_name}: {e}")
        
        # 创建Agent实例
        agent = Agent(
            system_prompt=system_prompt,  # 系统提示词
            description=kwargs.get("description", "AI Super Agent"),  # Agent描述
            model=model,  # LLM模型
            tools=tools,  # 工具列表
            max_steps=kwargs.get("max_steps", 15),  # 最大推理步数
            output_mode=kwargs.get("output_mode", "logger"),  # 输出模式
            workspace_dir=kwargs.get("workspace_dir"),  # 工作目录
            skill_manager=kwargs.get("skill_manager"),  # 技能管理器
            enable_skills=kwargs.get("enable_skills", True),  # 是否启用技能
            memory_manager=kwargs.get("memory_manager"),  # 记忆管理器
            max_context_tokens=kwargs.get("max_context_tokens"),  # 最大上下文token数
            context_reserve_tokens=kwargs.get("context_reserve_tokens"),  # 保留token数
            runtime_info=kwargs.get("runtime_info"),  # 运行时信息
        )

        # 记录技能加载详情
        if agent.skill_manager:
            logger.debug(f"[AgentBridge] SkillManager initialized with {len(agent.skill_manager.skills)} skills")

        return agent
    
    def get_agent(self, session_id: str = None) -> Optional[Agent]:
        """
        获取指定会话的Agent实例
        
        如果会话不存在，会自动创建Agent实例。
        这是实现会话隔离的关键方法。
        
        Args:
            session_id: 会话标识符（如用户ID）。如果为None，返回默认Agent。
            
        Returns:
            Agent实例
        """
        # 如果没有session_id，使用默认Agent（向后兼容）
        if session_id is None:
            if self.default_agent is None:
                self._init_default_agent()
            return self.default_agent
        
        # 检查该会话是否有Agent实例
        if session_id not in self.agents:
            # 为该会话创建Agent实例
            self._init_agent_for_session(session_id)
        
        return self.agents[session_id]
    
    def _init_default_agent(self):
        """
        初始化默认Agent实例
        
        用于向后兼容场景（无session_id时使用）
        """
        agent = self.initializer.initialize_agent(session_id=None)
        self.default_agent = agent
    
    def _init_agent_for_session(self, session_id: str):
        """
        为特定会话初始化Agent实例
        
        Args:
            session_id: 会话标识符
        """
        agent = self.initializer.initialize_agent(session_id=session_id)
        self.agents[session_id] = agent
    
    def agent_reply(self, query: str, context: Context = None, 
                   on_event=None, clear_history: bool = False) -> Reply:
        """
        使用超级Agent回复用户查询
        
        这是Agent模式的核心入口方法：
        1. 获取或创建会话的Agent实例
        2. 创建事件处理器
        3. 过滤工具（定时任务排除scheduler）
        4. 执行Agent推理
        5. 持久化消息
        6. 处理文件发送
        
        Args:
            query: 用户查询
            context: COW上下文（包含session_id用于用户隔离）
            on_event: 事件回调函数（可选）
            clear_history: 是否清除对话历史
            
        Returns:
            Reply对象
        """
        # 初始化变量
        session_id = None
        agent = None
        
        try:
            # 从context中提取session_id，用于用户隔离
            if context:
                session_id = context.kwargs.get("session_id") or context.get("session_id")
            
            # 获取该会话的Agent实例（如不存在会自动创建）
            agent = self.get_agent(session_id=session_id)
            if not agent:
                return Reply(ReplyType.ERROR, "Failed to initialize super agent")
            
            # 创建事件处理器，用于日志记录和渠道通信
            event_handler = AgentEventHandler(context=context, original_callback=on_event)
            
            # 获取原始工具列表
            original_tools = agent.tools
            filtered_tools = original_tools
            
            # 如果是定时任务执行，排除scheduler工具防止递归
            if context and context.get("is_scheduled_task"):
                filtered_tools = [tool for tool in agent.tools if tool.name != "scheduler"]
                agent.tools = filtered_tools
                logger.info(f"[AgentBridge] Scheduled task execution: excluded scheduler tool ({len(filtered_tools)}/{len(original_tools)} tools)")
            else:
                # 将context附加到scheduler工具
                if context and agent.tools:
                    for tool in agent.tools:
                        if tool.name == "scheduler":
                            try:
                                from agent.tools.scheduler.integration import attach_scheduler_to_tool
                                attach_scheduler_to_tool(tool, context)
                            except Exception as e:
                                logger.warning(f"[AgentBridge] Failed to attach context to scheduler: {e}")
                            break
            
            # 传递channel_type给model，用于LinkAI追踪
            if context and hasattr(agent, 'model'):
                agent.model.channel_type = context.get("channel_type", "")

            # 在Agent上存储session_id，以便executor在严重错误时清除数据库
            agent._current_session_id = session_id

            try:
                # 使用Agent的run_stream方法执行推理
                response = agent.run_stream(
                    user_message=query,
                    on_event=event_handler.handle_event,
                    clear_history=clear_history
                )
            finally:
                # 恢复原始工具列表
                if context and context.get("is_scheduled_task"):
                    agent.tools = original_tools

                # 记录执行摘要
                event_handler.log_summary()

            # 持久化本次运行生成的新消息
            if session_id:
                channel_type = (context.get("channel_type") or "") if context else ""
                new_messages = getattr(agent, '_last_run_new_messages', [])
                if new_messages:
                    self._persist_messages(session_id, list(new_messages), channel_type)
                else:
                    # 检查消息是否被清空（可能是格式错误）
                    with agent.messages_lock:
                        msg_count = len(agent.messages)
                    if msg_count == 0:
                        try:
                            from agent.memory import get_conversation_store
                            get_conversation_store().clear_session(session_id)
                            logger.info(f"[AgentBridge] Cleared DB for recovered session: {session_id}")
                        except Exception as e:
                            logger.warning(f"[AgentBridge] Failed to clear DB after recovery: {e}")
            
            # 检查是否有文件需要发送（来自read工具）
            if hasattr(agent, 'stream_executor') and hasattr(agent.stream_executor, 'files_to_send'):
                files_to_send = agent.stream_executor.files_to_send
                if files_to_send:
                    # 发送第一个文件（目前一次只处理一个）
                    file_info = files_to_send[0]
                    logger.info(f"[AgentBridge] Sending file: {file_info.get('path')}")
                    
                    # 清除文件列表，为下次请求做准备
                    agent.stream_executor.files_to_send = []
                    
                    # 根据文件类型返回文件回复
                    return self._create_file_reply(file_info, response, context)
            
            # 返回文本回复
            return Reply(ReplyType.TEXT, response)
            
        except Exception as e:
            logger.error(f"Agent reply error: {e}")
            # 如果Agent因格式错误/溢出清空了消息，也清空数据库
            if session_id and agent:
                try:
                    with agent.messages_lock:
                        msg_count = len(agent.messages)
                    if msg_count == 0:
                        from agent.memory import get_conversation_store
                        get_conversation_store().clear_session(session_id)
                        logger.info(f"[AgentBridge] Cleared DB for session after error: {session_id}")
                except Exception as db_err:
                    logger.warning(f"[AgentBridge] Failed to clear DB after error: {db_err}")
            return Reply(ReplyType.ERROR, f"Agent error: {str(e)}")
    
    def _create_file_reply(self, file_info: dict, text_response: str, context: Context = None) -> Reply:
        """
        创建文件回复
        
        根据文件类型创建相应的回复对象。
        
        Args:
            file_info: 文件元数据（来自read工具）
            text_response: Agent的文本响应
            context: 上下文对象
            
        Returns:
            Reply对象
        """
        # 获取文件类型和路径
        file_type = file_info.get("file_type", "file")
        file_path = file_info.get("path")
        
        # 图片类型：使用IMAGE_URL类型
        if file_type == "image":
            # 转换为file:// URL供渠道处理
            file_url = f"file://{file_path}"
            logger.info(f"[AgentBridge] Sending image: {file_url}")
            reply = Reply(ReplyType.IMAGE_URL, file_url)
            # 如果有 accompanying text，附加到回复（某些渠道支持文本+图片）
            if text_response:
                reply.text_content = text_response
            return reply
        
        # 文档、视频、音频类型：使用FILE类型
        if file_type in ["document", "video", "audio"]:
            file_url = f"file://{file_path}"
            logger.info(f"[AgentBridge] Sending {file_type}: {file_url}")
            reply = Reply(ReplyType.FILE, file_url)
            reply.file_name = file_info.get("file_name", os.path.basename(file_path))
            # 附加文本内容
            if text_response:
                reply.text_content = text_response
            return reply
        
        # 未知类型：返回文本包含文件信息
        message = text_response or file_info.get("message", "文件已准备")
        message += f"\n\n[文件: {file_info.get('file_name', file_path)}]"
        return Reply(ReplyType.TEXT, message)
    
    def _migrate_config_to_env(self, workspace_root: str):
        """
        将API密钥从config.json迁移到.env文件
        
        如果.env文件中尚未设置，则从config.json读取并写入。
        
        Args:
            workspace_root: 工作目录路径（保留用于兼容性）
        """
        from config import conf
        import os
        
        # 配置键到环境变量名的映射
        key_mapping = {
            "open_ai_api_key": "OPENAI_API_KEY",
            "open_ai_api_base": "OPENAI_API_BASE",
            "gemini_api_key": "GEMINI_API_KEY",
            "claude_api_key": "CLAUDE_API_KEY",
            "linkai_api_key": "LINKAI_API_KEY",
        }
        
        # 使用固定的 secure 位置存储 .env 文件
        env_file = expand_path("~/.cow/.env")
        
        # 从 .env 文件读取现有的环境变量
        existing_env_vars = {}
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, _ = line.split('=', 1)
                            existing_env_vars[key.strip()] = True
            except Exception as e:
                logger.warning(f"[AgentBridge] Failed to read .env file: {e}")
        
        # 检查哪些键需要迁移
        keys_to_migrate = {}
        for config_key, env_key in key_mapping.items():
            # 跳过已存在于 .env 的键
            if env_key in existing_env_vars:
                continue
            
            # 从 config.json 获取值
            value = conf().get(config_key, "")
            if value and value.strip():  # 只迁移非空值
                keys_to_migrate[env_key] = value.strip()
        
        # 如果有要跳过的键，记录日志
        if existing_env_vars:
            logger.debug(f"[AgentBridge] {len(existing_env_vars)} env vars already in .env")
        
        # 将新键写入 .env 文件
        if keys_to_migrate:
            try:
                # 确保 ~/.cow 目录和 .env 文件存在
                env_dir = os.path.dirname(env_file)
                if not os.path.exists(env_dir):
                    os.makedirs(env_dir, exist_ok=True)
                if not os.path.exists(env_file):
                    open(env_file, 'a').close()
                
                # 追加新键
                with open(env_file, 'a', encoding='utf-8') as f:
                    f.write('\n# Auto-migrated from config.json\n')
                    for key, value in keys_to_migrate.items():
                        f.write(f'{key}={value}\n')
                        # 同时在当前进程中设置
                        os.environ[key] = value
                
                logger.info(f"[AgentBridge] Migrated {len(keys_to_migrate)} API keys from config.json to .env: {list(keys_to_migrate.keys())}")
            except Exception as e:
                logger.warning(f"[AgentBridge] Failed to migrate API keys: {e}")
    
    def _persist_messages(
        self, session_id: str, new_messages: list, channel_type: str = ""
    ) -> None:
        """
        持久化新消息到对话存储
        
        每次Agent运行后将新消息保存到数据库。
        失败会被记录但不会传播，不应中断回复。
        
        Args:
            session_id: 会话标识符
            new_messages: 新消息列表
            channel_type: 渠道类型
        """
        if not new_messages:
            return
        try:
            from config import conf
            # 检查是否启用了对话持久化
            if not conf().get("conversation_persistence", True):
                return
        except Exception:
            pass
        try:
            from agent.memory import get_conversation_store
            get_conversation_store().append_messages(
                session_id, new_messages, channel_type=channel_type
            )
        except Exception as e:
            logger.warning(
                f"[AgentBridge] Failed to persist messages for session={session_id}: {e}"
            )

    def clear_session(self, session_id: str):
        """
        清除特定会话的Agent和对话历史
        
        Args:
            session_id: 要清除的会话标识符
        """
        if session_id in self.agents:
            logger.info(f"[AgentBridge] Clearing session: {session_id}")
            del self.agents[session_id]
    
    def clear_all_sessions(self):
        """
        清除所有Agent会话
        """
        logger.info(f"[AgentBridge] Clearing all sessions ({len(self.agents)} total)")
        self.agents.clear()
        self.default_agent = None
    
    def refresh_all_skills(self) -> int:
        """
        刷新所有Agent实例中的技能和条件工具
        
        在环境变量变更后调用，允许热重载而无需重启。
        
        Returns:
            刷新的Agent实例数量
        """
        import os
        from dotenv import load_dotenv
        from config import conf

        # 从 .env 文件重新加载环境变量
        workspace_root = expand_path(conf().get("agent_workspace", "~/cow"))
        env_file = os.path.join(workspace_root, '.env')

        if os.path.exists(env_file):
            load_dotenv(env_file, override=True)
            logger.info(f"[AgentBridge] Reloaded environment variables from {env_file}")

        refreshed_count = 0

        # 收集所有要刷新的Agent实例
        agents_to_refresh = []
        if self.default_agent:
            agents_to_refresh.append(("default", self.default_agent))
        for session_id, agent in self.agents.items():
            agents_to_refresh.append((session_id, agent))

        for label, agent in agents_to_refresh:
            # 刷新技能
            if hasattr(agent, 'skill_manager') and agent.skill_manager:
                agent.skill_manager.refresh_skills()

            # 刷新条件工具（如 web_search 依赖 API keys）
            self._refresh_conditional_tools(agent)

            refreshed_count += 1

        if refreshed_count > 0:
            logger.info(f"[AgentBridge] Refreshed skills & tools in {refreshed_count} agent instance(s)")

        return refreshed_count

    @staticmethod
    def _refresh_conditional_tools(agent):
        """
        根据当前环境变量添加或移除条件工具
        
        例如：web_search 应该在设置了 BOCHA_API_KEY 或 LINKAI_API_KEY 时才存在。
        
        Args:
            agent: Agent实例
        """
        try:
            from agent.tools.web_search.web_search import WebSearch

            # 检查是否已有web_search工具
            has_tool = any(t.name == "web_search" for t in agent.tools)
            
            # 检查web_search是否可用（API key是否设置）
            available = WebSearch.is_available()

            if available and not has_tool:
                # API key已添加 - 注入工具
                tool = WebSearch()
                tool.model = agent.model
                agent.tools.append(tool)
                logger.info("[AgentBridge] web_search tool added (API key now available)")
            elif not available and has_tool:
                # API key已移除 - 移除工具
                agent.tools = [t for t in agent.tools if t.name != "web_search"]
                logger.info("[AgentBridge] web_search tool removed (API key no longer available)")
        except Exception as e:
            logger.debug(f"[AgentBridge] Failed to refresh conditional tools: {e}")
