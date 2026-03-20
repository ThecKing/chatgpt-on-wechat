# -*- coding: utf-8 -*-
"""
Agent工具模块 - 包导出

导出所有可用的工具类：
- BaseTool: 工具基类
- ToolManager: 工具管理器
- 文件操作工具：Read, Write, Edit, Bash, Ls, Send
- 记忆工具：MemorySearchTool, MemoryGetTool
- 可选工具：EnvConfig, SchedulerTool, WebSearch, WebFetch, Vision
"""

# 导入工具基类
from agent.tools.base_tool import BaseTool

# 导入工具管理器
from agent.tools.tool_manager import ToolManager

# 导入文件操作工具
from agent.tools.read.read import Read        # 读取文件工具
from agent.tools.write.write import Write    # 写入文件工具
from agent.tools.edit.edit import Edit       # 编辑文件工具
from agent.tools.bash.bash import Bash       # 执行命令工具
from agent.tools.ls.ls import Ls             # 列出目录工具
from agent.tools.send.send import Send       # 发送消息工具

# 导入记忆工具
from agent.tools.memory.memory_search import MemorySearchTool  # 记忆搜索
from agent.tools.memory.memory_get import MemoryGetTool        # 获取记忆


def _import_optional_tools():
    """
    导入有可选依赖的工具
    
    某些工具需要额外的Python包才能使用，
    如果依赖缺失则跳过并记录错误日志。
    
    Returns:
        dict: 工具名称到工具类的映射
    """
    # 导入日志模块
    from common.log import logger
    
    # 初始化工具字典
    tools = {}
    
    # EnvConfig 工具（需要 python-dotenv）
    try:
        from agent.tools.env_config.env_config import EnvConfig
        tools['EnvConfig'] = EnvConfig
    except ImportError as e:
        # 记录缺失依赖的错误
        logger.error(
            f"[Tools] EnvConfig tool not loaded - missing dependency: {e}\n"
            f"  To enable environment variable management, run:\n"
            f"    pip install python-dotenv>=1.0.0"
        )
    except Exception as e:
        # 记录其他错误
        logger.error(f"[Tools] EnvConfig tool failed to load: {e}")
    
    # Scheduler 工具（需要 croniter）
    try:
        from agent.tools.scheduler.scheduler_tool import SchedulerTool
        tools['SchedulerTool'] = SchedulerTool
    except ImportError as e:
        # 记录缺失依赖的错误
        logger.error(
            f"[Tools] Scheduler tool not loaded - missing dependency: {e}\n"
            f"  To enable scheduled tasks, run:\n"
            f"    pip install croniter>=2.0.0"
        )
    except Exception as e:
        # 记录其他错误
        logger.error(f"[Tools] Scheduler tool failed to load: {e}")

    # WebSearch 工具（根据 API key 可用性条件加载）
    try:
        from agent.tools.web_search.web_search import WebSearch
        tools['WebSearch'] = WebSearch
    except ImportError as e:
        # 记录导入错误
        logger.error(f"[Tools] WebSearch not loaded - missing dependency: {e}")
    except Exception as e:
        # 记录其他错误
        logger.error(f"[Tools] WebSearch failed to load: {e}")

    # WebFetch 工具
    try:
        from agent.tools.web_fetch.web_fetch import WebFetch
        tools['WebFetch'] = WebFetch
    except ImportError as e:
        # 记录导入错误
        logger.error(f"[Tools] WebFetch not loaded - missing dependency: {e}")
    except Exception as e:
        # 记录其他错误
        logger.error(f"[Tools] WebFetch failed to load: {e}")

    # Vision 工具（根据 API key 可用性条件加载）
    try:
        from agent.tools.vision.vision import Vision
        tools['Vision'] = Vision
    except ImportError as e:
        # 记录导入错误
        logger.error(f"[Tools] Vision not loaded - missing dependency: {e}")
    except Exception as e:
        # 记录其他错误
        logger.error(f"[Tools] Vision failed to load: {e}")

    # 返回工具字典
    return tools


# 加载可选工具
_optional_tools = _import_optional_tools()

# 从可选工具字典中获取各个工具类（可能为 None）
EnvConfig = _optional_tools.get('EnvConfig')           # 环境配置工具
SchedulerTool = _optional_tools.get('SchedulerTool')   # 定时任务工具
WebSearch = _optional_tools.get('WebSearch')           # 网络搜索工具
WebFetch = _optional_tools.get('WebFetch')             # 网页抓取工具
Vision = _optional_tools.get('Vision')                 # 视觉识别工具
GoogleSearch = _optional_tools.get('GoogleSearch')     # Google搜索（预留）
FileSave = _optional_tools.get('FileSave')             # 文件保存（预留）
Terminal = _optional_tools.get('Terminal')             # 终端（预留）


def _import_browser_tool():
    """
    延迟导入 BrowserTool
    
    BrowserTool 需要 browser-use 包，如果未安装则返回占位类。
    
    Returns:
        BrowserTool 类或占位类
    """
    try:
        # 尝试导入 BrowserTool
        from agent.tools.browser.browser_tool import BrowserTool
        return BrowserTool
    except ImportError:
        # 如果导入失败，返回占位类
        class BrowserToolPlaceholder:
            """BrowserTool 占位类 - 提示用户安装依赖"""
            def __init__(self, *args, **kwargs):
                # 抛出导入错误，提示用户安装依赖
                raise ImportError(
                    "The 'browser-use' package is required to use BrowserTool. "
                    "Please install it with 'pip install browser-use>=0.1.40'."
                )

        return BrowserToolPlaceholder


# 动态设置 BrowserTool（当前已注释）
# BrowserTool = _import_browser_tool()


# 导出所有工具（包括可能为 None 的可选工具）
__all__ = [
    'BaseTool',           # 工具基类
    'ToolManager',        # 工具管理器
    'Read',               # 读取文件
    'Write',              # 写入文件
    'Edit',               # 编辑文件
    'Bash',               # 执行命令
    'Ls',                 # 列出目录
    'Send',               # 发送消息
    'MemorySearchTool',   # 记忆搜索
    'MemoryGetTool',      # 获取记忆
    'EnvConfig',          # 环境配置（可选）
    'SchedulerTool',      # 定时任务（可选）
    'WebSearch',          # 网络搜索（可选）
    'WebFetch',           # 网页抓取（可选）
    'Vision',             # 视觉识别（可选）
    # 可选工具（如果依赖未安装可能为 None）
    # 'BrowserTool'
]


"""
Tools module for Agent.

这个模块提供了Agent可以使用的所有工具。
工具是Agent与外部世界交互的主要方式，包括：
- 文件操作：读取、写入、编辑文件
- 命令执行：在终端执行命令
- 网络操作：搜索、抓取网页
- 记忆管理：搜索和获取长期记忆
- 其他功能：环境配置、定时任务等
"""
