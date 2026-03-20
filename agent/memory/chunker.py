# -*- coding: utf-8 -*-
"""
文本分块工具 - 用于记忆系统

将文本分割成带有token限制和重叠的块。
"""

# 启用延迟类型注解
from __future__ import annotations

# 导入类型提示
from typing import List, Tuple

# 导入数据类装饰器
from dataclasses import dataclass


@dataclass
class TextChunk:
    """
    文本块数据类
    
    表示一个带有行号的文本块。
    
    属性说明：
    - text: 文本内容
    - start_line: 起始行号
    - end_line: 结束行号
    """
    text: str          # 文本内容
    start_line: int    # 起始行号
    end_line: int      # 结束行号


class TextChunker:
    """
    文本分块器
    
    按行数和token估算分块，支持块之间的重叠。
    """
    
    def __init__(self, max_tokens: int = 500, overlap_tokens: int = 50):
        """
        初始化分块器
        
        Args:
            max_tokens: 每块最大token数
            overlap_tokens: 块之间重叠token数
        """
        self.max_tokens = max_tokens      # 最大token数
        self.overlap_tokens = overlap_tokens  # 重叠token数
        # 粗略估算：中英文混合约4字符/token
        self.chars_per_token = 4
    
    def chunk_text(self, text: str) -> List[TextChunk]:
        """
        将文本分割成重叠的块
        
        Args:
            text: 输入文本
            
        Returns:
            TextChunk对象列表
        """
        # 如果文本为空
        if not text.strip():
            return []
        
        # 分割为行
        lines = text.split('\n')
        # 结果列表
        chunks = []
        
        # 计算字符限制
        max_chars = self.max_tokens * self.chars_per_token
        overlap_chars = self.overlap_tokens * self.chars_per_token
        
        # 当前块
        current_chunk = []
        current_chars = 0
        start_line = 1
        
        # 遍历每一行
        for i, line in enumerate(lines, start=1):
            line_chars = len(line)
            
            # 如果单行超过最大限制，分割它
            if line_chars > max_chars:
                # 保存当前块（如果存在）
                if current_chunk:
                    chunks.append(TextChunk(
                        text='\n'.join(current_chunk),
                        start_line=start_line,
                        end_line=i - 1
                    ))
                    current_chunk = []
                    current_chars = 0
                
                # 将长行分割成多个块
                for sub_chunk in self._split_long_line(line, max_chars):
                    chunks.append(TextChunk(
                        text=sub_chunk,
                        start_line=i,
                        end_line=i
                    ))
                
                start_line = i + 1
                continue
            
            # 检查添加这行是否会超限
            if current_chars + line_chars > max_chars and current_chunk:
                # 保存当前块
                chunks.append(TextChunk(
                    text='\n'.join(current_chunk),
                    start_line=start_line,
                    end_line=i - 1
                ))
                
                # 开始新块，带重叠
                overlap_lines = self._get_overlap_lines(current_chunk, overlap_chars)
                current_chunk = overlap_lines + [line]
                current_chars = sum(len(l) for l in current_chunk)
                start_line = i - len(overlap_lines)
            else:
                # 添加行到当前块
                current_chunk.append(line)
                current_chars += line_chars
        
        # 保存最后一个块
        if current_chunk:
            chunks.append(TextChunk(
                text='\n'.join(current_chunk),
                start_line=start_line,
                end_line=len(lines)
            ))
        
        return chunks
    
    def _split_long_line(self, line: str, max_chars: int) -> List[str]:
        """
        将单行分割成多个块
        
        Args:
            line: 长行文本
            max_chars: 最大字符数
            
        Returns:
            分割后的文本块列表
        """
        chunks = []
        for i in range(0, len(line), max_chars):
            chunks.append(line[i:i + max_chars])
        return chunks
    
    def _get_overlap_lines(self, lines: List[str], target_chars: int) -> List[str]:
        """
        获取末尾几行用于重叠
        
        Args:
            lines: 行列表
            target_chars: 目标字符数
            
        Returns:
            重叠行列表
        """
        overlap = []
        chars = 0
        
        # 从后向前遍历
        for line in reversed(lines):
            line_chars = len(line)
            if chars + line_chars > target_chars:
                break
            overlap.insert(0, line)
            chars += line_chars
        
        return overlap
    
    def chunk_markdown(self, text: str) -> List[TextChunk]:
        """
        分块Markdown文本（尊重结构）
        
        未来增强：尊重Markdown章节结构
        
        Args:
            text: Markdown文本
            
        Returns:
            文本块列表
        """
        # 目前使用普通分块
        return self.chunk_text(text)
