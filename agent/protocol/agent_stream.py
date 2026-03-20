# -*- coding: utf-8 -*-
"""
Agent流式执行器模块

这是Agent系统的核心执行器，负责：
1. 与LLM进行流式交互
2. 管理工具调用循环
3. 智能上下文管理（防止溢出）
4. 错误处理和自动重试
5. 消息验证和修复

核心流程：
1. 接收用户消息
2. 调用LLM生成回复
3. 如果LLM调用工具，执行工具
4. 将工具结果返回给LLM
5. 重复步骤2-4直到LLM不再调用工具
6. 返回最终回复

特性：
- 支持多轮推理（Multi-turn Reasoning）
- 自动检测上下文溢出并智能裁剪
- 工具调用失败保护（防止无限循环）
- 支持流式输出
- 事件回调机制
"""

# 导入json模块，用于序列化/反序列化
import json

# 导入时间模块，用于计时
import time

# 导入日志模块
from common.log import logger

# 导入类型提示
from typing import List, Dict, Any, Tuple

# 导入协议模块
from agent.protocol.models import LLMRequest
from agent.protocol.message_utils import sanitize_claude_messages

# 导入工具相关
from agent.tools.base_tool import BaseTool


class AgentStreamExecutor:
    """
    Agent流式执行器类
    
    负责执行Agent的流式推理循环，包括：
    - 调用LLM生成回复
    - 执行工具调用
    - 管理对话上下文
    - 错误处理和重试
    
    属性说明：
    - agent: Agent实例
    - model: LLM模型实例
    - system_prompt: 系统提示词
    - tools: 可用工具字典
    - max_turns: 最大推理轮数
    - messages: 消息历史
    - on_event: 事件回调函数
    """
    
    def __init__(self, agent, model, system_prompt: str, tools: List[BaseTool] = None,
                 max_turns: int = 100, on_event=None, messages: List[Dict] = None,
                 max_context_turns: int = 20):
        """
        初始化AgentStreamExecutor
        
        Args:
            agent: Agent实例
            model: LLM模型实例
            system_prompt: 系统提示词
            tools: 可用工具列表
            max_turns: 最大推理轮数
            on_event: 事件回调函数
            messages: 初始消息历史
            max_context_turns: 最大上下文轮数
        """
        # 保存Agent引用
        self.agent = agent
        
        # LLM模型
        self.model = model
        
        # 系统提示词
        self.system_prompt = system_prompt
        
        # 工具列表（转为字典方便查找）
        self.tools = {}
        if tools:
            for tool in tools:
                self.tools[tool.name] = tool
        
        # 最大推理轮数
        self.max_turns = max_turns
        
        # 事件回调函数
        self.on_event = on_event
        
        # 消息历史
        self.messages = messages or []
        
        # 最大上下文轮数
        self.max_context_turns = max_context_turns
        
        # 待发送文件列表
        self.files_to_send = []
        
        # 工具失败历史（用于检测无限循环）
        # 格式: [(tool_name, args_hash, success), ...]
        self.tool_failure_history = []

    def _emit_event(self, event_type: str, data: Dict = None):
        """
        发送事件回调
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if self.on_event:
            event = {
                "type": event_type,
                "timestamp": time.time(),
                "data": data or {}
            }
            self.on_event(event)

    def _filter_think_tags(self, text: str) -> str:
        """
        过滤think标签
        
        某些LLM（如MiniMax）可能返回think标签包裹的思考过程。
        只移除标签本身，保留思考内容。
        
        Args:
            text: 原始文本
            
        Returns:
            过滤后的文本
        """
        if not text:
            return text
        import re
        # 只移除think标签，保留内容
        text = re.sub(r'<think>', '', text)
        text = re.sub(r'
</think>', '', text)
        return text

    def _hash_args(self, args: dict) -> str:
        """
        生成工具参数的哈希值
        
        Args:
            args: 参数字典
            
        Returns:
            8位哈希字符串
        """
        import hashlib
        # 排序键以确保一致性
        args_str = json.dumps(args, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(args_str.encode()).hexdigest()[:8]
    
    def _check_consecutive_failures(self, tool_name: str, args: dict) -> Tuple[bool, str, bool]:
        """
        检查工具是否连续失败太多次或使用相同参数重复调用
        
        Returns:
            (should_stop, reason, is_critical)
            - should_stop: 是否停止工具执行
            - reason: 停止原因
            - is_critical: 是否终止整个对话（8+次失败）
        """
        args_hash = self._hash_args(args)
        
        # 计算相同参数的连续调用次数（包括成功和失败）
        same_args_calls = 0
        for name, ahash, success in reversed(self.tool_failure_history):
            if name == tool_name and ahash == args_hash:
                same_args_calls += 1
            else:
                break
        
        # 相同参数调用5次则停止（防止无限循环）
        if same_args_calls >= 5:
            return True, f"工具 '{tool_name}' 使用相同参数已被调用 {same_args_calls} 次，停止执行以防止无限循环。", False
        
        # 计算相同参数的连续失败次数
        same_args_failures = 0
        for name, ahash, success in reversed(self.tool_failure_history):
            if name == tool_name and ahash == args_hash:
                if not success:
                    same_args_failures += 1
                else:
                    break
            else:
                break
        
        if same_args_failures >= 3:
            return True, f"工具 '{tool_name}' 使用相同参数连续失败 {same_args_failures} 次，停止执行", False
        
        # 计算同一工具的连续失败次数（任何参数）
        same_tool_failures = 0
        for name, ahash, success in reversed(self.tool_failure_history):
            if name == tool_name:
                if not success:
                    same_tool_failures += 1
                else:
                    break
            else:
                break
        
        # 8次失败 - 硬停止，返回严重错误消息
        if same_tool_failures >= 8:
            return True, f"抱歉，我没能完成这个任务。可能是我理解有误或者当前方法不太合适。建议你：\n• 换个方式描述需求试试\n• 把任务拆分成更小的步骤\n• 或者换个思路来解决", True
        
        # 6次失败警告
        if same_tool_failures >= 6:
            return True, f"工具 '{tool_name}' 连续失败 {same_tool_failures} 次，停止执行", False
        
        return False, "", False
    
    def _record_tool_result(self, tool_name: str, args: dict, success: bool):
        """
        记录工具执行结果，用于失败跟踪
        
        Args:
            tool_name: 工具名称
            args: 工具参数
            success: 是否成功
        """
        args_hash = self._hash_args(args)
        self.tool_failure_history.append((tool_name, args_hash, success))
        # 只保留最近50条记录
        if len(self.tool_failure_history) > 50:
            self.tool_failure_history = self.tool_failure_history[-50:]

    def run_stream(self, user_message: str) -> str:
        """
        执行流式推理循环
        
        Args:
            user_message: 用户消息
            
        Returns:
            最终响应文本
        """
        # 记录用户消息和模型信息
        logger.info(f"🤖 {self.model.model} | 👤 {user_message}")
        
        # 添加用户消息（Claude格式 - 使用内容块）
        self.messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_message
                }
            ]
        })

        # 在推理循环开始前裁剪一次上下文，不要在工具步骤中间裁剪
        # 这确保当前运行中创建的tool_use/tool_result链不会被剥离（会导致LLM循环）
        self._trim_messages()

        # 裁剪后验证：确保消息边界没有孤立的tool_use
        self._validate_and_fix_messages()

        self._emit_event("agent_start")

        final_response = ""
        turn = 0

        try:
            while turn < self.max_turns:
                turn += 1
                logger.info(f"[Agent] 第 {turn} 轮")
                self._emit_event("turn_start", {"turn": turn})

                # 调用LLM（启用空响应重试）
                assistant_msg, tool_calls = self._call_llm_stream(retry_on_empty=True)
                final_response = assistant_msg

                # 没有工具调用，结束循环
                if not tool_calls:
                    # 检查是否返回空响应
                    if not assistant_msg:
                        logger.warning(f"[Agent] LLM返回空响应（重试后）")
                        
                        # 如果之前有工具调用，强制要求LLM生成文本回复
                        if turn > 1:
                            logger.info(f"[Agent] 请求LLM显式回复...")
                            self.messages.append({
                                "role": "user",
                                "content": [{
                                    "type": "text",
                                    "text": "请向用户说明刚才工具执行的结果或回答用户的问题。"
                                }]
                            })
                            assistant_msg, tool_calls = self._call_llm_stream(retry_on_empty=False)
                            final_response = assistant_msg
                            
                            # 还是空，使用fallback
                            if not assistant_msg and not tool_calls:
                                final_response = "抱歉，我暂时无法生成回复。请尝试换一种方式描述你的需求，或稍后再试。"
                    else:
                        logger.info(f"💭 {assistant_msg[:150]}{'...' if len(assistant_msg) > 150 else ''}")
                    
                    logger.debug(f"✅ 完成 (无工具调用)")
                    self._emit_event("turn_end", {
                        "turn": turn,
                        "has_tool_calls": False
                    })
                    break

                # 记录工具调用
                tool_calls_str = []
                for tc in tool_calls:
                    args = tc.get('arguments') or {}
                    if isinstance(args, dict):
                        args_str = ', '.join([f"{k}={v}" for k, v in args.items()])
                        if args_str:
                            tool_calls_str.append(f"{tc['name']}({args_str})")
                        else:
                            tool_calls_str.append(tc['name'])
                    else:
                        tool_calls_str.append(tc['name'])
                logger.info(f"🔧 {', '.join(tool_calls_str)}")

                # 执行工具
                tool_results = []
                tool_result_blocks = []

                try:
                    for tool_call in tool_calls:
                        result = self._execute_tool(tool_call)
                        tool_results.append(result)
                        
                        # 检查是否是待发送文件
                        if result.get("status") == "success" and isinstance(result.get("result"), dict):
                            result_data = result.get("result")
                            if result_data.get("type") == "file_to_send":
                                self.files_to_send.append(result_data)
                                logger.info(f"📎 检测到待发送文件: {result_data.get('file_name', result_data.get('path'))}")
                        
                        # 检查严重错误 - 终止整个对话
                        if result.get("status") == "critical_error":
                            logger.error(f"💥 检测到严重错误，终止对话")
                            final_response = result.get('result', '任务执行失败')
                            return final_response
                        
                        # 记录工具结果
                        status_emoji = "✅" if result.get("status") == "success" else "❌"
                        result_data = result.get('result', '')
                        if isinstance(result_data, (dict, list)):
                            result_str = json.dumps(result_data, ensure_ascii=False)
                        else:
                            result_str = str(result_data)
                        logger.info(f"  {status_emoji} {tool_call['name']} ({result.get('execution_time', 0):.2f}s): {result_str[:200]}...")

                        # 构建工具结果块（Claude格式）
                        is_error = result.get("status") == "error"
                        if is_error:
                            result_content = f"Error: {result.get('result', 'Unknown error')}"
                        elif isinstance(result.get('result'), dict):
                            result_content = json.dumps(result.get('result'), ensure_ascii=False)
                        elif isinstance(result.get('result'), str):
                            result_content = result.get('result')
                        else:
                            result_content = json.dumps(result, ensure_ascii=False)

                        # 截断过大的工具结果
                        MAX_CURRENT_TURN_RESULT_CHARS = 50000
                        if len(result_content) > MAX_CURRENT_TURN_RESULT_CHARS:
                            result_content = result_content[:MAX_CURRENT_TURN_RESULT_CHARS] + \
                                f"\n\n[Output truncated: {len(result_content)} chars]"
                            logger.info(f"📎 截断工具结果: {len(result_content)} -> {MAX_CURRENT_TURN_RESULT_CHARS} chars"

                        tool_result_block = {
                            "type": "tool_result",
                            "tool_use_id": tool_call["id"],
                            "content": result_content
                        }
                        
                        if is_error:
                            tool_result_block["is_error"] = True
                        
                        tool_result_blocks.append(tool_result_block)
                
                finally:
                    # 关键：始终添加工具结果以保持消息历史完整性
                    if tool_result_blocks:
                        self.messages.append({
                            "role": "user",
                            "content": tool_result_blocks
                        })
                        
                        # 检测潜在无限循环
                        if turn >= 3 and len(tool_calls) > 0:
                            tool_name = tool_calls[0]["name"]
                            args_hash = self._hash_args(tool_calls[0]["arguments"])
                            
                            recent_success_count = sum(
                                1 for name, ahash, success in reversed(self.tool_failure_history[-10:])
                                if name == tool_name and ahash == args_hash and success
                            )
                            
                            if recent_success_count >= 3:
                                self.messages.append({
                                    "role": "user",
                                    "content": [{
                                        "type": "text",
                                        "text": "工具已成功执行并返回结果。请基于这些信息向用户做出回复，不要重复调用相同的工具。"
                                    }]
                                })
                    elif tool_calls:
                        # 意外错误 - 创建错误结果
                        emergency_blocks = []
                        for tool_call in tool_calls:
                            emergency_blocks.append({
                                "type": "tool_result",
                                "tool_use_id": tool_call["id"],
                                "content": "Error: Tool execution was interrupted",
                                "is_error": True
                            })
                        self.messages.append({
                            "role": "user",
                            "content": emergency_blocks
                        })

                self._emit_event("turn_end", {
                    "turn": turn,
                    "has_tool_calls": True,
                    "tool_count": len(tool_calls)
                })

            if turn >= self.max_turns:
                logger.warning(f"⚠️ 达到最大决策步数限制: {self.max_turns}")
                
                # 强制模型总结
                prompt_insert_idx = len(self.messages)
                self.messages.append({
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": f"你已经执行了{turn}个决策步骤，达到了单次运行的最大步数限制。请总结一下你目前的执行过程和结果，告诉用户当前的进展情况。不要再调用工具，直接用文字回复。"
                    }]
                })
                
                try:
                    summary_response, summary_tools = self._call_llm_stream(retry_on_empty=False)
                    if summary_response:
                        final_response = summary_response
                except Exception as e:
                    final_response = f"我已经执行了{turn}个决策步骤，达到了单次运行的步数上限。任务可能还未完全完成。"
                finally:
                    if prompt_insert_idx < len(self.messages):
                        self.messages.pop(prompt_insert_idx)

        except Exception as e:
            logger.error(f"❌ Agent执行错误: {e}")
            self._emit_event("error", {"error": str(e)})
            raise

        finally:
            logger.info(f"[Agent] 🏁 完成 ({turn}轮)")
            self._emit_event("agent_end", {"final_response": final_response})

        return final_response

    def _call_llm_stream(self, retry_on_empty=True, retry_count=0, max_retries=3,
                         _overflow_retry: bool = False) -> Tuple[str, List[Dict]]:
        """
        调用LLM进行流式推理，包含自动重试
        
        Args:
            retry_on_empty: 空响应是否重试一次
            retry_count: 当前重试次数
            max_retries: 最大重试次数
            _overflow_retry: 是否是溢出后的重试
            
        Returns:
            (response_text, tool_calls)
        """
        # 验证和修复消息历史
        self._validate_and_fix_messages()

        # 准备消息
        messages = self._prepare_messages()
        turns = self._identify_complete_turns()
        logger.info(f"发送 {len(messages)} 条消息（{len(turns)} 轮）到LLM")

        # 准备工具定义
        tools_schema = None
        if self.tools:
            tools_schema = []
            for tool in self.tools.values():
                tools_schema.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.params
                })

        # 创建请求
        request = LLMRequest(
            messages=messages,
            temperature=0,
            stream=True,
            tools=tools_schema,
            system=self.system_prompt
        )

        self._emit_event("message_start", {"role": "assistant"})

        # 流式响应
        full_content = ""
        tool_calls_buffer = {}
        stop_reason = None

        try:
            stream = self.model.call_stream(request)

            for chunk in stream:
                # 检查错误
                if isinstance(chunk, dict) and chunk.get("error"):
                    error_data = chunk.get("error", {})
                    if isinstance(error_data, dict):
                        error_msg = error_data.get("message", chunk.get("message", "Unknown error"))
                    else:
                        error_msg = chunk.get("message", str(error_data))
                    
                    status_code = chunk.get("status_code", "N/A")
                    
                    # 检查是否是上下文溢出错误
                    error_msg_lower = error_msg.lower()
                    is_overflow = any(keyword in error_msg_lower for keyword in [
                        'context length exceeded', 'maximum context length', 'prompt is too long',
                        'context overflow', 'context window', 'too large', 'exceeds model context',
                    ])
                    
                    if is_overflow:
                        raise Exception(f"[CONTEXT_OVERFLOW] {error_msg}")
                    else:
                        raise Exception(f"{error_msg} (Status: {status_code})")

                # 解析块
                if isinstance(chunk, dict) and chunk.get("choices"):
                    choice = chunk["choices"][0]
                    delta = choice.get("delta", {})
                    
                    finish_reason = choice.get("finish_reason")
                    if finish_reason:
                        stop_reason = finish_reason

                    # 处理文本内容
                    content_delta = delta.get("content") or ""
                    if content_delta:
                        filtered_delta = self._filter_think_tags(content_delta)
                        full_content += filtered_delta
                        if filtered_delta:
                            self._emit_event("message_update", {"delta": filtered_delta})

                    # 处理工具调用
                    if "tool_calls" in delta and delta["tool_calls"]:
                        for tc_delta in delta["tool_calls"]:
                            index = tc_delta.get("index", 0)
                            if index not in tool_calls_buffer:
                                tool_calls_buffer[index] = {"id": "", "name": "", "arguments": ""}
                            if tc_delta.get("id"):
                                tool_calls_buffer[index]["id"] = tc_delta["id"]
                            if "function" in tc_delta:
                                func = tc_delta["function"]
                                if func.get("name"):
                                    tool_calls_buffer[index]["name"] = func["name"]
                                if func.get("arguments"):
                                    tool_calls_buffer[index]["arguments"] += func["arguments"]

        except Exception as e:
            error_str = str(e)
            error_str_lower = error_str.lower()
            
            # 检查上下文溢出
            is_context_overflow = '[context_overflow]' in error_str_lower or any(
                keyword in error_str_lower for keyword in [
                    'context length exceeded', 'maximum context length', 'context overflow'
                ]
            )
            
            # 检查消息格式错误
            is_message_format_error = any(keyword in error_str_lower for keyword in [
                'tool_use', 'tool_result', 'tool_call_id', 'not found', '400'
            ]) and ('400' in error_str_lower or 'invalid' in error_str_lower)
            
            if is_context_overflow or is_message_format_error:
                logger.error(f"💥 {'上下文溢出' if is_context_overflow else '消息格式错误'}: {e}")
                
                if is_context_overflow and self.agent.memory_manager:
                    user_id = getattr(self.agent, '_current_user_id', None)
                    self.agent.memory_manager.flush_memory(
                        messages=self.messages, user_id=user_id,
                        reason="overflow", max_messages=0
                    )

                # 尝试激进裁剪
                if is_context_overflow and not _overflow_retry:
                    trimmed = self._aggressive_trim_for_overflow()
                    if trimmed:
                        logger.warning("🔄 激进裁剪上下文，重试...")
                        return self._call_llm_stream(
                            retry_on_empty=retry_on_empty,
                            retry_count=retry_count,
                            max_retries=max_retries,
                            _overflow_retry=True
                        )

                # 清理并抛出错误
                self.messages.clear()
                self._clear_session_db()
                raise Exception("抱歉，对话历史过长导致上下文溢出。我已清空历史记录，请重新描述你的需求。")
            
            # 检查限流
            is_rate_limit = '429' in error_str_lower or 'rate limit' in error_str_lower
            
            # 检查是否可重试
            is_retryable = any(keyword in error_str_lower for keyword in [
                'timeout', 'connection', 'rate limit', 'overloaded', '500', '502', '503', '504'
            ])
            
            if is_retryable and retry_count < max_retries:
                wait_time = 30 if is_rate_limit else (retry_count + 1) * 2
                logger.warning(f"⚠️ LLM API错误 (尝试 {retry_count + 1}/{max_retries}): {e}")
                logger.info(f"重试等待 {wait_time}s...")
                time.sleep(wait_time)
                return self._call_llm_stream(
                    retry_on_empty=retry_on_empty, 
                    retry_count=retry_count + 1,
                    max_retries=max_retries
                )
            else:
                logger.error(f"❌ LLM调用错误: {e}")
                raise

        # 解析工具调用
        tool_calls = []
        for idx in sorted(tool_calls_buffer.keys()):
            tc = tool_calls_buffer[idx]
            tool_id = tc.get("id") or f"call_{import uuid; uuid.uuid4().hex[:24]}"
            
            try:
                args_str = tc.get("arguments") or ""
                arguments = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                arguments = {}
            
            tool_calls.append({
                "id": tool_id,
                "name": tc["name"],
                "arguments": arguments
            })

        # 检查空响应
        if retry_on_empty and not full_content and not tool_calls:
            logger.warning(f"⚠️ LLM返回空响应，重试一次...")
            return self._call_llm_stream(retry_on_empty=False, retry_count=retry_count, max_retries=max_retries)

        # 过滤think标签
        full_content = self._filter_think_tags(full_content)
        
        # 添加助手消息到历史
        assistant_msg = {"role": "assistant", "content": []}
        if full_content:
            assistant_msg["content"].append({"type": "text", "text": full_content})
        if tool_calls:
            for tc in tool_calls:
                assistant_msg["content"].append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "input": tc.get("arguments", {})
                })
        
        if assistant_msg["content"]:
            self.messages.append(assistant_msg)

        self._emit_event("message_end", {
            "content": full_content,
            "tool_calls": tool_calls
        })

        return full_content, tool_calls

    def _execute_tool(self, tool_call: Dict) -> Dict[str, Any]:
        """
        执行工具
        
        Args:
            tool_call: {"id": str, "name": str, "arguments": dict}
            
        Returns:
            工具执行结果
        """
        tool_name = tool_call["name"]
        tool_id = tool_call["id"]
        arguments = tool_call["arguments"]

        # 检查JSON解析错误
        if "_parse_error" in tool_call:
            result = {"status": "error", "result": tool_call["_parse_error"], "execution_time": 0}
            self._record_tool_result(tool_name, arguments, False)
            return result

        # 检查连续失败
        should_stop, stop_reason, is_critical = self._check_consecutive_failures(tool_name, arguments)
        if should_stop:
            self._record_tool_result(tool_name, arguments, False)
            if is_critical:
                return {"status": "critical_error", "result": stop_reason, "execution_time": 0}
            else:
                return {"status": "error", "result": stop_reason, "execution_time": 0}

        self._emit_event("tool_execution_start", {
            "tool_call_id": tool_id,
            "tool_name": tool_name,
            "arguments": arguments
        })

        try:
            tool = self.tools.get(tool_name)
            if not tool:
                raise ValueError(f"Tool '{tool_name}' not found")

            # 设置工具上下文
            tool.model = self.model
            tool.context = self.agent

            # 执行工具
            start_time = time.time()
            result = tool.execute_tool(arguments)
            execution_time = time.time() - start_time

            result_dict = {
                "status": result.status,
                "result": result.result,
                "execution_time": execution_time
            }

            # 记录结果
            success = result.status == "success"
            self._record_tool_result(tool_name, arguments, success)

            self._emit_event("tool_execution_end", {
                "tool_call_id": tool_id,
                "tool_name": tool_name,
                **result_dict
            })

            return result_dict

        except Exception as e:
            logger.error(f"工具执行错误: {e}")
            error_result = {"status": "error", "result": str(e), "execution_time": 0}
            self._record_tool_result(tool_name, arguments, False)
            
            self._emit_event("tool_execution_end", {
                "tool_call_id": tool_id,
                "tool_name": tool_name,
                **error_result
            })
            return error_result

    def _validate_and_fix_messages(self):
        """
        验证和修复消息历史
        
        委托给共享的清理器
        """
        sanitize_claude_messages(self.messages)

    def _identify_complete_turns(self) -> List[Dict]:
        """
        识别完整的对话轮次
        
        Returns:
            轮次列表
        """
        turns = []
        current_turn = {'messages': []}
        
        for msg in self.messages:
            role = msg.get('role')
            content = msg.get('content', [])
            
            if role == 'user':
                is_user_query = False
                has_tool_result = False
                if isinstance(content, list):
                    has_text = any(
                        isinstance(block, dict) and block.get('type') == 'text'
                        for block in content
                    )
                    has_tool_result = any(
                        isinstance(block, dict) and block.get('type') == 'tool_result'
                        for block in content
                    )
                    is_user_query = has_text and not has_tool_result
                elif isinstance(content, str):
                    is_user_query = True
                
                if is_user_query:
                    if current_turn['messages']:
                        turns.append(current_turn)
                    current_turn = {'messages': [msg]}
                else:
                    current_turn['messages'].append(msg)
            else:
                current_turn['messages'].append(msg)
        
        if current_turn['messages']:
            turns.append(current_turn)
        
        return turns
    
    def _estimate_turn_tokens(self, turn: Dict) -> int:
        """估算一个轮次的tokens"""
        return sum(
            self.agent._estimate_message_tokens(msg) 
            for msg in turn['messages']
        )

    def _truncate_historical_tool_results(self):
        """
        截断历史消息中的工具结果以减少上下文大小
        """
        MAX_HISTORY_RESULT_CHARS = 20000
        if len(self.messages) < 2:
            return

        current_turn_start = len(self.messages)
        for i in range(len(self.messages) - 1, -1, -1):
            msg = self.messages[i]
            if msg.get("role") == "user":
                content = msg.get("content", [])
                if isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "text" for b in content
                ):
                    current_turn_start = i
                    break

        for i in range(current_turn_start):
            msg = self.messages[i]
            if msg.get("role") != "user":
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                result_str = block.get("content", "")
                if isinstance(result_str, str) and len(result_str) > MAX_HISTORY_RESULT_CHARS:
                    block["content"] = result_str[:MAX_HISTORY_RESULT_CHARS] + f"\n\n[截断: {len(result_str)} -> {MAX_HISTORY_RESULT_CHARS} chars]"

    def _aggressive_trim_for_overflow(self) -> bool:
        """
        激进裁剪以处理上下文溢出
        
        Returns:
            是否成功裁剪
        """
        if not self.messages:
            return False

        original_count = len(self.messages)
        AGGRESSIVE_LIMIT = 10000
        
        # 截断所有工具结果
        for msg in self.messages:
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    result_str = block.get("content", "")
                    if isinstance(result_str, str) and len(result_str) > AGGRESSIVE_LIMIT:
                        block["content"] = result_str[:AGGRESSIVE_LIMIT] + f"\n\n[截断]"
        
        # 保留最后5个完整轮次
        turns = self._identify_complete_turns()
        if len(turns) > 5:
            kept_turns = turns[-5:]
            new_messages = []
            for turn in kept_turns:
                new_messages.extend(turn["messages"])
            self.messages[:] = new_messages
            logger.info(f"🔧 裁剪: {original_count} -> {len(self.messages)} 消息")
            return True
        
        return False

    def _trim_messages(self):
        """
        智能清理消息历史，保持对话完整性
        
        使用完整轮次作为清理单位
        """
        if not self.messages or not self.agent:
            return

        # 截断历史工具结果
        self._truncate_historical_tool_results()

        # 识别完整轮次
        turns = self._identify_complete_turns()
        if not turns:
            return
        
        # 轮次限制
        if len(turns) > self.max_context_turns:
            removed_count = len(turns) // 2
            keep_count = len(turns) - removed_count
            
            if self.agent.memory_manager:
                discarded_messages = []
                for turn in turns[:removed_count]:
                    discarded_messages.extend(turn["messages"])
                if discarded_messages:
                    user_id = getattr(self.agent, '_current_user_id', None)
                    self.agent.memory_manager.flush_memory(
                        messages=discarded_messages, user_id=user_id,
                        reason="trim", max_messages=0
                    )
            
            turns = turns[-keep_count:]
            logger.info(f"💾 裁剪轮次: {keep_count + removed_count} -> {keep_count}")

        # Token限制
        context_window = self.agent._get_model_context_window()
        if hasattr(self.agent, 'max_context_tokens') and self.agent.max_context_tokens:
            max_tokens = self.agent.max_context_tokens
        else:
            reserve_tokens = int(context_window * 0.1)
            max_tokens = context_window - reserve_tokens

        system_tokens = self.agent._estimate_message_tokens({"role": "system", "content": self.system_prompt})
        current_tokens = sum(self._estimate_turn_tokens(turn) for turn in turns)

        if current_tokens + system_tokens <= max_tokens:
            new_messages = []
            for turn in turns:
                new_messages.extend(turn['messages'])
            self.messages = new_messages
            return

        # 超过限制 - 精简策略
        if len(turns) < 5:
            # 少轮次：压缩为纯文本
            compressed_turns = []
            for t in turns:
                compressed_turns.append(t)
            new_messages = []
            for turn in compressed_turns:
                new_messages.extend(turn["messages"])
            self.messages = new_messages
        else:
            # 多轮次：丢弃前一半
            removed_count = len(turns) // 2
            keep_count = len(turns) - removed_count
            kept_turns = turns[-keep_count:]
            
            new_messages = []
            for turn in kept_turns:
                new_messages.extend(turn['messages'])
            self.messages = new_messages

    def _clear_session_db(self):
        """清除当前会话的持久化消息"""
        try:
            session_id = getattr(self.agent, '_current_session_id', None)
            if not session_id:
                return
            from agent.memory import get_conversation_store
            store = get_conversation_store()
            store.clear_session(session_id)
            logger.info(f"🗑️ 清除会话数据: {session_id}")
        except Exception as e:
            logger.warning(f"清除会话DB失败: {e}")

    def _prepare_messages(self) -> List[Dict[str, Any]]:
        """
        准备发送给LLM的消息
        
        注意：系统提示词通过单独的system参数传递（Claude API）
        """
        return self.messages
