# -*- coding: utf-8 -*-
"""
工具辅助函数模块

提供截断和差异比较工具：
- truncate_head/truncate_tail: 内容截断
- strip_bom: 去除BOM
- fuzzy_find_text: 模糊文本查找
- generate_diff_string: 生成差异字符串
"""

# 导入截断工具
from .truncate import (
    truncate_head,         # 从头部截断
    truncate_tail,         # 从尾部截断
    truncate_line,         # 截断单行
    format_size,           # 格式化大小
    TruncationResult,      # 截断结果类
    DEFAULT_MAX_LINES,     # 默认最大行数
    DEFAULT_MAX_BYTES,     # 默认最大字节数
    GREP_MAX_LINE_LENGTH   # grep最大行长度
)

# 导入差异工具
from .diff import (
    strip_bom,              # 去除BOM
    detect_line_ending,     # 检测行尾符
    normalize_to_lf,        # 规范化为LF
    restore_line_endings,   # 恢复行尾符
    normalize_for_fuzzy_match,  # 模糊匹配规范化
    fuzzy_find_text,        # 模糊查找文本
    generate_diff_string,   # 生成差异字符串
    FuzzyMatchResult        # 模糊匹配结果类
)

# 公开导出
__all__ = [
    # 截断相关
    'truncate_head',
    'truncate_tail',
    'truncate_line',
    'format_size',
    'TruncationResult',
    'DEFAULT_MAX_LINES',
    'DEFAULT_MAX_BYTES',
    'GREP_MAX_LINE_LENGTH',
    # 差异相关
    'strip_bom',
    'detect_line_ending',
    'normalize_to_lf',
    'restore_line_endings',
    'normalize_for_fuzzy_match',
    'fuzzy_find_text',
    'generate_diff_string',
    'FuzzyMatchResult'
]
