# -*- coding: utf-8 -*-
"""
Agent工具模块 - 工具基类

定义所有工具的基础类和通用接口：
- ToolStage: 工具执行阶段枚举
- ToolResult: 工具执行结果封装
- BaseTool: 工具基类

所有具体工具都应该继承 BaseTool 并实现 execute 方法。
"""

# 导入枚举类
from enum import Enum

# 导入类型提示
from typing import Any, Optional

# 导入日志模块
from common.log import logger

# 导入深拷贝功能
import copy


class ToolStage(Enum):
    """
    工具执行阶段枚举
    
    定义工具在Agent执行流程中的触发时机：
    - PRE_PROCESS: 前置处理阶段，需要Agent主动选择调用
    - POST_PROCESS: 后置处理阶段，在最终回答后自动执行
    """
    PRE_PROCESS = "pre_process"    # 前置处理：Agent主动选择
    POST_PROCESS = "post_process"  # 后置处理：自动执行


class ToolResult:
    """
    工具执行结果封装类
    
    用于封装工具执行的返回结果，包括：
    - status: 执行状态（success/error）
    - result: 执行结果内容
    - ext_data: 扩展数据（可选）
    
    提供两个静态工厂方法：
    - success(): 创建成功结果
    - fail(): 创建失败结果
    """
    
    def __init__(self, status: str = None, result: Any = None, ext_data: Any = None):
        """
        初始化工具结果
        
        Args:
            status: 执行状态（success/error）
            result: 执行结果
            ext_data: 扩展数据
        """
        self.status = status      # 执行状态
        self.result = result      # 执行结果
        self.ext_data = ext_data  # 扩展数据

    @staticmethod
    def success(result, ext_data: Any = None):
        """
        创建成功结果的工厂方法
        
        Args:
            result: 执行结果
            ext_data: 扩展数据（可选）
            
        Returns:
            ToolResult: 成功状态的结果实例
        """
        return ToolResult(status="success", result=result, ext_data=ext_data)

    @staticmethod
    def fail(result, ext_data: Any = None):
        """
        创建失败结果的工厂方法
        
        Args:
            result: 错误信息
            ext_data: 扩展数据（可选）
            
        Returns:
            ToolResult: 失败状态的结果实例
        """
        return ToolResult(status="error", result=result, ext_data=ext_data)


class BaseTool:
    """
    工具基类
    
    所有Agent工具都应该继承此类并实现 execute 方法。
    
    类属性（子类必须覆盖）：
    - name: 工具名称（唯一标识）
    - description: 工具描述
    - params: 参数JSON Schema
    - stage: 执行阶段（默认PRE_PROCESS）
    
    实例属性：
    - model: LLM模型实例
    - context: Agent上下文
    """

    # 默认执行阶段为前置处理
    stage = ToolStage.PRE_PROCESS

    # 类属性（子类必须继承并覆盖）
    name: str = "base_tool"        # 工具名称
    description: str = "Base tool" # 工具描述
    params: dict = {}              # 参数JSON Schema
    model: Optional[Any] = None    # LLM模型实例（类型取决于bot实现）

    @classmethod
    def get_json_schema(cls) -> dict:
        """
        获取工具的标准JSON Schema描述
        
        用于向LLM描述工具的功能和参数格式。
        
        Returns:
            dict: 包含name、description、parameters的字典
        """
        return {
            "name": cls.name,           # 工具名称
            "description": cls.description,  # 工具描述
            "parameters": cls.params    # 参数Schema
        }

    def execute_tool(self, params: dict) -> ToolResult:
        """
        执行工具的入口方法
        
        包装 execute 方法，提供异常捕获。
        
        Args:
            params: 工具参数字典
            
        Returns:
            ToolResult: 执行结果
        """
        try:
            # 调用子类实现的 execute 方法
            return self.execute(params)
        except Exception as e:
            # 捕获异常并记录日志
            logger.error(e)

    def execute(self, params: dict) -> ToolResult:
        """
        具体的工具执行逻辑（子类必须实现）
        
        Args:
            params: 工具参数字典
            
        Returns:
            ToolResult: 执行结果
        """
        # 基类不实现具体逻辑，子类必须覆盖
        raise NotImplementedError

    @classmethod
    def _parse_schema(cls) -> dict:
        """
        将JSON Schema转换为Pydantic字段定义
        
        用于参数验证和类型转换。
        
        Returns:
            dict: 字段名到(类型, 默认值)的映射
        """
        # 初始化字段字典
        fields = {}
        
        # 遍历参数属性
        for name, prop in cls.params["properties"].items():
            # JSON Schema类型到Python类型的映射
            type_map = {
                "string": str,    # 字符串
                "number": float,  # 数字（浮点）
                "integer": int,   # 整数
                "boolean": bool,  # 布尔值
                "array": list,    # 数组
                "object": dict    # 对象
            }
            # 构建字段元组（类型, 默认值）
            fields[name] = (
                type_map[prop["type"]],  # 获取对应的Python类型
                prop.get("default", ...)  # 获取默认值，无则使用...
            )
        
        return fields

    def should_auto_execute(self, context) -> bool:
        """
        判断此工具是否应该自动执行
        
        只有后置处理阶段的工具会自动执行。
        
        Args:
            context: Agent上下文
            
        Returns:
            bool: True表示应该自动执行
        """
        # 只有后置处理阶段的工具才会自动执行
        return self.stage == ToolStage.POST_PROCESS

    def close(self):
        """
        关闭工具使用的资源
        
        需要清理资源（如浏览器连接、文件句柄等）的工具应该覆盖此方法。
        
        默认情况下，此方法不执行任何操作。
        """
        pass
