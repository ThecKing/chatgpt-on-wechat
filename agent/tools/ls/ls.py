# -*- coding: utf-8 -*-
"""
列出目录内容工具

列出目录中的文件和子目录：
- 按字母顺序排序
- 目录以'/'后缀标识
- 包含隐藏文件
- 支持条目数量和字节限制
"""

# 导入操作系统模块
import os

# 导入类型提示
from typing import Dict, Any

# 导入工具基类和结果类
from agent.tools.base_tool import BaseTool, ToolResult

# 导入截断工具
from agent.tools.utils.truncate import truncate_head, format_size, DEFAULT_MAX_BYTES

# 导入路径扩展工具
from common.utils import expand_path


# 默认条目限制
DEFAULT_LIMIT = 500


class Ls(BaseTool):
    """
    列出目录内容工具类
    
    功能：
    - 列出目录中的文件和子目录
    - 字母顺序排序
    - 目录标识为 name/
    - 包含隐藏文件
    """
    
    # 工具名称
    name: str = "ls"
    
    # 工具描述
    description: str = f"List directory contents. Returns entries sorted alphabetically, with '/' suffix for directories. Includes dotfiles. Output is truncated to {DEFAULT_LIMIT} entries or {DEFAULT_MAX_BYTES // 1024}KB (whichever is hit first)."
    
    # 参数JSON Schema
    params: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory to list. IMPORTANT: Relative paths are based on workspace directory. To access directories outside workspace, use absolute paths starting with ~ or /."
            },
            "limit": {
                "type": "integer",
                "description": f"Maximum number of entries to return (default: {DEFAULT_LIMIT})"
            }
        },
        "required": []
    }
    
    def __init__(self, config: dict = None):
        """
        初始化Ls工具
        
        Args:
            config: 配置字典，可包含：
                - cwd: 工作目录
        """
        # 存储配置
        self.config = config or {}
        # 获取工作目录
        self.cwd = self.config.get("cwd", os.getcwd())
    
    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        执行目录列表操作
        
        Args:
            args: 列表参数
                - path: 目录路径（默认当前目录）
                - limit: 最大条目数
            
        Returns:
            ToolResult: 目录内容或错误
        """
        # 获取参数
        path = args.get("path", ".").strip()      # 目录路径
        limit = args.get("limit", DEFAULT_LIMIT)  # 最大条目数
        
        # 解析路径
        absolute_path = self._resolve_path(path)
        
        # 安全检查：防止访问敏感配置目录
        env_config_dir = expand_path("~/.cow")
        if os.path.abspath(absolute_path) == os.path.abspath(env_config_dir):
            return ToolResult.fail(
                "Error: Access denied. API keys and credentials must be accessed through the env_config tool only."
            )
        
        # 检查路径是否存在
        if not os.path.exists(absolute_path):
            # 如果使用相对路径，提供有用提示
            if not os.path.isabs(path) and not path.startswith('~'):
                return ToolResult.fail(
                    f"Error: Path not found: {path}\n"
                    f"Resolved to: {absolute_path}\n"
                    f"Hint: Relative paths are based on workspace ({self.cwd}). For files outside workspace, use absolute paths."
                )
            return ToolResult.fail(f"Error: Path not found: {path}")
        
        # 检查是否是目录
        if not os.path.isdir(absolute_path):
            return ToolResult.fail(f"Error: Not a directory: {path}")
        
        try:
            # 读取目录条目
            entries = os.listdir(absolute_path)
            
            # 按字母顺序排序（不区分大小写）
            entries.sort(key=lambda x: x.lower())
            
            # 格式化条目（添加目录标识）
            results = []
            entry_limit_reached = False
            
            for entry in entries:
                # 检查条目限制
                if len(results) >= limit:
                    entry_limit_reached = True
                    break
                
                # 获取完整路径
                full_path = os.path.join(absolute_path, entry)
                
                try:
                    # 判断是否是目录
                    if os.path.isdir(full_path):
                        results.append(entry + '/')  # 目录添加/后缀
                    else:
                        results.append(entry)       # 文件不添加后缀
                except Exception:
                    # 跳过无法访问的条目
                    continue
            
            # 如果没有条目
            if not results:
                return ToolResult.success({"message": "(empty directory)", "entries": []})
            
            # 格式化输出
            raw_output = '\n'.join(results)
            truncation = truncate_head(raw_output, max_lines=999999)  # 只限制字节数
            
            output = truncation.content
            details = {}
            notices = []
            
            # 添加条目限制提示
            if entry_limit_reached:
                notices.append(f"{limit} entries limit reached. Use limit={limit * 2} for more")
                details["entry_limit_reached"] = limit
            
            # 添加截断提示
            if truncation.truncated:
                notices.append(f"{format_size(DEFAULT_MAX_BYTES)} limit reached")
                details["truncation"] = truncation.to_dict()
            
            # 添加提示信息
            if notices:
                output += f"\n\n[{'. '.join(notices)}]"
            
            return ToolResult.success({
                "output": output,               # 输出内容
                "entry_count": len(results),    # 条目数量
                "details": details if details else None  # 详情
            })
            
        except PermissionError:
            # 权限错误
            return ToolResult.fail(f"Error: Permission denied reading directory: {path}")
        except Exception as e:
            # 其他错误
            return ToolResult.fail(f"Error listing directory: {str(e)}")
    
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
