# -*- coding: utf-8 -*-
"""
记忆获取工具

允许Agent读取记忆文件中的特定内容。
用于获取完整上下文或特定行范围。
"""

# 导入工具基类
from agent.tools.base_tool import BaseTool


class MemoryGetTool(BaseTool):
    """
    记忆获取工具类
    
    功能：
    - 读取记忆文件内容
    - 支持指定行范围
    - 自动添加memory/前缀
    
    使用场景：
    - 获取完整的记忆上下文
    - 读取特定日期的记忆
    - 查看MEMORY.md文件
    """
    
    # 工具名称
    name: str = "memory_get"
    
    # 工具描述
    description: str = (
        "Read specific content from memory files. "
        "Use this to get full context from a memory file or specific line range."
    )
    
    # 参数JSON Schema
    params: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the memory file (e.g. 'MEMORY.md', 'memory/2026-01-01.md')"
            },
            "start_line": {
                "type": "integer",
                "description": "Starting line number (optional, default: 1)",
                "default": 1
            },
            "num_lines": {
                "type": "integer",
                "description": "Number of lines to read (optional, reads all if not specified)"
            }
        },
        "required": ["path"]
    }
    
    def __init__(self, memory_manager):
        """
        初始化记忆获取工具
        
        Args:
            memory_manager: MemoryManager实例
        """
        # 调用父类初始化
        super().__init__()
        # 存储记忆管理器
        self.memory_manager = memory_manager
    
    def execute(self, args: dict):
        """
        执行记忆文件读取
        
        Args:
            args: 包含path, start_line, num_lines的字典
            
        Returns:
            ToolResult: 文件内容
        """
        # 导入结果类
        from agent.tools.base_tool import ToolResult
        
        # 获取参数
        path = args.get("path")                   # 文件路径
        start_line = args.get("start_line", 1)    # 起始行号
        num_lines = args.get("num_lines")         # 读取行数
        
        # 检查路径参数
        if not path:
            return ToolResult.fail("Error: path parameter is required")
        
        try:
            # 获取工作区目录
            workspace_dir = self.memory_manager.config.get_workspace()
            
            # 自动添加memory/前缀（如果不存在且不是绝对路径）
            # 例外：MEMORY.md在根目录
            if not path.startswith('memory/') and not path.startswith('/') and path != 'MEMORY.md':
                path = f'memory/{path}'
            
            # 构建文件路径
            file_path = workspace_dir / path
            
            # 检查文件是否存在
            if not file_path.exists():
                return ToolResult.fail(f"Error: File not found: {path}")
            
            # 读取文件内容
            content = file_path.read_text(encoding='utf-8')
            # 分割为行
            lines = content.split('\n')
            
            # 处理行范围
            if start_line < 1:
                start_line = 1
            
            # 转换为0索引
            start_idx = start_line - 1
            
            # 如果指定了行数
            if num_lines:
                end_idx = start_idx + num_lines
                selected_lines = lines[start_idx:end_idx]
            else:
                # 读取到末尾
                selected_lines = lines[start_idx:]
            
            # 合并选中行
            result = '\n'.join(selected_lines)
            
            # 添加元数据
            total_lines = len(lines)         # 总行数
            shown_lines = len(selected_lines)  # 显示行数
            
            # 构建输出
            output = [
                f"File: {path}",
                f"Lines: {start_line}-{start_line + shown_lines - 1} (total: {total_lines})",
                "",
                result
            ]
            
            return ToolResult.success('\n'.join(output))
            
        except Exception as e:
            # 错误处理
            return ToolResult.fail(f"Error reading memory file: {str(e)}")
