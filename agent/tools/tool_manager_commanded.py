# -*- coding: utf-8 -*-
"""
工具管理器模块

管理Agent系统中所有工具的加载、配置和实例化。

主要功能：
1. 从目录动态加载工具类
2. 从配置文件中读取工具配置
3. 工具实例化工厂方法
4. 工具列表查询

ToolManager采用单例模式，确保全局只有一个工具管理器实例。
"""

# 导入动态导入模块
import importlib

# 导入动态导入规范模块
import importlib.util

# 导入路径处理模块
from pathlib import Path

# 导入类型提示
from typing import Dict, Any, Type

# 导入工具基类
from agent.tools.base_tool import BaseTool

# 导入日志模块
from common.log import logger

# 导入配置模块
from config import conf


class ToolManager:
    """
    工具管理器
    
    负责管理和加载所有可用的工具。
    采用单例模式，确保全局只有一个ToolManager实例。
    
    主要功能：
    1. 加载工具类：从目录或__init__.py中加载
    2. 配置工具：从配置文件读取工具参数
    3. 创建工具实例：根据名称创建工具实例
    4. 列出工具：查询所有已加载的工具
    """
    
    # 单例实例
    _instance = None

    def __new__(cls):
        """
        单例模式实现
        
        确保全局只有一个ToolManager实例。
        """
        if cls._instance is None:
            cls._instance = super(ToolManager, cls).__new__(cls)
            cls._instance.tool_classes = {}  # 存储工具类而非实例
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """
        初始化方法
        
        仅初始化一次。
        """
        # 仅初始化一次
        if not hasattr(self, 'tool_classes'):
            self.tool_classes = {}  # 存储工具类的字典

    def load_tools(self, tools_dir: str = "", config_dict=None):
        """
        从目录和配置加载工具
        
        Args:
            tools_dir: 工具模块目录路径
            config_dict: 工具配置字典
        """
        if tools_dir:
            # 从目录加载
            self._load_tools_from_directory(tools_dir)
            # 从配置加载
            self._configure_tools_from_config()
        else:
            # 从__init__加载
            self._load_tools_from_init()
            # 从配置加载
            self._configure_tools_from_config(config_dict)

    def _load_tools_from_init(self) -> bool:
        """
        从tools.__all__加载工具类
        
        Returns:
            如果工具加载成功返回True，否则返回False
        """
        try:
            # 尝试导入tools包
            tools_package = importlib.import_module("agent.tools")

            # 检查__all__是否定义
            if hasattr(tools_package, "__all__"):
                tool_classes = tools_package.__all__

                # 从tools包直接导入每个工具类
                for class_name in tool_classes:
                    try:
                        # 跳过基类
                        if class_name in ["BaseTool", "ToolManager"]:
                            continue

                        # 从tools包直接获取类
                        if hasattr(tools_package, class_name):
                            cls = getattr(tools_package, class_name)

                            # 检查是否是BaseTool的子类
                            if (
                                    isinstance(cls, type)
                                    and issubclass(cls, BaseTool)
                                    and cls != BaseTool
                            ):
                                try:
                                    # 跳过记忆工具（需要特殊的memory_manager初始化）
                                    if class_name in ["MemorySearchTool", "MemoryGetTool"]:
                                        logger.debug(f"Skipped tool {class_name} (requires memory_manager)")
                                        continue
                                    
                                    # 创建临时实例获取名称
                                    temp_instance = cls()
                                    tool_name = temp_instance.name
                                    # 存储类而非实例
                                    self.tool_classes[tool_name] = cls
                                    logger.debug(f"Loaded tool: {tool_name} from class {class_name}")
                                except ImportError as e:
                                    # 处理缺失依赖的错误
                                    error_msg = str(e)
                                    if "browser-use" in error_msg or "browser_use" in error_msg:
                                        logger.warning(
                                            f"[ToolManager] Browser tool not loaded - missing dependencies.\n"
                                            f"  To enable browser tool, run:\n"
                                            f"    pip install browser-use markdownify playwright\n"
                                            f"    playwright install chromium"
                                        )
                                    elif "markdownify" in error_msg:
                                        logger.warning(
                                            f"[ToolManager] {cls.__name__} not loaded - missing markdownify.\n"
                                            f"  Install with: pip install markdownify"
                                        )
                                    else:
                                        logger.warning(f"[ToolManager] {cls.__name__} not loaded due to missing dependency: {error_msg}")
                                except Exception as e:
                                    logger.error(f"Error initializing tool class {cls.__name__}: {e}")
                    except Exception as e:
                        logger.error(f"Error importing class {class_name}: {e}")

                return len(self.tool_classes) > 0
            return False
        except ImportError:
            logger.warning("Could not import agent.tools package")
            return False
        except Exception as e:
            logger.error(f"Error loading tools from __init__.__all__: {e}")
            return False

    def _load_tools_from_directory(self, tools_dir: str):
        """
        从目录动态加载工具类
        
        Args:
            tools_dir: 工具目录路径
        """
        tools_path = Path(tools_dir)

        # 遍历所有.py文件
        for py_file in tools_path.rglob("*.py"):
            # 跳过初始化文件和基类文件
            if py_file.name in ["__init__.py", "base_tool.py", "tool_manager.py"]:
                continue

            # 获取模块名
            module_name = py_file.stem

            try:
                # 从文件直接加载模块
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # 在模块中查找工具类
                    for attr_name in dir(module):
                        cls = getattr(module, attr_name)
                        if (
                                isinstance(cls, type)
                                and issubclass(cls, BaseTool)
                                and cls != BaseTool
                        ):
                            try:
                                # 跳过记忆工具
                                if attr_name in ["MemorySearchTool", "MemoryGetTool"]:
                                    logger.debug(f"Skipped tool {attr_name} (requires memory_manager)")
                                    continue
                                
                                # 创建临时实例获取名称
                                temp_instance = cls()
                                tool_name = temp_instance.name
                                # 存储类而非实例
                                self.tool_classes[tool_name] = cls
                            except ImportError as e:
                                # 处理缺失依赖
                                error_msg = str(e)
                                if "browser-use" in error_msg or "browser_use" in error_msg:
                                    logger.warning(
                                        f"[ToolManager] Browser tool not loaded - missing dependencies.\n"
                                        f"  To enable browser tool, run:\n"
                                        f"    pip install browser-use markdownify playwright\n"
                                        f"    playwright install chromium"
                                    )
                                elif "markdownify" in error_msg:
                                    logger.warning(
                                        f"[ToolManager] {cls.__name__} not loaded - missing markdownify.\n"
                                        f"  Install with: pip install markdownify"
                                    )
                                else:
                                    logger.warning(f"[ToolManager] {cls.__name__} not loaded due to missing dependency: {error_msg}")
                            except Exception as e:
                                logger.error(f"Error initializing tool class {cls.__name__}: {e}")
            except Exception as e:
                print(f"Error importing module {py_file}: {e}")

    def _configure_tools_from_config(self, config_dict=None):
        """
        根据配置文件配置工具类
        
        Args:
            config_dict: 工具配置字典
        """
        try:
            # 获取工具配置
            tools_config = config_dict or conf().get("tools", {})

            # 记录已配置但未加载的工具
            missing_tools = []

            # 存储配置以备后用
            self.tool_configs = tools_config

            # 检查哪些配置的工具缺失
            for tool_name in tools_config:
                if tool_name not in self.tool_classes:
                    missing_tools.append(tool_name)

            # 如果有缺失工具，记录警告
            if missing_tools:
                for tool_name in missing_tools:
                    if tool_name == "browser":
                        logger.warning(
                            f"[ToolManager] Browser tool is configured but not loaded.\n"
                            f"  To enable browser tool, run:\n"
                            f"    pip install browser-use markdownify playwright\n"
                            f"    playwright install chromium"
                        )
                    elif tool_name == "google_search":
                        logger.warning(
                            f"[ToolManager] Google Search tool is configured but may need API key.\n"
                            f"  Get API key from: https://serper.dev\n"
                            f"  Configure in config.json: tools.google_search.api_key"
                        )
                    else:
                        logger.warning(f"[ToolManager] Tool '{tool_name}' is configured but could not be loaded.")

        except Exception as e:
            logger.error(f"Error configuring tools from config: {e}")

    def create_tool(self, name: str) -> BaseTool:
        """
        根据名称获取新的工具实例
        
        Args:
            name: 工具名称
            
        Returns:
            工具实例，如果未找到返回None
        """
        tool_class = self.tool_classes.get(name)
        if tool_class:
            # 创建新实例
            tool_instance = tool_class()

            # 应用配置（如果有）
            if hasattr(self, 'tool_configs') and name in self.tool_configs:
                tool_instance.config = self.tool_configs[name]

            return tool_instance
        return None

    def list_tools(self) -> dict:
        """
        获取所有已加载工具的信息
        
        Returns:
            包含工具信息的字典
        """
        result = {}
        for name, tool_class in self.tool_classes.items():
            # 创建临时实例获取schema
            temp_instance = tool_class()
            result[name] = {
                "description": temp_instance.description,
                "parameters": temp_instance.get_json_schema()
            }
        return result
