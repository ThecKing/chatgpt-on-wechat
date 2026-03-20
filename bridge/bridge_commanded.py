# -*- coding: utf-8 -*-
"""
桥接模块（Bride）

这是项目的核心桥接层，类似于一座桥梁，连接了：
- 上层：各种消息渠道（Channel）
- 下层：各种AI模型（Bot）

主要功能：
1. 统一入口：所有渠道都通过Bridge调用AI模型，不需要关心底层是哪个模型
2. Bot工厂：根据配置创建对应的Bot实例（OpenAI、Claude、文心一言等）
3. 模型适配：根据配置中的model字段自动推断Bot类型
4. 单例模式：全局只有一个Bridge实例，避免重复创建Bot
5. Agent支持：集成了Agent模式，可以进行多轮对话和工具调用
6. 扩展能力：支持语音识别、语音合成、翻译等扩展功能

架构位置：
    Channel (消息渠道)
         ↓
       Bridge (桥接层)
         ↓
      Bot (AI模型)
"""

# 从模型工厂导入创建Bot的函数
# create_bot: 根据Bot类型创建对应的Bot实例
from models.bot_factory import create_bot

# 导入上下文模块
# Context: 消息上下文类，封装消息内容和元数据
from bridge.context import Context

# 导入回复模块
# Reply: 回复类，封装回复类型和内容
from bridge.reply import Reply

# 导入常量模块
# const: 包含各种模型类型、渠道类型等常量
from common import const

# 导入日志模块
from common.log import logger

# 导入单例装饰器
# @singleton: 确保全局只有一个Bridge实例
from common.singleton import singleton

# 导入配置模块
from config import conf

# 导入翻译工厂函数
from translate.factory import create_translator

# 导入语音工厂函数
from voice.factory import create_voice


@singleton
class Bridge(object):
    """
    桥接类 - 项目的核心枢纽
    
    作用：连接消息渠道和AI模型，提供统一的接口调用各种AI能力。
    
    主要功能：
    1. 管理Bot实例缓存（单例模式）
    2. 根据配置推断并创建Bot实例
    3. 提供统一的回复获取接口
    4. 支持语音识别、语音合成、翻译等扩展
    5. 支持Agent模式
    
    属性说明：
    - btype: 字典，存储各类型Bot的标识（chat、voice_to_text、text_to_voice、translate）
    - bots: 字典，缓存已创建的Bot实例，避免重复创建
    - chat_bots: 字典，缓存特定类型的聊天Bot
    - _agent_bridge: Agent桥接实例（懒加载）
    """
    
    def __init__(self):
        """
        Bridge初始化方法
        
        初始化时完成：
        1. 设置默认Bot类型映射
        2. 根据配置推断Bot类型（支持多种模型）
        3. 初始化Bot缓存字典
        4. 初始化Agent桥接引用
        """
        # ========== 设置默认Bot类型 ==========
        # 这是一个字典，key是功能类型，value是对应的Bot标识
        # chat: 聊天/对话
        # voice_to_text: 语音识别
        # text_to_voice: 语音合成
        # translate: 翻译
        self.btype = {
            "chat": const.OPENAI,  # 默认使用OpenAI
            "voice_to_text": conf().get("voice_to_text", "openai"),  # 默认语音识别
            "text_to_voice": conf().get("text_to_voice", "google"),   # 默认语音合成
            "translate": conf().get("translate", "baidu"),            # 默认翻译
        }
        
        # ========== 根据配置推断Bot类型 ==========
        # 优先使用bot_type配置（显式指定）
        bot_type = conf().get("bot_type")
        
        if bot_type:
            # 如果显式配置了bot_type，直接使用
            self.btype["chat"] = bot_type
        else:
            # 根据model配置推断Bot类型
            # 从配置中获取model，默认为GPT_4O_MINI
            model_type = conf().get("model") or const.GPT_41_MINI
            
            # ========== 类型安全检查 ==========
            # 确保model_type是字符串，避免后续startswith()调用时出现AttributeError
            # 某些配置解析可能将数字模型名（如"1"）解析为整数
            if not isinstance(model_type, str):
                logger.warning(f"[Bridge] model_type is not a string: {model_type} (type: {type(model_type).__name__}), converting to string")
                model_type = str(model_type)
            
            # ========== 根据模型名推断Bot类型 ==========
            
            # OpenAI原生模型
            if model_type in ["text-davinci-003"]:
                self.btype["chat"] = const.OPEN_AI
            
            # Azure OpenAI
            if conf().get("use_azure_chatgpt", False):
                self.btype["chat"] = const.CHATGPTONAZURE
            
            # 百度文心一言
            if model_type in ["wenxin", "wenxin-4"]:
                self.btype["chat"] = const.BAIDU
            
            # 讯飞星火
            if model_type in ["xunfei"]:
                self.btype["chat"] = const.XUNFEI
            
            # 阿里Qwen（本地部署）
            if model_type in [const.QWEN]:
                self.btype["chat"] = const.QWEN
            
            # 阿里Qwen（DashScope云端）
            if model_type in [const.QWEN_TURBO, const.QWEN_PLUS, const.QWEN_MAX]:
                self.btype["chat"] = const.QWEN_DASHSCOPE
            
            # 支持Qwen3及其他DashScope模型
            # qwen: Qwen系列（如qwen-turbo、qwen-plus）
            # qwq: Qwen推理模型
            # qvq: Qwen视觉模型
            if model_type and (model_type.startswith("qwen") or model_type.startswith("qwq") or model_type.startswith("qvq")):
                self.btype["chat"] = const.QWEN_DASHSCOPE
            
            # Google Gemini
            if model_type and model_type.startswith("gemini"):
                self.btype["chat"] = const.GEMINI
            
            # 智谱GLM
            if model_type and model_type.startswith("glm"):
                self.btype["chat"] = const.ZHIPU_AI
            
            # Anthropic Claude
            if model_type and model_type.startswith("claude"):
                self.btype["chat"] = const.CLAUDEAPI
            
            # 月之暗面Moonshot (Kimi)
            if model_type in [const.MOONSHOT, "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]:
                self.btype["chat"] = const.MOONSHOT
            if model_type and model_type.startswith("kimi"):
                self.btype["chat"] = const.MOONSHOT
            
            # 字节跳动豆包
            if model_type and model_type.startswith("doubao"):
                self.btype["chat"] = const.DOUBAO
            
            # ModelScope（魔搭）
            if model_type in [const.MODELSCOPE]:
                self.btype["chat"] = const.MODELSCOPE
            
            # MiniMax（稀宇科技）
            # 支持 abab6.5-chat、abab6.5 及所有 minimax 开头的模型
            if model_type and (model_type in ["abab6.5-chat", "abab6.5"] or model_type.lower().startswith("minimax")):
                self.btype["chat"] = const.MiniMax
            
            # ========== LinkAI 配置 ==========
            # 如果启用LinkAI且配置了API Key，优先使用LinkAI
            if conf().get("use_linkai") and conf().get("linkai_api_key"):
                self.btype["chat"] = const.LINKAI
                
                # LinkAI也提供语音识别和语音合成
                # 如果没有配置或配置为openai，则使用LinkAI
                if not conf().get("voice_to_text") or conf().get("voice_to_text") in ["openai"]:
                    self.btype["voice_to_text"] = const.LINKAI
                if not conf().get("text_to_voice") or conf().get("text_to_voice") in ["openai", const.TTS_1, const.TTS_1_HD]:
                    self.btype["text_to_voice"] = const.LINKAI
        
        # ========== 初始化Bot缓存 ==========
        
        # bots字典：缓存已创建的Bot实例
        # key: 功能类型（chat、voice_to_text等）
        # value: Bot实例
        self.bots = {}
        
        # chat_bots字典：缓存特定类型的聊天Bot
        # 用于find_chat_bot方法
        self.chat_bots = {}
        
        # _agent_bridge: Agent桥接实例，懒加载
        # 首次调用get_agent_bridge时创建
        self._agent_bridge = None

    def get_bot(self, typename):
        """
        获取Bot实例
        
        根据功能类型获取对应的Bot实例。
        如果实例不存在，则创建并缓存。
        
        这是工厂模式的实现，通过create_bot工厂函数创建具体Bot。
        
        Args:
            typename: 功能类型字符串
                - "chat": 聊天Bot
                - "voice_to_text": 语音识别Bot
                - "text_to_voice": 语音合成Bot
                - "translate": 翻译Bot
                
        Returns:
            对应功能的Bot实例
        """
        # 检查Bot实例是否已缓存
        if self.bots.get(typename) is None:
            # 实例不存在，创建并记录日志
            logger.info("create bot {} for {}".format(self.btype[typename], typename))
            
            # 根据功能类型调用对应的工厂函数创建Bot
            if typename == "text_to_voice":
                # 语音合成
                self.bots[typename] = create_voice(self.btype[typename])
            elif typename == "voice_to_text":
                # 语音识别
                self.bots[typename] = create_voice(self.btype[typename])
            elif typename == "chat":
                # 聊天
                self.bots[typename] = create_bot(self.btype[typename])
            elif typename == "translate":
                # 翻译
                self.bots[typename] = create_translator(self.btype[typename])
                
        # 返回缓存的Bot实例
        return self.bots[typename]

    def get_bot_type(self, typename):
        """
        获取Bot类型标识
        
        返回指定功能对应的Bot类型标识（常量）。
        
        Args:
            typename: 功能类型字符串
            
        Returns:
            Bot类型标识（如const.OPENAI、const.BAIDU等）
        """
        return self.btype[typename]

    def fetch_reply_content(self, query, context: Context) -> Reply:
        """
        获取聊天回复（统一入口）
        
        这是聊天功能的核心入口方法。
        Channel通过调用此方法获取AI的回复。
        
        内部实现：
        1. 获取聊天Bot实例
        2. 调用Bot的reply方法生成回复
        
        Args:
            query: 用户输入的查询/消息
            context: 消息上下文，包含会话信息等
            
        Returns:
            Reply: 回复对象，包含type和content
        """
        # 获取聊天Bot并调用reply方法
        return self.get_bot("chat").reply(query, context)

    def fetch_voice_to_text(self, voiceFile) -> Reply:
        """
        语音识别（统一入口）
        
        将音频文件转换为文字。
        
        内部实现：
        1. 获取语音识别Bot实例
        2. 调用Bot的voiceToText方法
        
        Args:
            voiceFile: 音频文件路径
            
        Returns:
            Reply: 回复对象，type为TEXT，content为识别出的文字
        """
        # 获取语音识别Bot并调用voiceToText方法
        return self.get_bot("voice_to_text").voiceToText(voiceFile)

    def fetch_text_to_voice(self, text) -> Reply:
        """
        语音合成（统一入口）
        
        将文字转换为语音。
        
        内部实现：
        1. 获取语音合成Bot实例
        2. 调用Bot的textToVoice方法
        
        Args:
            text: 要转换的文字
            
        Returns:
            Reply: 回复对象，type为VOICE，content为音频文件路径
        """
        # 获取语音合成Bot并调用textToVoice方法
        return self.get_bot("text_to_voice").textToVoice(text)

    def fetch_translate(self, text, from_lang="", to_lang="en") -> Reply:
        """
        翻译功能（统一入口）
        
        将文字从一种语言翻译到另一种语言。
        
        内部实现：
        1. 获取翻译Bot实例
        2. 调用Bot的translate方法
        
        Args:
            text: 要翻译的文字
            from_lang: 源语言（空字符串表示自动检测）
            to_lang: 目标语言，默认为英语
            
        Returns:
            Reply: 回复对象，type为TEXT，content为翻译结果
        """
        # 获取翻译Bot并调用translate方法
        return self.get_bot("translate").translate(text, from_lang, to_lang)

    def find_chat_bot(self, bot_type: str):
        """
        根据Bot类型查找聊天Bot
        
        与get_bot("chat")不同，这个方法直接根据传入的bot_type创建Bot。
        用于需要明确指定Bot类型的场景。
        
        Args:
            bot_type: Bot类型标识（如const.OPENAI、const.BAIDU等）
            
        Returns:
            对应类型的聊天Bot实例
        """
        # 检查是否已缓存
        if self.chat_bots.get(bot_type) is None:
            # 创建Bot实例并缓存
            self.chat_bots[bot_type] = create_bot(bot_type)
            
        # 返回缓存的Bot实例
        return self.chat_bots.get(bot_type)

    def reset_bot(self):
        """
        重置Bot路由
        
        重新初始化Bridge，相当于重新创建所有Bot实例。
        用于配置变更后需要刷新Bot的场景。
        
        调用此方法后，下次调用get_bot时会重新创建Bot实例。
        """
        # 调用__init__重新初始化
        self.__init__()

    def get_agent_bridge(self):
        """
        获取Agent桥接实例
        
        如果Agent桥接实例不存在，则创建并缓存。
        使用懒加载模式，首次调用时导入AgentBridge类。
        
        Returns:
            AgentBridge: Agent桥接实例
        """
        # 懒加载：首次调用时创建
        if self._agent_bridge is None:
            # 导入AgentBridge类（避免循环导入）
            from bridge.agent_bridge import AgentBridge
            
            # 创建AgentBridge实例，传入Bridge自身
            self._agent_bridge = AgentBridge(self)
            
        # 返回缓存的实例
        return self._agent_bridge

    def fetch_agent_reply(self, query: str, context: Context = None,
                          on_event=None, clear_history: bool = False) -> Reply:
        """
        使用Agent模式获取回复
        
        与普通模式不同，Agent模式支持：
        1. 多轮对话
        2. 工具调用（Function Calling）
        3. 流式输出
        4. 长期记忆
        
        内部实现：
        1. 获取AgentBridge实例
        2. 调用agent_reply方法执行Agent逻辑
        
        Args:
            query: 用户输入的查询/消息
            context: 消息上下文，包含会话信息等
            on_event: 事件回调函数，用于流式输出（如SSE）
            clear_history: 是否清除会话历史，默认False
            
        Returns:
            Reply: Agent生成的回复对象
        """
        # 获取Agent桥接实例
        agent_bridge = self.get_agent_bridge()
        
        # 调用Agent回复方法
        return agent_bridge.agent_reply(query, context, on_event, clear_history)
