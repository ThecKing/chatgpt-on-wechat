# -*- coding: utf-8 -*-
"""
插件管理器模块

该模块负责插件的加载、卸载、启用、禁用、事件触发等核心功能。
是整个插件系统的核心管理器。

主要功能：
1. 插件注册（@register装饰器）
2. 插件扫描（scan_plugins）
3. 插件配置管理（load_config, save_config）
4. 插件实例化（activate_plugins）
5. 事件触发与传播（emit_event）
6. 插件安装、卸载、更新（install_plugin, uninstall_plugin, update_plugin）
7. 插件优先级管理（set_plugin_priority）

插件工作流程：
1. 启动时加载配置文件（plugins.json）
2. 扫描插件目录，发现并导入插件
3. 根据配置启用/禁用插件
4. 实例化已启用的插件
5. 消息到达时，触发事件，插件可以拦截或处理
"""

# 设置文件编码为UTF-8，支持中文注释
# encoding:utf-8

# 导入动态导入模块，用于运行时导入插件模块
import importlib

# 导入动态导入工具，用于从文件路径导入模块
import importlib.util

# 导入JSON模块，用于读写插件配置文件
import json

# 导入操作系统模块，用于文件路径操作、目录遍历等
import os

# 导入系统模块，用于管理系统模块缓存、获取模块信息等
import sys

# 从common.log导入日志模块，记录程序运行日志
from common.log import logger

# 从common.singleton导入单例装饰器，确保全局只有一个PluginManager实例
from common.singleton import singleton

# 从common.sorted_dict导入有序字典，用于按优先级排序插件
from common.sorted_dict import SortedDict

# 从config导入配置相关函数：
# conf(): 获取配置对象
# remove_plugin_config(): 移除插件配置
# write_plugin_config(): 写入插件配置
from config import conf, remove_plugin_config, write_plugin_config

# 从当前包的event模块导入所有内容
# 包括：Event（事件类型枚举）、EventContext（事件上下文类）、EventAction（事件动作枚举）
from .event import *


@singleton
class PluginManager:
    """
    插件管理器类
    
    使用@singleton装饰器，确保全局只有一个PluginManager实例。
    负责管理所有插件的生命周期和事件触发。
    
    属性说明：
    - plugins: 有序字典，存储所有已注册的插件类，按优先级排序
    - listening_plugins: 字典，存储监听各事件的插件列表
    - instances: 字典，存储已实例化的插件对象
    - pconf: 字典，插件配置信息
    - current_plugin_path: 当前正在加载的插件路径
    - loaded: 字典，记录已加载的插件模块
    """
    
    def __init__(self):
        """
        插件管理器初始化
        
        初始化插件管理器的各个数据结构：
        - plugins: 使用SortedDict，按priority字段降序排列
        - listening_plugins: 事件名 -> 插件名列表的映射
        - instances: 插件名 -> 插件实例的映射
        - pconf: 插件配置字典
        - current_plugin_path: 当前加载路径（用于register装饰器）
        - loaded: 已加载模块的缓存
        """
        # 创建有序字典，按priority降序排列插件（扫描文件路径的）
        # key: 插件名(大写), value: 插件类
        self.plugins = SortedDict(lambda k, v: v.priority, reverse=True)
        
        # 存储监听各事件的插件列表
        # key: 事件名(Event枚举), value: 插件名列表
        self.listening_plugins = {}
        
        # 存储已实例化的插件对象
        # key: 插件名(大写), value: 插件实例
        self.instances = {}
        
        # 存储插件配置信息（从json配置文件中扫描）
        # 结构: {"plugins": {插件名: {enabled: bool, priority: int}}}
        self.pconf = {}
        
        # 当前正在加载的插件路径
        # 在register装饰器中使用，记录当前正在解析哪个插件
        self.current_plugin_path = None
        
        # 已加载的插件模块缓存
        # key: 插件路径, value: 模块对象或reload后的模块
        self.loaded = {}

    def register(self, name: str, desire_priority: int = 0, **kwargs):
        """
        插件注册装饰器
        
        这是一个装饰器工厂，用于注册插件类。
        使用方式：@plugin_manager.register("插件名", 优先级)
        
        Args:
            name: 插件名称
            desire_priority: 期望的优先级，数值越大越先执行，默认0
            **kwargs: 额外参数，如desc、author、version、namecn、hidden等
            
        Returns:
            wrapper: 装饰器函数
        """
        def wrapper(plugincls):
            """
            实际的装饰器函数
            
            为插件类设置元数据，并将其注册到plugins字典中。
            """
            # 设置插件名称
            plugincls.name = name
            
            # 设置插件优先级
            plugincls.priority = desire_priority
            
            # 设置插件描述（可选）
            plugincls.desc = kwargs.get("desc")
            
            # 设置插件作者（可选）
            plugincls.author = kwargs.get("author")
            
            # 设置插件路径（当前正在加载的插件目录）
            plugincls.path = self.current_plugin_path
            
            # 设置插件版本，默认1.0
            plugincls.version = kwargs.get("version") if kwargs.get("version") != None else "1.0"
            
            # 设置插件中文名，默认使用英文名
            plugincls.namecn = kwargs.get("namecn") if kwargs.get("namecn") != None else name
            
            # 设置是否隐藏（隐藏插件不出现在插件列表中）
            plugincls.hidden = kwargs.get("hidden") if kwargs.get("hidden") != None else False
            
            # 设置插件是否启用，默认启用
            plugincls.enabled = True
            
            # 检查插件路径是否设置（必须在scan_plugins中使用）
            if self.current_plugin_path == None:
                raise Exception("Plugin path not set")
                
            # 将插件注册到plugins字典（键名为大写）
            self.plugins[name.upper()] = plugincls
            
            # 记录调试日志
            logger.debug("Plugin %s_v%s registered, path=%s" % (name, plugincls.version, plugincls.path))

        return wrapper

    def save_config(self):
        """
        保存插件配置到文件
        
        将当前的pconf（插件配置）保存到 plugins.json 文件中。
        """
        # 以UTF-8编码写入JSON文件
        with open("./plugins/plugins.json", "w", encoding="utf-8") as f:
            # 格式化写入，indent=4表示缩进4空格，ensure_ascii=False允许中文
            json.dump(self.pconf, f, indent=4, ensure_ascii=False)

    def load_config(self):
        """
        加载插件配置文件
        
        从 plugins.json 加载插件配置。
        如果文件不存在，则创建默认配置。
        
        Returns:
            pconf: 插件配置字典
        """
        logger.debug("Loading plugins config...")

        # 标记配置是否被修改（新建或缺失字段）
        modified = False
        
        # 检查配置文件是否存在
        if os.path.exists("./plugins/plugins.json"):
            # 存在则读取
            with open("./plugins/plugins.json", "r", encoding="utf-8") as f:
                pconf = json.load(f)
                # 将plugins也转为有序字典，按priority降序
                pconf["plugins"] = SortedDict(lambda k, v: v["priority"], pconf["plugins"], reverse=True)
        else:
            # 不存在则创建默认配置
            modified = True
            pconf = {"plugins": SortedDict(lambda k, v: v["priority"], reverse=True)}
            
        # 保存到实例属性
        self.pconf = pconf
        
        # 如果是新创建的配置文件，保存一次
        if modified:
            self.save_config()
            
        return pconf

    @staticmethod
    def _load_all_config():
        """
        加载所有插件的统一配置
        
        背景：
        之前插件配置存放在每个插件目录的config.json下，
        Docker运行时不方便映射目录，故增加统一管理入口。
        
        功能：
        从 plugins/config.json 加载所有插件的配置，
        并写入全局配置中，供插件通过 config.pconf(plugin_name) 获取。
        """
        # 统一配置文件路径
        all_config_path = "./plugins/config.json"
        
        try:
            # 检查文件是否存在
            if os.path.exists(all_config_path):
                # 从统一配置文件读取
                with open(all_config_path, "r", encoding="utf-8") as f:
                    all_conf = json.load(f)
                    logger.info(f"load all config from plugins/config.json: {all_conf}")

                # 写入全局配置（供config.pconf()使用）
                write_plugin_config(all_conf)
                
        except Exception as e:
            # 捕获异常并记录错误日志
            logger.error(e)

    def scan_plugins(self):
        """
        扫描并加载插件
        
        扫描 plugins 目录下的所有子目录，
        发现包含 __init__.py 的模块并导入，
        自动执行 @register 装饰器注册插件。
        
        Returns:
            new_plugins: 新发现的插件列表
        """
        logger.debug("Scanning plugins ...")
        
        # 插件目录路径
        plugins_dir = "./plugins"
        
        # 记录扫描前的已有插件
        raws = [self.plugins[name] for name in self.plugins]
        
        # 遍历插件目录下的所有项
        for plugin_name in os.listdir(plugins_dir):
            # 拼接完整路径
            plugin_path = os.path.join(plugins_dir, plugin_name)
            
            # 只处理目录
            if os.path.isdir(plugin_path):
                # 判断插件是否包含同名__init__.py文件（Python包标识）
                main_module_path = os.path.join(plugin_path, "__init__.py")
                
                if os.path.isfile(main_module_path):
                    # 构造导入路径：plugins.插件名
                    import_path = "plugins.{}".format(plugin_name)
                    
                    try:
                        # 设置当前插件路径（供register装饰器使用）
                        self.current_plugin_path = plugin_path
                        
                        # 检查是否已加载过
                        if plugin_path in self.loaded:
                            # 非GODCMD插件可以重载
                            if plugin_name.upper() != 'GODCMD':
                                logger.info("reload module %s" % plugin_name)
                                # 重新加载模块
                                self.loaded[plugin_path] = importlib.reload(sys.modules[import_path])
                                
                                # 找出所有依赖模块并重载
                                dependent_module_names = [name for name in sys.modules.keys() if name.startswith(import_path + ".")]
                                for name in dependent_module_names:
                                    logger.info("reload module %s" % name)
                                    importlib.reload(sys.modules[name])
                        else:
                            # 首次加载，导入模块
                            self.loaded[plugin_path] = importlib.import_module(import_path)
                            
                        # 加载完成，清空当前路径
                        self.current_plugin_path = None
                        
                    except Exception as e:
                        # 导入失败，记录警告并跳过
                        logger.warn("Failed to import plugin %s: %s" % (plugin_name, e))
                        continue
                        
        # 获取当前所有已注册的插件
        pconf = self.pconf
        news = [self.plugins[name] for name in self.plugins]
        
        # 计算新增的插件（新注册但未在配置中的）
        new_plugins = list(set(news) - set(raws))
        
        # 标记配置是否被修改
        modified = False
        
        # 遍历所有插件，检查配置
        for name, plugincls in self.plugins.items():
            # 获取插件原始名称
            rawname = plugincls.name
            
            # 如果配置中没有该插件，添加到配置
            if rawname not in pconf["plugins"]:
                modified = True
                logger.info("Plugin %s not found in pconfig, adding to pconfig..." % name)
                pconf["plugins"][rawname] = {
                    "enabled": plugincls.enabled,  # 是否启用
                    "priority": plugincls.priority,  # 优先级
                }
            else:
                # 配置中已有，从配置读取启用状态和优先级
                self.plugins[name].enabled = pconf["plugins"][rawname]["enabled"]
                self.plugins[name].priority = pconf["plugins"][rawname]["priority"]
                # 更新有序堆（保持排序）
                self.plugins._update_heap(name)
                
        # 如果有修改，保存配置
        if modified:
            self.save_config()
            
        return new_plugins

    def refresh_order(self):
        """
        刷新事件监听插件的优先级顺序
        
        根据plugins中各插件的priority重新排序listening_plugins中的列表。
        """
        # 遍历所有事件
        for event in self.listening_plugins.keys():
            # 按priority降序排序
            self.listening_plugins[event].sort(key=lambda name: self.plugins[name].priority, reverse=True)

    def activate_plugins(self):
        """
        激活已启用的插件（实例化）
        
        遍历所有插件，对已启用的插件进行实例化，
        并注册到事件监听列表中。
        
        Returns:
            failed_plugins: 激活失败的插件名列表
        """
        # 记录激活失败的插件
        failed_plugins = []
        
        # 遍历所有插件
        for name, plugincls in self.plugins.items():
            # 只处理已启用的插件
            if plugincls.enabled:
                # 跳过GODCMD（特殊插件，只能有一个实例）
                if 'GODCMD' in self.instances and name == 'GODCMD':
                    continue
                    
                # 尝试实例化插件
                # if name not in self.instances:  # 原有的判断已删除
                try:
                    instance = plugincls()
                except Exception as e:
                    # 实例化失败，禁用插件
                    logger.warn("Failed to init %s, diabled. %s" % (name, e))
                    self.disable_plugin(name)
                    failed_plugins.append(name)
                    continue
                    
                # 如果已存在实例，先清空handlers
                if name in self.instances:
                    self.instances[name].handlers.clear()
                    
                # 保存实例
                self.instances[name] = instance
                
                # 注册到事件监听列表
                for event in instance.handlers:
                    if event not in self.listening_plugins:
                        self.listening_plugins[event] = []
                    self.listening_plugins[event].append(name)
                    
        # 刷新优先级顺序
        self.refresh_order()
        
        return failed_plugins

    def reload_plugin(self, name: str):
        """
        重新加载指定插件
        
        流程：
        1. 移除插件配置
        2. 清除实例和事件监听
        3. 重新激活插件
        
        Args:
            name: 插件名称
            
        Returns:
            bool: 是否成功重新加载
        """
        # 统一转为大写
        name = name.upper()
        
        # 移除插件配置
        remove_plugin_config(name)
        
        # 如果插件已有实例
        if name in self.instances:
            # 从事件监听列表中移除
            for event in self.listening_plugins:
                if name in self.listening_plugins[event]:
                    self.listening_plugins[event].remove(name)
                    
            # 清空handlers
            if name in self.instances:
                self.instances[name].handlers.clear()
                
            # 删除实例
            del self.instances[name]
            
            # 重新激活
            self.activate_plugins()
            return True
            
        return False

    def load_plugins(self):
        """
        加载所有插件的主入口
        
        完整的插件加载流程：
        1. 加载配置文件
        2. 扫描并注册插件
        3. 加载全量插件配置
        4. 激活已启用的插件
        """
        # 步骤1：加载配置文件
        self.load_config()
        
        # 步骤2：扫描并注册插件
        self.scan_plugins()
        
        # 步骤3：加载全量插件配置（plugins/config.json）
        self._load_all_config()
        
        # 获取配置
        pconf = self.pconf
        logger.debug("plugins.json config={}".format(pconf))
        
        # 检查配置中有的插件是否都已注册
        for name, plugin in pconf["plugins"].items():
            if name.upper() not in self.plugins:
                logger.error("Plugin %s not found, but found in plugins.json" % name)
                
        # 步骤4：激活已启用的插件
        self.activate_plugins()

    def emit_event(self, e_context: EventContext, *args, **kwargs):
        """
        触发事件，通知所有监听该事件的插件
        
        这是插件系统的核心机制。
        当有消息到达或需要处理时，调用此方法触发相应事件，
        所有监听该事件的插件按优先级顺序执行。
        
        Args:
            e_context: 事件上下文对象，包含事件类型和相关数据
            *args: 额外的位置参数
            **kwargs: 额外的关键字参数
            
        Returns:
            e_context: 处理后的事件上下文对象
        """
        # 检查是否有插件监听该事件
        if e_context.event in self.listening_plugins:
            # 遍历监听该事件的插件
            for name in self.listening_plugins[e_context.event]:
                # 检查插件是否启用且事件动作是CONTINUE
                if self.plugins[name].enabled and e_context.action == EventAction.CONTINUE:
                    # 记录调试日志
                    logger.debug("Plugin %s triggered by event %s" % (name, e_context.event))
                    
                    # 获取插件实例
                    instance = self.instances[name]
                    
                    # 调用插件的事件处理函数
                    # 传入事件上下文和额外参数
                    instance.handlers[e_context.event](e_context, *args, **kwargs)
                    
                    # 检查是否中断（插件标记为break）
                    if e_context.is_break():
                        # 记录中断信息
                        e_context["breaked_by"] = name
                        logger.debug("Plugin %s breaked event %s" % (name, e_context.event))
                        
        # 返回处理后的上下文
        return e_context

    def set_plugin_priority(self, name: str, priority: int):
        """
        设置插件优先级
        
        Args:
            name: 插件名称
            priority: 新的优先级
            
        Returns:
            bool: 是否设置成功
        """
        # 统一转为大写
        name = name.upper()
        
        # 插件不存在
        if name not in self.plugins:
            return False
            
        # 优先级未变
        if self.plugins[name].priority == priority:
            return True
            
        # 更新插件优先级
        self.plugins[name].priority = priority
        # 更新有序堆
        self.plugins._update_heap(name)
        
        # 获取原始名称
        rawname = self.plugins[name].name
        
        # 更新配置中的优先级
        self.pconf["plugins"][rawname]["priority"] = priority
        self.pconf["plugins"]._update_heap(rawname)
        
        # 保存配置
        self.save_config()
        
        # 刷新事件监听顺序
        self.refresh_order()
        
        return True

    def enable_plugin(self, name: str):
        """
        启用插件
        
        Args:
            name: 插件名称
            
        Returns:
            tuple: (是否成功, 消息)
        """
        # 统一转为大写
        name = name.upper()
        
        # 插件不存在
        if name not in self.plugins:
            return False, "插件不存在"
            
        # 如果当前未启用
        if not self.plugins[name].enabled:
            # 设置为启用
            self.plugins[name].enabled = True
            rawname = self.plugins[name].name
            self.pconf["plugins"][rawname]["enabled"] = True
            
            # 保存配置
            self.save_config()
            
            # 重新激活插件
            failed_plugins = self.activate_plugins()
            
            # 检查是否激活失败
            if name in failed_plugins:
                return False, "插件开启失败"
                
            return True, "插件已开启"
            
        return True, "插件已开启"

    def disable_plugin(self, name: str):
        """
        禁用插件
        
        Args:
            name: 插件名称
            
        Returns:
            tuple: (是否成功, 消息)
        """
        # 统一转为大写
        name = name.upper()
        
        # 插件不存在
        if name not in self.plugins:
            return False
            
        # 如果当前已启用
        if self.plugins[name].enabled:
            # 设置为禁用
            self.plugins[name].enabled = False
            rawname = self.plugins[name].name
            self.pconf["plugins"][rawname]["enabled"] = False
            
            # 保存配置
            self.save_config()
            
        return True

    def list_plugins(self):
        """
        列出所有已注册的插件
        
        Returns:
            plugins: 插件有序字典
        """
        return self.plugins

    def install_plugin(self, repo: str):
        """
        安装插件（从Git仓库克隆）
        
        支持两种安装方式：
        1. 直接提供Git仓库URL
        2. 从source.json中查找仓库URL
        
        Args:
            repo: Git仓库地址或source.json中的别名
            
        Returns:
            tuple: (是否成功, 消息)
        """
        try:
            # 尝试导入dulwich（Git库操作库）
            import common.package_manager as pkgmgr
            pkgmgr.check_dulwich()
        except Exception as e:
            # 导入失败，返回错误
            logger.error("Failed to install plugin, {}".format(e))
            return False, "无法导入dulwich，安装插件失败"
            
        # 导入正则表达式模块
        import re

        # 导入dulwich的porcelain模块（高级Git操作）
        from dulwich import porcelain

        logger.info("clone git repo: {}".format(repo))

        # 尝试匹配Git仓库URL格式
        # 支持：https://github.com/user/repo.git 或 git@github.com:user/repo.git
        match = re.match(r"^(https?:\/\/|git@)([^\/:]+)[\/:]([^\/:]+)\/(.+).git$", repo)

        # URL格式不匹配
        if not match:
            try:
                # 尝试从source.json中查找
                with open("./plugins/source.json", "r", encoding="utf-8") as f:
                    source = json.load(f)
                    
                # 检查别名是否存在
                if repo in source["repo"]:
                    # 使用source中的URL
                    repo = source["repo"][repo]["url"]
                    match = re.match(r"^(https?:\/\/|git@)([^\/:]+)[\/:]([^\/:]+)\/(.+).git$", repo)
                    if not match:
                        return False, "安装插件失败，source中的仓库地址不合法"
                else:
                    return False, "安装插件失败，仓库地址不合法"
                    
            except Exception as e:
                logger.error("Failed to install plugin, {}".format(e))
                return False, "安装插件失败，请检查仓库地址是否正确"
                
        # 构造插件安装目录
        # match.group(4) 是仓库名（不含.git）
        dirname = os.path.join("./plugins", match.group(4))
        
        try:
            # 克隆仓库到本地
            repo = porcelain.clone(repo, dirname, checkout=True)
            
            # 检查是否有requirements.txt
            if os.path.exists(os.path.join(dirname, "requirements.txt")):
                logger.info("detect requirements.txt，installing...")
                # 安装Python依赖
                pkgmgr.install_requirements(os.path.join(dirname, "requirements.txt"))
                
            return True, "安装插件成功，请使用 #scanp 命令扫描插件或重启程序，开启前请检查插件是否需要配置"
            
        except Exception as e:
            logger.error("Failed to install plugin, {}".format(e))
            return False, "安装插件失败，" + str(e)

    def update_plugin(self, name: str):
        """
        更新插件（从Git仓库拉取最新代码）
        
        Args:
            name: 插件名称
            
        Returns:
            tuple: (是否成功, 消息)
        """
        try:
            # 检查dulwich是否可用
            import common.package_manager as pkgmgr
            pkgmgr.check_dulwich()
        except Exception as e:
            logger.error("Failed to install plugin, {}".format(e))
            return False, "无法导入dulwich，更新插件失败"
            
        from dulwich import porcelain

        # 统一转为大写
        name = name.upper()
        
        # 插件不存在
        if name not in self.plugins:
            return False, "插件不存在"
            
        # 预置插件列表（不允许更新）
        if name in [
            "HELLO",
            "GODCMD",
            "ROLE",
            "TOOL",
            "BDUNIT",
            "BANWORDS",
            "FINISH",
            "DUNGEON",
        ]:
            return False, "预置插件无法更新，请更新主程序仓库"
            
        # 获取插件目录
        dirname = self.plugins[name].path
        
        try:
            # 从origin拉取最新代码
            porcelain.pull(dirname, "origin")
            
            # 检查并安装依赖
            if os.path.exists(os.path.join(dirname, "requirements.txt")):
                logger.info("detect requirements.txt，installing...")
                pkgmgr.install_requirements(os.path.join(dirname, "requirements.txt"))
                
            return True, "更新插件成功，请重新运行程序"
            
        except Exception as e:
            logger.error("Failed to update plugin, {}".format(e))
            return False, "更新插件失败，" + str(e)

    def uninstall_plugin(self, name: str):
        """
        卸载插件
        
        流程：
        1. 禁用插件
        2. 删除插件目录
        3. 清理注册信息和配置
        
        Args:
            name: 插件名称
            
        Returns:
            tuple: (是否成功, 消息)
        """
        # 统一转为大写
        name = name.upper()
        
        # 插件不存在
        if name not in self.plugins:
            return False, "插件不存在"
            
        # 如果插件已实例化，先禁用
        if name in self.instances:
            self.disable_plugin(name)
            
        # 获取插件目录
        dirname = self.plugins[name].path
        
        try:
            # 导入 shutil 模块（用于删除目录）
            import shutil
            
            # 删除插件目录
            shutil.rmtree(dirname)
            
            # 获取原始名称
            rawname = self.plugins[name].name
            
            # 从事件监听列表中移除
            for event in self.listening_plugins:
                if name in self.listening_plugins[event]:
                    self.listening_plugins[event].remove(name)
                    
            # 删除插件注册信息
            del self.plugins[name]
            del self.pconf["plugins"][rawname]
            
            # 标记路径为None（表示已卸载）
            self.loaded[dirname] = None
            
            # 保存配置
            self.save_config()
            
            return True, "卸载插件成功"
            
        except Exception as e:
            logger.error("Failed to uninstall plugin, {}".format(e))
            return False, "卸载插件失败，请手动删除文件夹完成卸载，" + str(e)
