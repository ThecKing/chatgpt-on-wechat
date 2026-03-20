# -*- coding: utf-8 -*-
"""
截断工具模块 - 工具输出的共享截断工具

截断基于两个独立的限制 - 先达到者胜出：
- 行限制（默认：2000行）
- 字节限制（默认：50KB）

永远不返回部分行（除了bash尾部截断的边界情况）。
"""

# 导入类型提示
from typing import Dict, Any, Optional, Literal, Tuple


# 默认最大行数
DEFAULT_MAX_LINES = 2000

# 默认最大字节数（50KB）
DEFAULT_MAX_BYTES = 50 * 1024

# grep匹配行的最大字符数
GREP_MAX_LINE_LENGTH = 500


class TruncationResult:
    """
    截断结果类
    
    封装截断操作的结果，包括：
    - 截断后的内容
    - 是否被截断
    - 截断原因（行数/字节）
    - 原始和输出的统计信息
    """
    
    def __init__(
        self,
        content: str,
        truncated: bool,
        truncated_by: Optional[Literal["lines", "bytes"]],
        total_lines: int,
        total_bytes: int,
        output_lines: int,
        output_bytes: int,
        last_line_partial: bool = False,
        first_line_exceeds_limit: bool = False,
        max_lines: int = DEFAULT_MAX_LINES,
        max_bytes: int = DEFAULT_MAX_BYTES
    ):
        """
        初始化截断结果
        
        Args:
            content: 截断后的内容
            truncated: 是否被截断
            truncated_by: 截断原因（"lines" 或 "bytes"）
            total_lines: 原始总行数
            total_bytes: 原始总字节数
            output_lines: 输出行数
            output_bytes: 输出字节数
            last_line_partial: 最后一行是否部分（尾部截断边界情况）
            first_line_exceeds_limit: 第一行是否超过限制
            max_lines: 最大行数限制
            max_bytes: 最大字节数限制
        """
        self.content = content                    # 截断后内容
        self.truncated = truncated                # 是否截断
        self.truncated_by = truncated_by          # 截断原因
        self.total_lines = total_lines            # 原始总行数
        self.total_bytes = total_bytes            # 原始总字节数
        self.output_lines = output_lines          # 输出行数
        self.output_bytes = output_bytes          # 输出字节数
        self.last_line_partial = last_line_partial    # 最后行是否部分
        self.first_line_exceeds_limit = first_line_exceeds_limit  # 首行是否超限
        self.max_lines = max_lines                # 最大行数
        self.max_bytes = max_bytes                # 最大字节数
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典
        
        Returns:
            dict: 包含所有属性的字典
        """
        return {
            "content": self.content,                    # 内容
            "truncated": self.truncated,                # 是否截断
            "truncated_by": self.truncated_by,          # 截断原因
            "total_lines": self.total_lines,            # 原始行数
            "total_bytes": self.total_bytes,            # 原始字节数
            "output_lines": self.output_lines,          # 输出行数
            "output_bytes": self.output_bytes,          # 输出字节数
            "last_line_partial": self.last_line_partial,    # 最后行部分
            "first_line_exceeds_limit": self.first_line_exceeds_limit,  # 首行超限
            "max_lines": self.max_lines,                # 最大行数
            "max_bytes": self.max_bytes                 # 最大字节数
        }


def format_size(bytes_count: int) -> str:
    """
    格式化字节数为人类可读大小
    
    Args:
        bytes_count: 字节数
        
    Returns:
        str: 格式化的大小字符串（如 "1.5KB"）
    """
    # 小于1KB
    if bytes_count < 1024:
        return f"{bytes_count}B"
    # 小于1MB
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f}KB"
    # 大于等于1MB
    else:
        return f"{bytes_count / (1024 * 1024):.1f}MB"


def truncate_head(content: str, max_lines: Optional[int] = None, max_bytes: Optional[int] = None) -> TruncationResult:
    """
    从头部截断内容（保留前N行/字节）
    适用于文件读取，需要查看开头内容。
    
    永不返回部分行。如果第一行超过字节限制，
    返回空内容并设置 first_line_exceeds_limit=True。
    
    Args:
        content: 要截断的内容
        max_lines: 最大行数（默认：2000）
        max_bytes: 最大字节数（默认：50KB）
        
    Returns:
        TruncationResult: 截断结果
    """
    # 使用默认值
    if max_lines is None:
        max_lines = DEFAULT_MAX_LINES
    if max_bytes is None:
        max_bytes = DEFAULT_MAX_BYTES
    
    # 计算总字节数
    total_bytes = len(content.encode('utf-8'))
    # 分割为行
    lines = content.split('\n')
    # 总行数
    total_lines = len(lines)
    
    # 检查是否不需要截断
    if total_lines <= max_lines and total_bytes <= max_bytes:
        return TruncationResult(
            content=content,                 # 原内容
            truncated=False,                 # 未截断
            truncated_by=None,               # 无截断原因
            total_lines=total_lines,         # 总行数
            total_bytes=total_bytes,         # 总字节数
            output_lines=total_lines,        # 输出行数等于总行数
            output_bytes=total_bytes,        # 输出字节数等于总字节数
            last_line_partial=False,         # 最后行完整
            first_line_exceeds_limit=False,  # 首行未超限
            max_lines=max_lines,
            max_bytes=max_bytes
        )
    
    # 检查第一行是否单独超过字节限制
    first_line_bytes = len(lines[0].encode('utf-8'))
    if first_line_bytes > max_bytes:
        return TruncationResult(
            content="",                      # 空内容
            truncated=True,                  # 已截断
            truncated_by="bytes",            # 因字节限制
            total_lines=total_lines,
            total_bytes=total_bytes,
            output_lines=0,                  # 输出0行
            output_bytes=0,
            last_line_partial=False,
            first_line_exceeds_limit=True,   # 首行超限
            max_lines=max_lines,
            max_bytes=max_bytes
        )
    
    # 收集能放下的完整行
    output_lines_arr = []
    output_bytes_count = 0
    truncated_by = "lines"
    
    # 遍历每一行
    for i, line in enumerate(lines):
        # 检查行数限制
        if i >= max_lines:
            break
        
        # 计算行字节数（非首行加换行符）
        line_bytes = len(line.encode('utf-8')) + (1 if i > 0 else 0)
        
        # 检查字节限制
        if output_bytes_count + line_bytes > max_bytes:
            truncated_by = "bytes"
            break
        
        # 添加行
        output_lines_arr.append(line)
        output_bytes_count += line_bytes
    
    # 如果因行数限制退出
    if len(output_lines_arr) >= max_lines and output_bytes_count <= max_bytes:
        truncated_by = "lines"
    
    # 合并输出行
    output_content = '\n'.join(output_lines_arr)
    # 计算实际输出字节数
    final_output_bytes = len(output_content.encode('utf-8'))
    
    return TruncationResult(
        content=output_content,
        truncated=True,
        truncated_by=truncated_by,
        total_lines=total_lines,
        total_bytes=total_bytes,
        output_lines=len(output_lines_arr),
        output_bytes=final_output_bytes,
        last_line_partial=False,
        first_line_exceeds_limit=False,
        max_lines=max_lines,
        max_bytes=max_bytes
    )


def truncate_tail(content: str, max_lines: Optional[int] = None, max_bytes: Optional[int] = None) -> TruncationResult:
    """
    从尾部截断内容（保留最后N行/字节）
    适用于bash输出，需要查看结尾内容（错误、最终结果）。
    
    如果原始内容的最后一行超过字节限制，可能返回部分首行。
    
    Args:
        content: 要截断的内容
        max_lines: 最大行数（默认：2000）
        max_bytes: 最大字节数（默认：50KB）
        
    Returns:
        TruncationResult: 截断结果
    """
    # 使用默认值
    if max_lines is None:
        max_lines = DEFAULT_MAX_LINES
    if max_bytes is None:
        max_bytes = DEFAULT_MAX_BYTES
    
    # 计算总字节数
    total_bytes = len(content.encode('utf-8'))
    # 分割为行
    lines = content.split('\n')
    # 总行数
    total_lines = len(lines)
    
    # 检查是否不需要截断
    if total_lines <= max_lines and total_bytes <= max_bytes:
        return TruncationResult(
            content=content,
            truncated=False,
            truncated_by=None,
            total_lines=total_lines,
            total_bytes=total_bytes,
            output_lines=total_lines,
            output_bytes=total_bytes,
            last_line_partial=False,
            first_line_exceeds_limit=False,
            max_lines=max_lines,
            max_bytes=max_bytes
        )
    
    # 从末尾向前工作
    output_lines_arr = []
    output_bytes_count = 0
    truncated_by = "lines"
    last_line_partial = False
    
    # 从后向前遍历
    for i in range(len(lines) - 1, -1, -1):
        # 检查行数限制
        if len(output_lines_arr) >= max_lines:
            break
        
        line = lines[i]
        # 计算行字节数（非首个添加的行加换行符）
        line_bytes = len(line.encode('utf-8')) + (1 if len(output_lines_arr) > 0 else 0)
        
        # 检查字节限制
        if output_bytes_count + line_bytes > max_bytes:
            truncated_by = "bytes"
            # 边界情况：还没添加任何行，这行就超限
            if len(output_lines_arr) == 0:
                # 取这行的末尾部分
                truncated_line = _truncate_string_to_bytes_from_end(line, max_bytes)
                output_lines_arr.insert(0, truncated_line)
                output_bytes_count = len(truncated_line.encode('utf-8'))
                last_line_partial = True
            break
        
        # 在数组开头插入行
        output_lines_arr.insert(0, line)
        output_bytes_count += line_bytes
    
    # 如果因行数限制退出
    if len(output_lines_arr) >= max_lines and output_bytes_count <= max_bytes:
        truncated_by = "lines"
    
    # 合并输出行
    output_content = '\n'.join(output_lines_arr)
    # 计算实际输出字节数
    final_output_bytes = len(output_content.encode('utf-8'))
    
    return TruncationResult(
        content=output_content,
        truncated=True,
        truncated_by=truncated_by,
        total_lines=total_lines,
        total_bytes=total_bytes,
        output_lines=len(output_lines_arr),
        output_bytes=final_output_bytes,
        last_line_partial=last_line_partial,
        first_line_exceeds_limit=False,
        max_lines=max_lines,
        max_bytes=max_bytes
    )


def _truncate_string_to_bytes_from_end(text: str, max_bytes: int) -> str:
    """
    从末尾截断字符串以适应字节限制
    正确处理多字节UTF-8字符。
    
    Args:
        text: 要截断的字符串
        max_bytes: 最大字节数
        
    Returns:
        str: 截断后的字符串
    """
    # 编码为UTF-8字节
    encoded = text.encode('utf-8')
    
    # 如果已经足够小
    if len(encoded) <= max_bytes:
        return text
    
    # 从末尾开始，跳过maxBytes
    start = len(encoded) - max_bytes
    
    # 找到有效的UTF-8边界（字符起始位置）
    # UTF-8继续字节的形式是 10xxxxxx (0x80-0xBF)
    while start < len(encoded) and (encoded[start] & 0xC0) == 0x80:
        start += 1
    
    # 解码并返回
    return encoded[start:].decode('utf-8', errors='ignore')


def truncate_line(line: str, max_chars: int = GREP_MAX_LINE_LENGTH) -> Tuple[str, bool]:
    """
    将单行截断到最大字符数，添加 [truncated] 后缀
    用于grep匹配行。
    
    Args:
        line: 要截断的行
        max_chars: 最大字符数
        
    Returns:
        Tuple[str, bool]: (截断后的文本, 是否被截断)
    """
    # 如果行足够短
    if len(line) <= max_chars:
        return line, False
    # 截断并添加后缀
    return f"{line[:max_chars]}... [truncated]", True
