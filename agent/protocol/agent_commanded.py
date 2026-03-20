# -*- coding: utf-8 -*-
"""
Agent 智能体核心类

这是项目的 Agent 核心模块，封装了智能体的所有功能：
1. 多轮对话管理（消息历史）
2. 工具调用（Function Calling）
3. 流式输出
4. 技能系统（Skills）集成
5. 记忆管理（Memory Manager）
6. 上下文窗口和Token管理
7. 后处理工具执行

Agent 是项目的核心大脑，负责：
1. 接收用户消息
2. 构建完整的系统提示词（包含技能、工具列表、运行时信息）
3. 调用 AgentStreamExecutor 执行流式推理循环
4. 管理对话历史和工具调用历史
5. 执行后处理工具（如文件发送）

典型使用流程：
    agent = Agent(system_prompt="你是一个助手", model=llm_model, tools=[...])
    response = agent.run_stream("用户消息", on_event=callback)
"""

# 导入JSON模块，用于序列化和反序列化
import json

# 导入操作系统模块，用于路径操作等
import os

# 导入时间模块
import time

# 导入线程模块，用于线程安全的操作
import threading

# 导入日志模块
from common.log import logger

# 导入协议模块的数据模型
from agent.protocol.models import LLMRequest, LLMModel

# 导入Agent流式执行器
from agent.protocol.agent_stream import AgentStreamExecutor

# 导入结果模型
from agent.protocol.result import AgentAction, AgentActionType, ToolResult, AgentResult

# 导入工具基类和工具阶段枚举
from agent.tools.base_tool import BaseTool, ToolStage


class Agent:
    """
    Agent 智能体核心类
    
    这是项目的核心智能体实现，封装了与LLM交互的所有逻辑。
    
    主要功能：
    1. 系统提示词管理：基础提示词 + 工具列表 + 运行时信息 + 技能列表
    2. 消息历史管理：线程安全的消息列表，支持多轮对话
    3. 工具管理：添加、移除工具，动态构建工具列表
    4. 技能管理：集成SkillManager，支持动态加载技能
    5. 流式执行：通过AgentStreamExecutor实现流式推理
    6. 后处理工具：在主流程完成后执行额外操作（如发送文件）
    7. 上下文管理：智能裁剪上下文，避免溢出
    
    属性说明：
    - name: Agent名称
    - system_prompt: 系统提示词基础内容
    - description: Agent描述
    - model: LLM模型实例
    - tools: 工具列表
    - max_steps: 最大推理步数
    - max_context_tokens: 最大上下文Token数
    - messages: 对话历史列表
    - messages_lock: 线程锁，保护消息列表
    - memory_manager: 记忆管理器
    - skill_manager: 技能管理器
    - enable_skills: 是否启用技能
    - runtime_info: 运行时信息（如当前时间、模型名等）
    """
    
    def __init__(self, system_prompt: str, description: str = "AI Agent", model: LLMModel = None,
                 tools=None, output_mode="print", max_steps=100, max_context_tokens=None, 
                 context_reserve_tokens=None, memory_manager=None, name: str = None,
                 workspace_dir: str = None, skill_manager=None, enable_skills: bool = True,
                 runtime_info: dict = None):
        """
        Agent 初始化方法
        
        创建一个新的Agent实例，配置所有参数。
        
        Args:
            system_prompt: 系统提示词，定义Agent的行为和能力
            description: Agent的描述信息
            model: LLM模型实例（必须）
            tools: 可用的工具列表
            output_mode: 输出模式，"print"输出到控制台，"logger"输出到日志
            max_steps: 最大推理步数，默认100
            max_context_tokens: 最大上下文Token数，默认根据模型自动计算
            context_reserve_tokens: 为新请求预留的Token数
            memory_manager: 记忆管理器实例
            name: Agent名称（已废弃）
            workspace_dir: 工作目录，用于技能加载
            skill_manager: 技能管理器实例
            enable_skills: 是否启用技能，默认True
            runtime_info: 运行时信息字典（包含_get_current_time等）
        """
        # Agent名称
        self.name = name or "Agent"
        
        # 系统提示词
        self.system_prompt = system_prompt
        
        # LLM模型实例
        self.model: LLMModel = model
        
        # Agent描述
        self.description = description
        
        # 工具列表
        self.tools: list = []
        
        # 最大工具调用步数，默认100
        self.max_steps = max_steps
        
        # 最大上下文Token数
        self.max_context_tokens = max_context_tokens
        
        # 为新请求预留的Token数
        self.context_reserve_tokens = context_reserve_tokens
        
        # 捕获的动作列表
        self.captured_actions = []
        
        # 输出模式
        self.output_mode = output_mode
        
        # 上次API调用的使用统计
        self.last_usage = None
        
        # 对话历史（流式模式统一使用）
        self.messages = []
        
        # 线程锁，保护消息列表的并发访问
        self.messages_lock = threading.Lock()
        
        # 记忆管理器
        self.memory_manager = memory_manager
        
        # 工作目录
        self.workspace_dir = workspace_dir
        
        # 技能启用标志
        self.enable_skills = enable_skills
        
        # 运行时信息
        self.runtime_info = runtime_info
        
        # ========== 初始化技能管理器 ==========
        self.skill_manager = None
        
        # 如果启用技能
        if enable_skills:
            # 如果传入了skill_manager，直接使用
            if skill_manager:
                self.skill_manager = skill_manager
            else:
                # 自动创建skill_manager
                try:
                    from agent.skills import SkillManager
                    
                    # 构建技能目录路径
                    custom_dir = os.path.join(workspace_dir, "skills") if workspace_dir else None
                    
                    # 创建技能管理器
                    self.skill_manager = SkillManager(custom_dir=custom_dir)
                    
                    logger.debug(f"Initialized SkillManager with {len(self.skill_manager.skills)} skills")
                except Exception as e:
                    logger.warning(f"Failed to initialize SkillManager: {e}")
        
        # 如果提供了工具列表，添加工具
        if tools:
            for tool in tools:
                self.add_tool(tool)

    def add_tool(self, tool: BaseTool):
        """
        添加工具到Agent
        
        Args:
            tool: 工具实例（BaseTool或子类）
        """
        # 如果工具已经是实例，直接使用
        tool.model = self.model
        self.tools.append(tool)

    def get_skills_prompt(self, skill_filter=None) -> str:
        """
        获取技能提示词
        
        构建技能相关的提示词片段，供加入系统提示词。
        
        Args:
            skill_filter: 可选的技能名称过滤列表
            
        Returns:
            格式化的技能提示词字符串，或空字符串
        """
        # 如果没有技能管理器，返回空
        if not self.skill_manager:
            return ""
        
        try:
            return self.skill_manager.build_skills_prompt(skill_filter=skill_filter)
        except Exception as e:
            logger.warning(f"Failed to build skills prompt: {e}")
            return ""
    
    def get_full_system_prompt(self, skill_filter=None) -> str:
        """
        获取完整的系统提示词
        
        组合以下部分：
        1. 基础系统提示词
        2. 工具系统部分（重建以反映当前self.tools）
        3. 运行时信息部分（动态更新时间）
        4. 技能部分（动态加载技能）
        
        注意：技能现在由PromptBuilder构建到系统提示词中，
        此方法仅返回基础提示词。为保持向后兼容而保留。
        
        Args:
            skill_filter: 可选的技能名称过滤列表（已废弃）
            
        Returns:
            完整的系统提示词
        """
        # 从基础提示词开始
        prompt = self.system_prompt

        # 重建工具列表部分，反映当前self.tools
        # 处理动态添加/移除的条件工具（如web_search）
        prompt = self._rebuild_tool_list_section(prompt)

        # 如果runtime_info包含动态时间函数，重建运行时部分
        if self.runtime_info and callable(self.runtime_info.get('_get_current_time')):
            prompt = self._rebuild_runtime_section(prompt)

        # 重建技能部分，反映新安装/移除的技能
        if self.skill_manager:
            prompt = self._rebuild_skills_section(prompt)

        return prompt
    
    def _rebuild_runtime_section(self, prompt: str) -> str:
        """
        重建运行时信息部分
        
        动态更新运行时信息，通过调用_get_current_time函数获取当前时间。
        
        Args:
            prompt: 原始系统提示词
            
        Returns:
            更新后的系统提示词
        """
        try:
            # 动态获取当前时间
            time_info = self.runtime_info['_get_current_time']()
            
            # 构建新的运行时信息部分
            runtime_lines = [
                "\n## 运行时信息\n",
                "\n",
                f"当前时间: {time_info['time']} {time_info['weekday']} ({time_info['timezone']})\n",
                "\n"
            ]
            
            # 添加其他运行时信息
            runtime_parts = []
            if self.runtime_info.get("model"):
                runtime_parts.append(f"模型={self.runtime_info['model']}")
            if self.runtime_info.get("workspace"):
                # Windows路径的反斜杠替换为正斜杠
                workspace_path = str(self.runtime_info['workspace']).replace('\\', '/')
                runtime_parts.append(f"工作空间={workspace_path}")
            if self.runtime_info.get("channel") and self.runtime_info.get("channel") != "web":
                runtime_parts.append(f"渠道={self.runtime_info['channel']}")
            
            if runtime_parts:
                runtime_lines.append("运行时: " + " | ".join(runtime_parts) + "\n")
                runtime_lines.append("\n")
            
            new_runtime_section = "".join(runtime_lines)
            
            # 查找并替换运行时信息部分
            import re
            pattern = r'\n## 运行时信息\s*\n.*?(?=\n##|\Z)'
            _repl = new_runtime_section.rstrip('\n')
            updated_prompt = re.sub(pattern, lambda m: _repl, prompt, flags=re.DOTALL)
            
            return updated_prompt
        except Exception as e:
            logger.warning(f"Failed to rebuild runtime section: {e}")
            return prompt

    def _rebuild_skills_section(self, prompt: str) -> str:
        """
        重建技能部分
        
        重建<available_skills>块，以便反映新安装或移除的技能，
        无需重新创建Agent。
        
        Args:
            prompt: 原始系统提示词
            
        Returns:
            更新后的系统提示词
        """
        try:
            import re
            
            # 刷新技能列表
            self.skill_manager.refresh_skills()
            
            # 构建新的技能XML
            new_skills_xml = self.skill_manager.build_skills_prompt()

            # 查找旧的技能块
            old_block_pattern = r'<available_skills>.*?</available_skills>'
            has_old_block = re.search(old_block_pattern, prompt, flags=re.DOTALL)

            # 从提示词中提取新的<available_skills>...</available_skills>标签
            new_block = ""
            if new_skills_xml and new_skills_xml.strip():
                m = re.search(old_block_pattern, new_skills_xml, flags=re.DOTALL)
                if m:
                    new_block = m.group(0)

            if has_old_block:
                # 替换旧块
                replacement = new_block or "<available_skills>\n</available_skills>"
                prompt = re.sub(old_block_pattern, lambda m: replacement, prompt, flags=re.DOTALL)
            elif new_block:
                # 如果没有旧块但有新块，插入
                skills_header = "以下是可用技能："
                idx = prompt.find(skills_header)
                if idx != -1:
                    insert_pos = idx + len(skills_header)
                    prompt = prompt[:insert_pos] + "\n" + new_block + prompt[insert_pos:]
        except Exception as e:
            logger.warning(f"Failed to rebuild skills section: {e}")
        return prompt

    def _rebuild_tool_list_section(self, prompt: str) -> str:
        """
        重建工具列表部分
        
        重建"## 工具系统"部分，使其始终反映当前的self.tools，
        处理条件工具（如web_search）的动态添加/移除。
        
        Args:
            prompt: 原始系统提示词
            
        Returns:
            更新后的系统提示词
        """
        import re
        from agent.prompt.builder import _build_tooling_section

        try:
            if not self.tools:
                return prompt

            # 构建新的工具部分
            new_lines = _build_tooling_section(self.tools, "zh")
            new_section = "\n".join(new_lines).rstrip("\n")

            # 替换现有的工具部分
            pattern = r'## 工具系统\s*\n.*?(?=\n## |\Z)'
            updated = re.sub(pattern, lambda m: new_section, prompt, count=1, flags=re.DOTALL)
            return updated
        except Exception as e:
            logger.warning(f"Failed to rebuild tool list section: {e}")
            return prompt

    def refresh_skills(self):
        """
        刷新加载的技能
        """
        if self.skill_manager:
            self.skill_manager.refresh_skills()
            logger.info(f"Refreshed skills: {len(self.skill_manager.skills)} skills loaded")
    
    def list_skills(self):
        """
        列出所有加载的技能
        
        Returns:
            技能条目列表，或空列表
        """
        if not self.skill_manager:
            return []
        return self.skill_manager.list_skills()

    def _get_model_context_window(self) -> int:
        """
        获取模型的上下文窗口大小（Token数）
        
        根据模型名自动检测。
        
        模型上下文窗口：
        - Claude 3.5/3.7 Sonnet: 200K tokens
        - Claude 3 Opus: 200K tokens
        - GPT-4 Turbo/128K: 128K tokens
        - GPT-4: 8K-32K tokens
        - GPT-3.5: 16K tokens
        - DeepSeek: 64K tokens
        
        Returns:
            上下文窗口大小（Token数）
        """
        if self.model and hasattr(self.model, 'model'):
            model_name = self.model.model.lower()

            # Claude模型 - 200K上下文
            if 'claude-3' in model_name or 'claude-sonnet' in model_name:
                return 200000

            # GPT-4模型
            elif 'gpt-4' in model_name:
                if 'turbo' in model_name or '128k' in model_name:
                    return 128000
                elif '32k' in model_name:
                    return 32000
                else:
                    return 8000

            # GPT-3.5
            elif 'gpt-3.5' in model_name:
                if '16k' in model_name:
                    return 16000
                else:
                    return 4000

            # DeepSeek
            elif 'deepseek' in model_name:
                return 64000
            
            # Gemini模型
            elif 'gemini' in model_name:
                if '2.0' in model_name or 'exp' in model_name:
                    return 2000000  # Gemini 2.0: 2M tokens
                else:
                    return 1000000  # Gemini 1.5: 1M tokens

        # 默认保守值
        return 128000

    def _get_context_reserve_tokens(self) -> int:
        """
        获取为新请求预留的Token数
        
        通过保留缓冲区来防止上下文溢出。
        
        Returns:
            预留的Token数
        """
        if self.context_reserve_tokens is not None:
            return self.context_reserve_tokens

        # 预留上下文窗口的约10%，最小10K，最大200K
        context_window = self._get_model_context_window()
        reserve = int(context_window * 0.1)
        return max(10000, min(200000, reserve))

    def _estimate_message_tokens(self, message: dict) -> int:
        """
        估算消息的Token数
        
        对中文内容使用chars/3，对ASCII内容使用chars/4，
        加上tool_use/tool_result结构的块开销。
        
        Args:
            message: 包含'role'和'content'的消息字典
            
        Returns:
            估算的Token数
        """
        content = message.get('content', '')
        if isinstance(content, str):
            return max(1, self._estimate_text_tokens(content))
        elif isinstance(content, list):
            total_tokens = 0
            for part in content:
                if not isinstance(part, dict):
                    continue
                block_type = part.get('type', '')
                if block_type == 'text':
                    total_tokens += self._estimate_text_tokens(part.get('text', ''))
                elif block_type == 'image':
                    total_tokens += 1200
                elif block_type == 'tool_use':
                    # tool_use 包含id + name + input (JSON编码)
                    total_tokens += 50  # 结构开销
                    input_data = part.get('input', {})
                    if isinstance(input_data, dict):
                        import json
                        input_str = json.dumps(input_data, ensure_ascii=False)
                        total_tokens += self._estimate_text_tokens(input_str)
                elif block_type == 'tool_result':
                    # tool_result 包含tool_use_id + content
                    total_tokens += 30  # 结构开销
                    result_content = part.get('content', '')
                    if isinstance(result_content, str):
                        total_tokens += self._estimate_text_tokens(result_content)
                else:
                    # 未知块类型，保守估算
                    total_tokens += 10
            return max(1, total_tokens)
        return 1

    @staticmethod
    def _estimate_text_tokens(text: str) -> int:
        """
        估算文本字符串的Token数
        
        中文/CJK字符通常每个约1.5个Token，
        ASCII每个约0.25个Token（4字符/Token）。
        使用基于字符混合的加权平均。
        
        Args:
            text: 输入文本
            
        Returns:
            估算的Token数
        """
        if not text:
            return 0
        # 统计非ASCII字符（CJK、emoji等）
        non_ascii = sum(1 for c in text if ord(c) > 127)
        ascii_count = len(text) - non_ascii
        # CJK字符：每个1.5 tokens；ASCII：每字符0.25 tokens
        return int(non_ascii * 1.5 + ascii_count * 0.25) + 1

    def _get_model_context_window(self) -> int:
        """
        获取模型的上下文窗口大小（Token数）
        
        这是_get_model_context_window的重复定义，
        用于确保上下文窗口正确获取。
        
        Returns:
            上下文窗口大小
        """
        if self.model and hasattr(self.model, 'model'):
            model_name = self.model.model.lower()
            # ... 同上
            return 128000
        return 128000

    def _find_tool(self, tool_name: str):
        """
        查找指定名称的工具
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具实例，或None
        """
        for tool in self.tools:
            if tool.name == tool_name:
                # 只有预处理器阶段的工具可以主动调用
                if tool.stage == ToolStage.PRE_PROCESS:
                    tool.model = self.model
                    tool.context = self  # 设置工具上下文
                    return tool
                else:
                    # 如果是后处理工具，返回None防止直接调用
                    logger.warning(f"Tool {tool_name} is a post-process tool and cannot be called directly.")
                    return None
        return None

    def output(self, message="", end="\n"):
        """
        根据模式输出消息
        
        Args:
            message: 消息内容
            end: 结束符
        """
        if self.output_mode == "print":
            print(message, end=end)
        elif message:
            logger.info(message)

    def _execute_post_process_tools(self):
        """
        执行所有后处理阶段的工具
        """
        # 获取所有后处理阶段的工具
        post_process_tools = [tool for tool in self.tools if tool.stage == ToolStage.POST_PROCESS]

        # 执行每个工具
        for tool in post_process_tools:
            # 设置工具上下文
            tool.context = self

            # 记录开始时间用于执行计时
            start_time = time.time()

            # 执行工具（空参数，工具将从上下文提取所需信息）
            result = tool.execute({})

            # 计算执行时间
            execution_time = time.time() - start_time

            # 捕获工具使用以便跟踪
            self.capture_tool_use(
                tool_name=tool.name,
                input_params={},  # 后处理工具通常不带参数
                output=result.result,
                status=result.status,
                error_message=str(result.result) if result.status == "error" else None,
                execution_time=execution_time
            )

            # 记录结果
            if result.status == "success":
                # 以所需格式打印工具执行结果
                self.output(f"\n🛠️ {tool.name}: {json.dumps(result.result)}")
            else:
                # 打印失败
                self.output(f"\n🛠️ {tool.name}: {json.dumps({'status': 'error', 'message': str(result.result)})}")

    def capture_tool_use(self, tool_name, input_params, output, status, thought=None, error_message=None,
                         execution_time=0.0):
        """
        捕获工具使用
        
        记录工具执行的详细信息到captured_actions列表。
        
        Args:
            thought: 思考内容
            tool_name: 工具名称
            input_params: 传递给工具的参数
            output: 工具输出
            status: 执行状态
            error_message: 错误信息（如果失败）
            execution_time: 执行时间
        """
        tool_result = ToolResult(
            tool_name=tool_name,
            input_params=input_params,
            output=output,
            status=status,
            error_message=error_message,
            execution_time=execution_time
        )

        action = AgentAction(
            agent_id=self.id if hasattr(self, 'id') else str(id(self)),
            agent_name=self.name,
            action_type=AgentActionType.TOOL_USE,
            tool_result=tool_result,
            thought=thought
        )

        self.captured_actions.append(action)

        return action

    def run_stream(self, user_message: str, on_event=None, clear_history: bool = False, skill_filter=None) -> str:
        """
        使用流式执行单次Agent任务（基于工具调用）
        
        此方法支持：
        - 流式输出
        - 基于工具调用的多轮推理
        - 事件回调
        - 跨调用的持久化对话历史
        
        Args:
            user_message: 用户消息
            on_event: 事件回调函数 callback(event: dict)
                     event = {"type": str, "timestamp": float, "data": dict}
            clear_history: 如果为True，在此调用前清除对话历史（默认False）
            skill_filter: 此运行中包含的可选技能名称列表
            
        Returns:
            最终响应文本
            
        Example:
            # 带记忆的多轮对话
            response1 = agent.run_stream("我的名字是Alice")
            response2 = agent.run_stream("我叫什么？")  # 会记住Alice

            # 不带记忆的单轮
            response = agent.run_stream("你好", clear_history=True)
        """
        # 如果请求清除历史
        if clear_history:
            with self.messages_lock:
                self.messages = []

        # 获取要使用的模型
        if not self.model:
            raise ValueError("No model available for agent")

        # 获取包含技能的完整系统提示词
        full_system_prompt = self.get_full_system_prompt(skill_filter=skill_filter)

        # 创建消息副本以避免并发修改
        # 记录原始长度以跟踪哪些消息是新增的
        with self.messages_lock:
            messages_copy = self.messages.copy()
            original_length = len(self.messages)

        # 从配置获取max_context_turns
        from config import conf
        max_context_turns = conf().get("agent_max_context_turns", 20)
        
        # 使用复制的消息历史创建流执行器
        executor = AgentStreamExecutor(
            agent=self,
            model=self.model,
            system_prompt=full_system_prompt,
            tools=self.tools,
            max_turns=self.max_steps,
            on_event=on_event,
            messages=messages_copy,  # 传递复制的消息历史
            max_context_turns=max_context_turns
        )

        # 执行
        try:
            response = executor.run_stream(user_message)
        except Exception:
            # 如果执行器清空了自己的消息（上下文溢出/消息格式错误），
            # 同步回Agent自己的消息列表，以便下次请求
            # 从头开始而不是永远遇到相同的溢出
            if len(executor.messages) == 0:
                with self.messages_lock:
                    self.messages.clear()
                    logger.info("[Agent] Cleared Agent message history after executor recovery")
            raise

        # 同步执行器的消息回Agent（线程安全）
        # 如果执行器裁剪了上下文，其消息列表比original_length短，
        # 因此必须替换而不是追加
        with self.messages_lock:
            self.messages = list(executor.messages)
            # 跟踪此运行中添加的消息（用户查询 + 所有助手/工具消息）
            # 裁剪后original_length可能超过executor.messages长度
            trim_adjusted_start = min(original_length, len(executor.messages))
            self._last_run_new_messages = list(executor.messages[trim_adjusted_start:])
        
        # 存储执行器引用以供agent_bridge访问files_to_send
        self.stream_executor = executor

        # 执行所有后处理工具
        self._execute_post_process_tools()

        return response

    def clear_history(self):
        """
        清除对话历史和捕获的动作
        """
        self.messages = []
        self.captured_actions = []
