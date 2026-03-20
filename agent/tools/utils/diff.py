# -*- coding: utf-8 -*-
"""
文件编辑差异工具

提供模糊匹配和差异生成功能，用于edit工具：
- BOM处理
- 行尾符检测和转换
- 模糊文本匹配
- 统一差异生成
"""

# 导入差异比较库
import difflib

# 导入正则表达式
import re

# 导入类型提示
from typing import Optional, Tuple


def strip_bom(text: str) -> Tuple[str, str]:
    """
    去除BOM（字节顺序标记）
    
    Args:
        text: 原始文本
        
    Returns:
        Tuple[str, str]: (BOM, 去除BOM后的文本)
    """
    # UTF-8 BOM 是 \ufeff
    if text.startswith('\ufeff'):
        return '\ufeff', text[1:]
    return '', text


def detect_line_ending(text: str) -> str:
    """
    检测行尾符类型
    
    Args:
        text: 文本内容
        
    Returns:
        str: 行尾符类型（'\r\n' 或 '\n'）
    """
    # 检查是否包含Windows换行符
    if '\r\n' in text:
        return '\r\n'
    # 默认Unix换行符
    return '\n'


def normalize_to_lf(text: str) -> str:
    """
    将所有行尾符规范化为LF (\n)
    
    Args:
        text: 原始文本
        
    Returns:
        str: 规范化后的文本
    """
    # 先替换 \r\n，再替换单独的 \r
    return text.replace('\r\n', '\n').replace('\r', '\n')


def restore_line_endings(text: str, original_ending: str) -> str:
    """
    恢复原始行尾符
    
    Args:
        text: LF规范化的文本
        original_ending: 原始行尾符
        
    Returns:
        str: 恢复行尾符后的文本
    """
    # 如果原始是Windows换行符
    if original_ending == '\r\n':
        return text.replace('\n', '\r\n')
    return text


def normalize_for_fuzzy_match(text: str) -> str:
    """
    规范化文本用于模糊匹配
    去除多余空白但保留基本结构。
    
    Args:
        text: 原始文本
        
    Returns:
        str: 规范化后的文本
    """
    # 将多个空格/制表符压缩为一个空格
    text = re.sub(r'[ \t]+', ' ', text)
    # 去除行尾空格
    text = re.sub(r' +\n', '\n', text)
    # 去除行首空格（但保留缩进结构，只去除多余）
    lines = text.split('\n')
    normalized_lines = []
    for line in lines:
        # 去除行首空白
        stripped = line.lstrip()
        if stripped:
            # 计算缩进级别
            indent_count = len(line) - len(stripped)
            # 规范化缩进（将制表符转换为空格）
            normalized_indent = ' ' * indent_count
            normalized_lines.append(normalized_indent + stripped)
        else:
            normalized_lines.append('')
    return '\n'.join(normalized_lines)


class FuzzyMatchResult:
    """
    模糊匹配结果类
    
    封装模糊匹配的结果：
    - found: 是否找到
    - index: 匹配位置
    - match_length: 匹配长度
    - content_for_replacement: 用于替换的内容
    """
    
    def __init__(self, found: bool, index: int = -1, match_length: int = 0, content_for_replacement: str = ""):
        """
        初始化模糊匹配结果
        
        Args:
            found: 是否找到匹配
            index: 匹配起始位置
            match_length: 匹配长度
            content_for_replacement: 用于替换的内容
        """
        self.found = found                      # 是否找到
        self.index = index                      # 匹配位置
        self.match_length = match_length        # 匹配长度
        self.content_for_replacement = content_for_replacement  # 替换内容


def fuzzy_find_text(content: str, old_text: str) -> FuzzyMatchResult:
    """
    在内容中查找文本，先尝试精确匹配，再尝试模糊匹配
    
    Args:
        content: 要搜索的内容
        old_text: 要查找的文本
        
    Returns:
        FuzzyMatchResult: 匹配结果
    """
    # 首先尝试精确匹配
    index = content.find(old_text)
    if index != -1:
        # 精确匹配成功
        return FuzzyMatchResult(
            found=True,
            index=index,
            match_length=len(old_text),
            content_for_replacement=content
        )
    
    # 尝试模糊匹配
    fuzzy_content = normalize_for_fuzzy_match(content)
    fuzzy_old_text = normalize_for_fuzzy_match(old_text)
    
    index = fuzzy_content.find(fuzzy_old_text)
    if index != -1:
        # 模糊匹配成功，使用规范化内容进行替换
        return FuzzyMatchResult(
            found=True,
            index=index,
            match_length=len(fuzzy_old_text),
            content_for_replacement=fuzzy_content
        )
    
    # 未找到
    return FuzzyMatchResult(found=False)


def generate_diff_string(old_content: str, new_content: str) -> dict:
    """
    生成统一差异字符串
    
    Args:
        old_content: 旧内容
        new_content: 新内容
        
    Returns:
        dict: 包含diff和首次变更行号的字典
    """
    # 分割为行
    old_lines = old_content.split('\n')
    new_lines = new_content.split('\n')
    
    # 生成统一差异
    diff_lines = list(difflib.unified_diff(
        old_lines,          # 旧行
        new_lines,          # 新行
        lineterm='',        # 行终止符
        fromfile='original', # 原文件名
        tofile='modified'    # 新文件名
    ))
    
    # 查找首次变更的行号
    first_changed_line = None
    for line in diff_lines:
        if line.startswith('@@'):
            # 解析 @@ -1,3 +1,3 @@ 格式
            match = re.search(r'@@ -\d+,?\d* \+(\d+)', line)
            if match:
                first_changed_line = int(match.group(1))
                break
    
    # 合并差异行
    diff_string = '\n'.join(diff_lines)
    
    return {
        'diff': diff_string,               # 差异字符串
        'first_changed_line': first_changed_line  # 首次变更行号
    }
