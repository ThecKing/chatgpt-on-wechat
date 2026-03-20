# -*- coding: utf-8 -*-
"""
编辑文件工具

通过精确文本替换编辑文件：
- 替换：oldText必须完全匹配（包括空白）
- 追加：oldText为空时追加到文件末尾

支持模糊匹配处理行尾符差异。
"""

# 导入操作系统模块
import os

# 导入类型提示
from typing import Dict, Any

# 导入工具基类和结果类
from agent.tools.base_tool import BaseTool, ToolResult

# 导入路径扩展工具
from common.utils import expand_path

# 导入差异工具
from agent.tools.utils.diff import (
    strip_bom,              # 去除BOM
    detect_line_ending,     # 检测行尾符
    normalize_to_lf,        # 规范化为LF
    restore_line_endings,   # 恢复原行尾符
    normalize_for_fuzzy_match,  # 模糊匹配规范化
    fuzzy_find_text,        # 模糊查找文本
    generate_diff_string    # 生成差异字符串
)


class Edit(BaseTool):
    """
    编辑文件工具类
    
    功能：
    - 精确替换文本
    - 追加到文件末尾
    - 自动检测和保留原行尾符
    
    限制：
    - oldText必须完全匹配（包括空白）
    - 如果有多个匹配，必须提供更多上下文使其唯一
    """
    
    # 工具名称
    name: str = "edit"
    
    # 工具描述
    description: str = "Edit a file by replacing exact text, or append to end if oldText is empty. For append: use empty oldText. For replace: oldText must match exactly (including whitespace)."
    
    # 参数JSON Schema
    params: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to edit (relative or absolute)"
            },
            "oldText": {
                "type": "string",
                "description": "Text to find and replace. Use empty string to append to end of file. For replacement: must match exactly including whitespace."
            },
            "newText": {
                "type": "string",
                "description": "New text to replace the old text with"
            }
        },
        "required": ["path", "oldText", "newText"]
    }
    
    def __init__(self, config: dict = None):
        """
        初始化编辑工具
        
        Args:
            config: 配置字典，可包含：
                - cwd: 工作目录
                - memory_manager: 记忆管理器
        """
        # 存储配置
        self.config = config or {}
        # 获取工作目录
        self.cwd = self.config.get("cwd", os.getcwd())
        # 获取记忆管理器（可选）
        self.memory_manager = self.config.get("memory_manager", None)
    
    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        执行文件编辑操作
        
        Args:
            args: 包含文件路径、旧文本和新文本
                - path: 文件路径
                - oldText: 要替换的文本（空字符串表示追加）
                - newText: 新文本
            
        Returns:
            ToolResult: 操作结果
        """
        # 获取参数
        path = args.get("path", "").strip()       # 文件路径
        old_text = args.get("oldText", "")         # 旧文本
        new_text = args.get("newText", "")         # 新文本
        
        # 检查路径参数
        if not path:
            return ToolResult.fail("Error: path parameter is required")
        
        # 解析路径
        absolute_path = self._resolve_path(path)
        
        # 检查文件是否存在
        if not os.path.exists(absolute_path):
            return ToolResult.fail(f"Error: File not found: {path}")
        
        # 检查是否可读写
        if not os.access(absolute_path, os.R_OK | os.W_OK):
            return ToolResult.fail(f"Error: File is not readable/writable: {path}")
        
        try:
            # 读取文件
            with open(absolute_path, 'r', encoding='utf-8') as f:
                raw_content = f.read()
            
            # 去除BOM（LLM不会在oldText中包含不可见的BOM）
            bom, content = strip_bom(raw_content)
            
            # 检测原始行尾符
            original_ending = detect_line_ending(content)
            
            # 规范化为LF
            normalized_content = normalize_to_lf(content)
            normalized_old_text = normalize_to_lf(old_text)
            normalized_new_text = normalize_to_lf(new_text)
            
            # 特殊情况：空oldText表示追加到文件末尾
            if not old_text or not old_text.strip():
                # 追加模式：将newText添加到末尾
                # 如果文件不以换行结尾，添加换行
                if normalized_content and not normalized_content.endswith('\n'):
                    new_content = normalized_content + '\n' + normalized_new_text
                else:
                    new_content = normalized_content + normalized_new_text
                base_content = normalized_content  # 用于验证
            else:
                # 正常编辑模式：查找并替换
                # 使用模糊匹配查找old text（先精确匹配，再模糊匹配）
                match_result = fuzzy_find_text(normalized_content, normalized_old_text)
                
                if not match_result.found:
                    return ToolResult.fail(
                        f"Error: Could not find the exact text in {path}. "
                        "The old text must match exactly including all whitespace and newlines."
                    )
                
                # 计算出现次数（使用模糊规范化内容以保持一致性）
                fuzzy_content = normalize_for_fuzzy_match(normalized_content)
                fuzzy_old_text = normalize_for_fuzzy_match(normalized_old_text)
                occurrences = fuzzy_content.count(fuzzy_old_text)
                
                # 如果有多个匹配
                if occurrences > 1:
                    return ToolResult.fail(
                        f"Error: Found {occurrences} occurrences of the text in {path}. "
                        "The text must be unique. Please provide more context to make it unique."
                    )
                
                # 执行替换（使用匹配到的文本位置）
                base_content = match_result.content_for_replacement
                new_content = (
                    base_content[:match_result.index] +
                    normalized_new_text +
                    base_content[match_result.index + match_result.match_length:]
                )
            
            # 验证替换实际改变了内容
            if base_content == new_content:
                return ToolResult.fail(
                    f"Error: No changes made to {path}. "
                    "The replacement produced identical content. "
                    "This might indicate an issue with special characters or the text not existing as expected."
                )
            
            # 恢复原始行尾符
            final_content = bom + restore_line_endings(new_content, original_ending)
            
            # 写入文件
            with open(absolute_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            # 生成差异
            diff_result = generate_diff_string(base_content, new_content)
            
            # 构建成功结果
            result = {
                "message": f"Successfully replaced text in {path}",  # 成功消息
                "path": path,               # 文件路径
                "diff": diff_result['diff'], # 差异字符串
                "first_changed_line": diff_result['first_changed_line']  # 第一行变更行号
            }
            
            # 如果文件在记忆目录中，通知记忆管理器
            if self.memory_manager and "memory/" in path:
                try:
                    self.memory_manager.mark_dirty()
                except Exception as e:
                    # 如果通知失败，不使编辑失败
                    pass
            
            return ToolResult.success(result)
            
        except UnicodeDecodeError:
            # 编码错误
            return ToolResult.fail(f"Error: File is not a valid text file (encoding error): {path}")
        except PermissionError:
            # 权限错误
            return ToolResult.fail(f"Error: Permission denied accessing {path}")
        except Exception as e:
            # 其他错误
            return ToolResult.fail(f"Error editing file: {str(e)}")
    
    def _resolve_path(self, path: str) -> str:
        """
        解析路径为绝对路径
        
        Args:
            path: 相对或绝对路径
            
        Returns:
            str: 绝对路径
        """
        # 扩展 ~ 为用户主目录
        path = expand_path(path)
        if os.path.isabs(path):
            return path
        # 相对路径基于工作目录
        return os.path.abspath(os.path.join(self.cwd, path))
