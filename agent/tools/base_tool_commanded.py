# -*- coding: utf-8 -*-
"""
工具系统基类模块

这是所有工具的基类，定义了工具的基本结构、执行接口和通用方法。

主要类：
1. ToolStage: 枚举，定义工具的决策阶段
2. ToolResult: 工具执行结果封装类
3. BaseTool: 所有工具的基类

工具分类：
- 预处理工具（PRE_PROCESS）：需要Agent主动选择调用
- 后处理工具（POST_PROCESS）：Agent完成后自动执行（如发送文件）
"""

# 导入枚举类型
from enum import Enum

# 导入类型提示
from typing import Any, Optional

# 导入日志模块
from common.log import logger

# 导入拷贝模块
import copy


class ToolStage(Enum):
    """
    工具决策阶段枚举
    
    定义工具在Agent执行流程中的位置：
    - PRE_PROCESS: 预处理阶段，需要Agent主动选择和调用
    - POST_PROCESS: 后处理阶段，Agent完成主流程后自动执行
    """
    # 需要Agent主动选择的工具
    PRE_PROCESS = "pre_process"
    
    # Agent完成后自动执行的工具
    POST_PROCESS = "post_process"


class ToolResult:
    """
    工具执行结果封装类
    
    封装工具执行的状态、结果和额外数据。
    """
    
    def __init__(self, status: str = None, result: Any = None, ext_data: Any = None):
        """
        初始化工具结果
        
        Args:
            status: 执行状态，"success" 或 "error"
            result: 执行结果，可以是任意类型
            ext_data: 额外数据
        """
        self.status = status  # 执行状态
        self.result = result  # 执行结果
        self.ext_data = ext_data  # 额外数据

    @staticmethod
    def success(result, ext_data: Any = None):
        """
        创建成功结果
        
        Args:
            result: 执行结果
            ext_data: 额外数据
            
        Returns:
            ToolResult: 状态为success的结果对象
        """
        return ToolResult(status="success", result=result, ext_data=ext_data)

    @staticmethod
    def fail(result, ext_data: Any = None):
        """
        创建失败结果
        
        Args:
            result: 错误信息
            ext_data: 额外数据
            
        Returns:
            ToolResult: 状态为error的结果对象
        """
        return ToolResult(status="error", result=result, ext_data=ext_data)


class BaseTool:
    """
    工具基类
    
    所有具体工具都应继承此类，并实现execute方法。
    
    类属性：
    - name: 工具名称
    - description: 工具描述（用于LLM理解工具用途）
    - params: JSON Schema格式的参数定义
    - model: LLM模型实例
    - stage: 工具阶段（PRE_PROCESS或POST_PROCESS）
    
    使用示例：
        class MyTool(BaseTool):
            name = "my_tool"
            description = "这是一个示例工具"
            params = {
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "参数1"}
                },
                "required": ["arg1"]
            }
            
            def execute(self, params: dict) -> ToolResult:
                # 实现工具逻辑
                return ToolResult.success(f"处理: {params['arg1']}")
    """
    
    # 默认决策阶段是预处理
    stage = ToolStage.PRE_PROCESS

    # 类属性必须被继承
    name: str = "base_tool"  # 工具名称
    description: str = "Base tool"  # 工具描述
    params: dict = {}  # 存储JSON Schema
    model: Optional[Any] = None  # LLM模型实例，类型取决于bot实现

    @classmethod
    def get_json_schema(cls) -> dict:
        """
        获取工具的标准描述
        
        返回符合工具调用规范的JSON Schema。
        
        Returns:
            包含name、description、parameters的字典
        """
        return {
            "name": cls.name,
            "description": cls.description,
            "parameters": cls.params
        }

    def execute_tool(self, params: dict) -> ToolResult:
        """
        执行工具的包装方法
        
        捕获异常并转换为ToolResult格式。
        
        Args:
            params: 工具参数
            
        Returns:
            ToolResult: 执行结果
        """
        try:
            return self.execute(params)
        except Exception as e:
            logger.error(e)

    def execute(self, params: dict) -> ToolResult:
        """
        执行工具的具体逻辑（需子类实现）
        
        Args:
            params: 工具参数字典
            
        Returns:
            ToolResult: 执行结果
            
        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError

    @classmethod
    def _parse_schema(cls) -> dict:
        """
        将JSON Schema转换为Pydantic字段
        
        用于内部验证和处理参数。
        
        Returns:
            字段字典
        """
        fields = {}
        for name, prop in cls.params["properties"].items():
            # JSON Schema类型映射到Python类型
            type_map = {
                "string": str,
                "number": float,
                "integer": int,
                "boolean": bool,
                "array": list,
                "object": dict
            }
            fields[name] = (
                type_map[prop["type"]],
                prop.get("default", ...)
            )
        return fields

    def should_auto_execute(self, context) -> bool:
        """
        判断此工具是否应根据上下文自动执行
        
        Args:
            context: Agent上下文
            
        Returns:
            如果工具应执行返回True，否则返回False
        """
        # 只有后处理阶段的工具才会自动执行
        return self.stage == ToolStage.POST_PROCESS

    def close(self):
        """
        关闭工具使用的任何资源
        
        此方法应被需要清理资源（如浏览器连接、文件句柄等）的工具覆盖。
        
        默认情况下，此方法不执行任何操作。
        """
        pass
