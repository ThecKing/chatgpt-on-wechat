# -*- coding: utf-8 -*-
"""
写入文件工具

创建或覆盖文件，自动创建父目录。
支持单次写入不超过10KB的内容。
大文件应先创建骨架，再用edit工具分块添加内容。
"""

# 导入操作系统模块
import os

# 导入类型提示
from typing import Dict, Any

# 导入路径处理
from pathlib import Path

# 导入工具基类和结果类
from agent.tools.base_tool import BaseTool, ToolResult

# 导入路径扩展工具
from common.utils import expand_path


class Write(BaseTool):
    """
    写入文件工具类
    
    功能：
    - 创建新文件
    - 覆盖现有文件
    - 自动创建父目录
    
    限制：
    - 单次写入不超过10KB
    - 大文件应分块写入
    """
    
    # 工具名称
    name: str = "write"
    
    # 工具描述
    description: str = "Write content to a file. Creates the file if it doesn't exist, overwrites if it does. Automatically creates parent directories. IMPORTANT: Single write should not exceed 10KB. For large files, create a skeleton first, then use edit to add content in chunks."
    
    # 参数JSON Schema
    params: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write (relative or absolute)"
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file"
            }
        },
        "required": ["path", "content"]
    }
    
    def __init__(self, config: dict = None):
        """
        初始化写入工具
        
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
        执行文件写入操作
        
        Args:
            args: 包含文件路径和内容
                - path: 文件路径
                - content: 要写入的内容
            
        Returns:
            ToolResult: 操作结果
        """
        # 获取参数
        path = args.get("path", "").strip()   # 文件路径
        content = args.get("content", "")      # 文件内容
        
        # 检查路径参数
        if not path:
            return ToolResult.fail("Error: path parameter is required")
        
        # 解析路径
        absolute_path = self._resolve_path(path)
        
        try:
            # 创建父目录（如果需要）
            parent_dir = os.path.dirname(absolute_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            
            # 写入文件
            with open(absolute_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 计算写入字节数
            bytes_written = len(content.encode('utf-8'))
            
            # 如果是记忆文件，自动同步到记忆数据库
            if self.memory_manager and 'memory/' in path:
                self.memory_manager.mark_dirty()
            
            # 构建成功结果
            result = {
                "message": f"Successfully wrote {bytes_written} bytes to {path}",  # 成功消息
                "path": path,               # 文件路径
                "bytes_written": bytes_written  # 写入字节数
            }
            
            return ToolResult.success(result)
            
        except PermissionError:
            # 权限错误
            return ToolResult.fail(f"Error: Permission denied writing to {path}")
        except Exception as e:
            # 其他错误
            return ToolResult.fail(f"Error writing file: {str(e)}")
    
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
