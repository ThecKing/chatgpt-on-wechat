# -*- coding: utf-8 -*-
"""
记忆搜索工具

允许Agent使用语义和关键词搜索其长期记忆。
用于回忆过去的对话、偏好和知识。
"""

# 导入类型提示
from typing import Dict, Any, Optional

# 导入工具基类
from agent.tools.base_tool import BaseTool


class MemorySearchTool(BaseTool):
    """
    记忆搜索工具类
    
    功能：
    - 语义搜索长期记忆
    - 关键词搜索
    - 支持限定用户范围
    
    使用场景：
    - 回忆过去的对话
    - 查找用户偏好
    - 检索存储的知识
    """
    
    # 工具名称
    name: str = "memory_search"
    
    # 工具描述
    description: str = (
        "Search agent's long-term memory using semantic and keyword search. "
        "Use this to recall past conversations, preferences, and knowledge."
    )
    
    # 参数JSON Schema
    params: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (can be natural language question or keywords)"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 10)",
                "default": 10
            },
            "min_score": {
                "type": "number",
                "description": "Minimum relevance score (0-1, default: 0.1)",
                "default": 0.1
            }
        },
        "required": ["query"]
    }
    
    def __init__(self, memory_manager, user_id: Optional[str] = None):
        """
        初始化记忆搜索工具
        
        Args:
            memory_manager: MemoryManager实例
            user_id: 可选的用户ID，用于限定搜索范围
        """
        # 调用父类初始化
        super().__init__()
        # 存储记忆管理器
        self.memory_manager = memory_manager
        # 存储用户ID
        self.user_id = user_id
    
    def execute(self, args: dict):
        """
        执行记忆搜索
        
        Args:
            args: 包含query, max_results, min_score的字典
            
        Returns:
            ToolResult: 格式化的搜索结果
        """
        # 导入结果类
        from agent.tools.base_tool import ToolResult
        # 导入异步IO模块
        import asyncio
        
        # 获取参数
        query = args.get("query")                    # 搜索查询
        max_results = args.get("max_results", 10)    # 最大结果数
        min_score = args.get("min_score", 0.1)       # 最小相关性分数
        
        # 检查查询参数
        if not query:
            return ToolResult.fail("Error: query parameter is required")
        
        try:
            # 在同步上下文中运行异步搜索
            results = asyncio.run(self.memory_manager.search(
                query=query,               # 搜索查询
                user_id=self.user_id,      # 用户ID
                max_results=max_results,   # 最大结果数
                min_score=min_score,       # 最小分数
                include_shared=True        # 包含共享记忆
            ))
            
            # 如果没有结果
            if not results:
                # 返回清晰的消息表示还没有记忆
                # 这防止无限重试循环
                return ToolResult.success(
                    f"No memories found for '{query}'. "
                    f"This is normal if no memories have been stored yet. "
                    f"You can store new memories by writing to MEMORY.md or memory/YYYY-MM-DD.md files."
                )
            
            # 格式化结果
            output = [f"Found {len(results)} relevant memories:\n"]
            
            # 遍历结果
            for i, result in enumerate(results, 1):
                # 添加结果信息
                output.append(f"\n{i}. {result.path} (lines {result.start_line}-{result.end_line})")
                output.append(f"   Score: {result.score:.3f}")
                output.append(f"   Snippet: {result.snippet}")
            
            return ToolResult.success("\n".join(output))
            
        except Exception as e:
            # 错误处理
            return ToolResult.fail(f"Error searching memory: {str(e)}")
