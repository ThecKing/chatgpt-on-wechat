# -*- coding: utf-8 -*-
"""
消息清理器模块 - 修复破损的 tool_use / tool_result 配对

提供两个可复用的公共函数，用于 agent_stream.py 和其他需要
将消息转换为 OpenAI 格式的 bot：

1. sanitize_claude_messages(messages)
   对内部 Claude 格式消息列表进行原地操作（in-place）

2. drop_orphaned_tool_results_openai(messages)
   对已转换为 OpenAI 格式的消息列表进行清理，返回清理后的副本

为什么需要这个模块：
- Claude API 要求 tool_use 和 tool_result 必须配对
- 如果网络中断或发生错误，可能导致消息历史中存在孤立的工具调用
- 这些孤立的消息会导致后续 API 调用失败
"""

# 启用延迟类型注解
from __future__ import annotations

# 导入类型提示
from typing import Dict, List, Set

# 导入日志模块
from common.log import logger


# ------------------------------------------------------------------ #
# Claude格式清理器（被 agent_stream 使用）
# ------------------------------------------------------------------ #

def sanitize_claude_messages(messages: List[Dict]) -> int:
    """
    验证并修复 Claude 格式的消息列表（原地操作）
    
    修复的问题：
    - 尾随的 assistant 消息包含 tool_use 但没有后续的 tool_result
    - 开头的孤立 tool_result user 消息
    - 中间的 tool_result 块，其 tool_use_id 在前面的 assistant 消息中找不到匹配
    
    Args:
        messages: 消息列表（会被原地修改）
        
    Returns:
        被移除的消息/块数量
    """
    # 如果消息列表为空，直接返回
    if not messages:
        return 0

    # 记录移除数量
    removed = 0

    # 1. 移除尾部不完整的 tool_use assistant 消息
    #    这种消息会导致下一次 API 调用失败
    while messages:
        # 获取最后一条消息
        last = messages[-1]
        # 如果不是 assistant 消息，停止
        if last.get("role") != "assistant":
            break
        # 获取消息内容
        content = last.get("content", [])
        # 检查是否包含 tool_use 块
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_use"
            for b in content
        ):
            # 记录警告日志
            logger.warning("⚠️ Removing trailing incomplete tool_use assistant message")
            # 移除这条消息
            messages.pop()
            removed += 1
        else:
            # 没有tool_use，停止检查
            break

    # 2. 移除开头的孤立 tool_result user 消息
    #    这种消息没有对应的 tool_use，是无效的
    while messages:
        # 获取第一条消息
        first = messages[0]
        # 如果不是 user 消息，停止
        if first.get("role") != "user":
            break
        # 获取消息内容
        content = first.get("content", [])
        # 检查是否只有 tool_result 没有 text
        if isinstance(content, list) and _has_block_type(content, "tool_result") \
                and not _has_block_type(content, "text"):
            # 记录警告日志
            logger.warning("⚠️ Removing leading orphaned tool_result user message")
            # 移除这条消息
            messages.pop(0)
            removed += 1
        else:
            # 有text或其他内容，停止检查
            break

    # 3. 迭代移除不匹配的 tool_use / tool_result 直到稳定
    #    移除一条破损消息可能会导致其他消息变成孤立的
    #    所以需要循环多次直到清理完毕
    for _ in range(5):  # 最多迭代5次
        # 收集所有 tool_use 的 ID
        use_ids: Set[str] = set()
        # 收集所有 tool_result 引用的 ID
        result_ids: Set[str] = set()
        
        # 遍历所有消息
        for msg in messages:
            # 遍历消息中的所有块
            for block in (msg.get("content") or []):
                # 跳过非字典块
                if not isinstance(block, dict):
                    continue
                # 如果是 tool_use，记录其 ID
                if block.get("type") == "tool_use" and block.get("id"):
                    use_ids.add(block["id"])
                # 如果是 tool_result，记录其引用的 tool_use_id
                elif block.get("type") == "tool_result" and block.get("tool_use_id"):
                    result_ids.add(block["tool_use_id"])

        # 找出没有对应 tool_result 的 tool_use ID
        bad_use = use_ids - result_ids
        # 找出没有对应 tool_use 的 tool_result 引用 ID
        bad_result = result_ids - use_ids
        
        # 如果没有破损的配对，退出循环
        if not bad_use and not bad_result:
            break

        # 本轮移除的数量
        pass_removed = 0
        # 消息索引
        i = 0
        
        # 遍历消息列表
        while i < len(messages):
            msg = messages[i]
            role = msg.get("role")
            content = msg.get("content", [])
            
            # 跳过非列表内容
            if not isinstance(content, list):
                i += 1
                continue

            # 处理包含不匹配 tool_use 的 assistant 消息
            if role == "assistant" and bad_use and any(
                isinstance(b, dict) and b.get("type") == "tool_use"
                and b.get("id") in bad_use for b in content
            ):
                logger.warning(f"⚠️ Removing assistant msg with unmatched tool_use")
                # 移除这条消息
                messages.pop(i)
                pass_removed += 1
                continue

            # 处理包含不匹配 tool_result 的 user 消息
            if role == "user" and bad_result and _has_block_type(content, "tool_result"):
                # 检查是否包含不匹配的 tool_result
                has_bad = any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    and b.get("tool_use_id") in bad_result for b in content
                )
                if has_bad:
                    # 如果消息只有 tool_result 没有 text，移除整条消息
                    if not _has_block_type(content, "text"):
                        logger.warning(f"⚠️ Removing user msg with unmatched tool_result")
                        messages.pop(i)
                        pass_removed += 1
                        continue
                    else:
                        # 如果消息还有 text，只移除不匹配的 tool_result 块
                        before = len(content)
                        msg["content"] = [
                            b for b in content
                            if not (isinstance(b, dict) and b.get("type") == "tool_result"
                                    and b.get("tool_use_id") in bad_result)
                        ]
                        pass_removed += before - len(msg["content"])

            # 移动到下一条消息
            i += 1

        # 累加移除数量
        removed += pass_removed
        # 如果本轮没有移除任何内容，退出循环
        if pass_removed == 0:
            break

    # 如果有移除，记录日志
    if removed:
        logger.info(f"🔧 Message validation: removed {removed} broken message(s)")
    
    # 返回移除总数
    return removed


# ------------------------------------------------------------------ #
# OpenAI格式清理器（被 minimax_bot, openai_compatible_bot 使用）
# ------------------------------------------------------------------ #

def drop_orphaned_tool_results_openai(messages: List[Dict]) -> List[Dict]:
    """
    返回消息列表（OpenAI格式）的副本，移除孤立的 tool 消息
    
    孤立的 tool 消息是指其 tool_call_id 在前面的 assistant 消息的
    tool_calls 中找不到匹配的 ID。
    
    Args:
        messages: OpenAI 格式的消息列表
        
    Returns:
        清理后的消息列表副本
    """
    # 已知的 tool_call_id 集合
    known_ids: Set[str] = set()
    # 清理后的消息列表
    cleaned: List[Dict] = []
    
    # 遍历所有消息
    for msg in messages:
        # 如果是 assistant 消息且有 tool_calls
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            # 收集所有 tool_call 的 ID
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id", "")
                if tc_id:
                    known_ids.add(tc_id)

        # 如果是 tool 消息
        if msg.get("role") == "tool":
            # 获取其引用的 tool_call_id
            ref_id = msg.get("tool_call_id", "")
            # 如果这个 ID 不在已知 ID 中，跳过这条消息
            if ref_id and ref_id not in known_ids:
                logger.warning(
                    f"[MessageSanitizer] Dropping orphaned tool result "
                    f"(tool_call_id={ref_id} not in known ids)"
                )
                continue
        # 添加到清理后的列表
        cleaned.append(msg)
    
    # 返回清理后的列表
    return cleaned


# ------------------------------------------------------------------ #
# 内部辅助函数
# ------------------------------------------------------------------ #

def _has_block_type(content: list, block_type: str) -> bool:
    """
    检查内容列表中是否包含指定类型的块
    
    Args:
        content: 内容块列表
        block_type: 要检查的块类型
        
    Returns:
        True 表示包含，False 表示不包含
    """
    return any(
        isinstance(b, dict) and b.get("type") == block_type
        for b in content
    )


def _extract_text_from_content(content) -> str:
    """
    从消息内容字段中提取纯文本
    
    支持两种格式：
    - 字符串：直接返回
    - 块列表：提取所有 text 类型块的文本
    
    Args:
        content: 消息内容（字符串或块列表）
        
    Returns:
        提取的纯文本
    """
    # 如果是字符串，直接返回（去除首尾空白）
    if isinstance(content, str):
        return content.strip()
    
    # 如果是列表，提取所有 text 块的内容
    if isinstance(content, list):
        # 遍历所有块，提取 text 类型块的文本
        parts = [
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        # 用换行符连接所有文本部分
        return "\n".join(p for p in parts if p).strip()
    
    # 其他类型返回空字符串
    return ""


def compress_turn_to_text_only(turn: Dict) -> Dict:
    """
    将完整的对话轮次（包含 tool_use/tool_result 链）压缩为轻量级的纯文本轮次
    
    只保留第一个用户的文本和最后一个助手的文本。
    这样可以保留对话上下文（用户问了什么，Agent得出什么结论），
    同时移除大量中间的工具交互内容。
    
    Args:
        turn: 对话轮次字典，包含 messages 列表
        
    Returns:
        新的轮次字典，原始数据不会被修改
    """
    # 用户文本（取第一个）
    user_text = ""
    # 助手文本（取最后一个）
    last_assistant_text = ""

    # 遍历轮次中的所有消息
    for msg in turn["messages"]:
        role = msg.get("role")
        content = msg.get("content", [])

        # 处理用户消息
        if role == "user":
            # 跳过只包含 tool_result 的消息
            if isinstance(content, list) and _has_block_type(content, "tool_result"):
                continue
            # 只取第一个用户文本
            if not user_text:
                user_text = _extract_text_from_content(content)

        # 处理助手消息
        elif role == "assistant":
            # 提取文本内容
            text = _extract_text_from_content(content)
            # 如果有文本，更新（保留最后一个）
            if text:
                last_assistant_text = text

    # 构建压缩后的消息列表
    compressed_messages = []
    
    # 添加用户消息
    if user_text:
        compressed_messages.append({
            "role": "user",
            "content": [{"type": "text", "text": user_text}]
        })
    
    # 添加助手消息
    if last_assistant_text:
        compressed_messages.append({
            "role": "assistant",
            "content": [{"type": "text", "text": last_assistant_text}]
        })

    # 返回新的轮次字典
    return {"messages": compressed_messages}
