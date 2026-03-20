# encoding:utf-8
# 声明使用 utf-8 编码

import os # 导入操作系统接口模块
import signal # 导入信号处理模块，用于处理进程退出等信号
import sys # 导入系统特定的参数和函数模块
import time # 导入时间模块，用于延迟或计时

from channel import channel_factory # 从 channel 包导入通道工厂模块，用于创建具体的通道实例
from common import const # 从 common 包导入常量定义模块
from common.log import logger # 导入日志记录器，用于打印和记录系统日志
from config import load_config, conf # 从 config 模块导入配置加载函数和获取当前配置的函数
from plugins import * # 导入所有的插件
import threading # 导入多线程模块，用于支持并发运行多个通道

_channel_mgr = None # 全局变量，用于存储全局的通道管理器实例


def get_channel_manager():
    # 获取全局的通道管理器实例
    return _channel_mgr


def _parse_channel_type(raw) -> list:
    """
    Parse channel_type config value into a list of channel names.
    解析 config 中的 channel_type，确保无论输入是什么形式都返回一个列表格式的 channel_type
    Supports (支持的格式):
      - single string (单字符串): "feishu"
      - comma-separated string (逗号分隔字符串): "feishu, dingtalk"
      - list (列表): ["feishu", "dingtalk"]
      【解析chennels，确保格式一致】
    """
    if isinstance(raw, list):
        # 如果已经是列表，直接遍历去除每个元素的空白字符并过滤空值，然后返回
        return [ch.strip() for ch in raw if ch.strip()]
    if isinstance(raw, str):
        # 如果是字符串，则按逗号切割成列表，去除空白字符并过滤空值后返回
        return [ch.strip() for ch in raw.split(",") if ch.strip()]
    return [] # 如果都不是，则返回空列表


class ChannelManager:
    """
    Manage the lifecycle of multiple channels running concurrently.
    管理多个通道并行运行的生命周期。
    Each channel.startup() runs in its own daemon thread.
    每个 channel.startup() 方法都会在自己的一个守护线程中运行。
    The web channel is started as default console unless explicitly disabled.
    如果没有被明确禁用，Web 通道通常会作为默认的控制台被启动。
    """

    def __init__(self):
        # 初始化字典，存放 通道名称 映射到 通道实例
        self._channels = {}        # channel_name -> channel instance
        # 初始化字典，存放 通道名称 映射到 具体运行该通道的线程
        self._threads = {}         # channel_name -> thread
        # 主频道，非web情况下的首选通道，用于后向兼容
        self._primary_channel = None
        # 初始化线程锁，用于操作 self._channels 等共享资源时保证线程安全
        self._lock = threading.Lock()
        # 云端模式的标识，当云端客户端处于活动状态时会被设为 True
        self.cloud_mode = False    # set to True when cloud client is active

    @property
    def channel(self):
        """Return the primary (first non-web) channel for backward compatibility."""
        # 返回主通道实例（用于老版本兼容）
        return self._primary_channel

    def get_channel(self, channel_name: str):
        # 根据通道名称获取对应的通道实例
        return self._channels.get(channel_name)

    def start(self, channel_names: list, first_start: bool = False):
        """
        Create and start one or more channels in sub-threads.
        在子线程中创建并启动一个或多个通道。
        If first_start is True, plugins and linkai client will also be initialized.
        如果 first_start 为 True，还会进行插件系统的加载以及 LinkAI 客户端的初始化。
        """
        with self._lock: # 使用锁定，保证多线程环境下操作实例变量安全
            channels = [] # 本次准备启动的通道列表

            # 遍历传入的需要启动的通道名称列表
            for name in channel_names:
                # 利用工程模式，传入通道名，生成对应的通道实例对象
                ch = channel_factory.create_channel(name)
                ch.cloud_mode = self.cloud_mode # 继承当前的云端模式设置
                self._channels[name] = ch # 存入实例的 _channels 字典管理
                channels.append((name, ch)) # 将名字和实例组成元组存入局部列表
                
                # 如果主通道还没被设置，并且当前处理的不是 web 控制台通道
                if self._primary_channel is None and name != "web":
                    self._primary_channel = ch # 将主通道设为该通道

            # 如果还是没有主通道且本次有需要启动的通道列表，那就选列表第一个作为主通道（即便它是 web 也可以）
            if self._primary_channel is None and channels:
                self._primary_channel = channels[0][1]

            if first_start: # 如果是应用首次启动
                # 加载所有的插件
                PluginManager().load_plugins()

                # 如果配置中使用了 LinkAI
                if conf().get("use_linkai"):
                    try:
                        from common import cloud_client # 延迟导入云端客户端
                        # 开一个新线程启动云端客户端
                        threading.Thread(
                            target=cloud_client.start,
                            args=(self._primary_channel, self), # 传入主通道和通道管理器实例自身
                            daemon=True,
                        ).start()
                    except Exception:
                        pass # 异常则忽略

            # start web console first so its logs print cleanly,
            # 先启动 web 控制台，以便它的日志一开始干净地输出，
            # then start remaining channels after a brief pause.
            # 接着等待一会再启动剩下的信道以错峰输出日志。
            web_entry = None
            other_entries = []
            
            # 过滤分类 web 通道 和 其他通道
            for entry in channels:
                if entry[0] == "web":
                    web_entry = entry
                else:
                    other_entries.append(entry)

            # 让 web 通道排在列表第一位，其它通道跟在后面
            ordered = ([web_entry] if web_entry else []) + other_entries
            
            # 使用列表存放频道，在循环里为每个 channel 开一个独立守护线程运行它的 startup()
            for i, (name, ch) in enumerate(ordered):
                # 针对非 web 通道，错峰启动，防止同时打印日志导致日志混乱
                if i > 0 and name != "web":
                    time.sleep(0.1)
                
                # 将具体信道的启动任务放入一个守护线程（如果主线程结束，守护线程会自动结束）
                t = threading.Thread(target=self._run_channel, args=(name, ch), daemon=True)
                self._threads[name] = t # 登记该名称对应的线程对象
                t.start() # 开始执行启动代码
                logger.debug(f"[ChannelManager] Channel '{name}' started in sub-thread")

    def _run_channel(self, name: str, channel):
        # 实际被线程调用的目标函数，为了捕获通道启动时的崩溃
        try:
            channel.startup() # 启动信道监听或连接机制
        except Exception as e:
            logger.error(f"[ChannelManager] Channel '{name}' startup error: {e}")
            logger.exception(e) # 记录完整的堆栈异常

    def stop(self, channel_name: str = None):
        """
        Stop channel(s). If channel_name is given, stop only that channel;
        otherwise stop all channels.
        停止一个或者全部通道。如果提供了具体的 channel_name 就只停一个。
        """
        # Pop under lock, then stop outside lock to avoid deadlock
        # 在锁的范围内把需要停止的 channel 先“弹出”并收集，之后出锁再执行停掉逻辑，为了防止互相等待造成死锁
        with self._lock:
            # 确定要停止的名字列表：指定的或者全部
            names = [channel_name] if channel_name else list(self._channels.keys())
            to_stop = [] # 等待处理停止的列表
            for name in names:
                ch = self._channels.pop(name, None) # 删除并提取 channel 配置
                th = self._threads.pop(name, None)  # 删除并提取 thread 对象
                to_stop.append((name, ch, th))
            # 如果主通道刚好被停止掉了，就把主通道重置为 None
            if channel_name and self._primary_channel is self._channels.get(channel_name):
                self._primary_channel = None

        # 遍历需要被关闭的列表，此时不持有系统锁
        for name, ch, th in to_stop:
            if ch is None:
                logger.warning(f"[ChannelManager] Channel '{name}' not found in managed channels")
                # 对象虽然没了，但如果线程还在跑，也得设法打断它
                if th and th.is_alive():
                    self._interrupt_thread(th, name)
                continue
                
            logger.info(f"[ChannelManager] Stopping channel '{name}'...")
            graceful = False # 标识是否能优雅关闭
            if hasattr(ch, 'stop'): # 判断该通道有无实现 stop 方法
                try:
                    ch.stop() # 尝试正常关闭
                    graceful = True
                except Exception as e:
                    logger.warning(f"[ChannelManager] Error during channel '{name}' stop: {e}")
            
            # 如果对应的线程还活着（还在执行）
            if th and th.is_alive():
                th.join(timeout=5) # 尝试等该线程自己结束，限时5秒钟
                if th.is_alive():  # 如果5秒钟之后还是活着
                    if graceful: # 如果调用了 stop()，那就让守护进程自己顺其自然结束  # TODO 这只是随着主线程结束啊，而不是随着channel的进程结束啊？
                        logger.info(f"[ChannelManager] Channel '{name}' thread still alive after stop(), "
                                    "leaving daemon thread to finish on its own")
                    else: # 反之说明没提供 stop()，强制给线程里抛出中断异常进行强制停止
                        logger.warning(f"[ChannelManager] Channel '{name}' thread did not exit in 5s, forcing interrupt")
                        self._interrupt_thread(th, name)

    @staticmethod
    def _interrupt_thread(th: threading.Thread, name: str):
        """Raise SystemExit in target thread to break blocking loops like start_forever."""
        # 静态方法：向目标线程里面抛出 SystemExit 异常以强制终止卡死的无限循环，比如一些不断接收消息的底层调用
        import ctypes
        try:
            tid = th.ident # 拿到目标线程 ID
            if tid is None:
                return # 还没启动或者已经退出
                
            # 利用 pythonapi 抛出 SystemExit
            res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(tid), ctypes.py_object(SystemExit)
            )
            if res == 1:
                logger.info(f"[ChannelManager] Interrupted thread for channel '{name}'")
            elif res > 1:
                # 大于1的情况，代表抛掷出问题了，需将上面抛掷的异常清空取消
                ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), None)
                logger.warning(f"[ChannelManager] Failed to interrupt thread for channel '{name}'")
        except Exception as e:
            logger.warning(f"[ChannelManager] Thread interrupt error for '{name}': {e}")

    def restart(self, new_channel_name: str):
        """
        Restart a single channel with a new channel type.
        用新的通道名类型重新启动一个通道。
        Can be called from any thread (e.g. linkai config callback).
        可以被任何线程调用（如云端远程下发的配置更新指令时调用）。
        """
        logger.info(f"[ChannelManager] Restarting channel to '{new_channel_name}'...")
        self.stop(new_channel_name) # 停止现有通道
        _clear_singleton_cache(new_channel_name) # 清理原本对某个类单例的缓存，避免保留死掉的对象
        time.sleep(1) # 睡眠1秒，确保停干净资源
        self.start([new_channel_name], first_start=False) # 重新启动
        logger.info(f"[ChannelManager] Channel restarted to '{new_channel_name}' successfully")

    def add_channel(self, channel_name: str):
        """
        Dynamically add and start a new channel.
        动态增加和启动一个新频道。
        If the channel is already running, restart it instead.
        如果正在运行就转交为重启。
        """
        with self._lock:
            # 锁定判断它是否已经存在
            if channel_name in self._channels:
                logger.info(f"[ChannelManager] Channel '{channel_name}' already exists, restarting")
        
        # 重接启动
        if self._channels.get(channel_name):
            self.restart(channel_name)
            return
            
        logger.info(f"[ChannelManager] Adding channel '{channel_name}'...")
        _clear_singleton_cache(channel_name) # 清除缓存准备新开
        self.start([channel_name], first_start=False) # 执行非首次启动逻辑（不再执行插件加载了）
        logger.info(f"[ChannelManager] Channel '{channel_name}' added successfully")

    def remove_channel(self, channel_name: str):
        """
        Dynamically stop and remove a running channel.
        动态地停止并移除一个运行中的通道
        """
        with self._lock:
            if channel_name not in self._channels:
                logger.warning(f"[ChannelManager] Channel '{channel_name}' not found, nothing to remove")
                return # 没找到直接返回不管
                
        logger.info(f"[ChannelManager] Removing channel '{channel_name}'...")
        self.stop(channel_name) # 用stop销毁它
        logger.info(f"[ChannelManager] Channel '{channel_name}' removed successfully")


def _clear_singleton_cache(channel_name: str):
    """
    Clear the singleton cache for the channel class so that
    a new instance can be created with updated config.
    清理某个通道类实现的“单例”属性缓存，从而接下来可以创建一个带着全新配置的实例对象。
    """
    # 这个字典保存通道名称和该通道实现类其包路径的一一映射关系
    cls_map = {
        "web": "channel.web.web_channel.WebChannel",
        "wechatmp": "channel.wechatmp.wechatmp_channel.WechatMPChannel",
        "wechatmp_service": "channel.wechatmp.wechatmp_channel.WechatMPChannel",
        "wechatcom_app": "channel.wechatcom.wechatcomapp_channel.WechatComAppChannel",
        const.FEISHU: "channel.feishu.feishu_channel.FeiShuChanel",
        const.DINGTALK: "channel.dingtalk.dingtalk_channel.DingTalkChanel",
        const.WECOM_BOT: "channel.wecom_bot.wecom_bot_channel.WecomBotChannel",
        const.QQ: "channel.qq.qq_channel.QQChannel",
    }
    module_path = cls_map.get(channel_name)
    if not module_path:
        return # 没找到对应类就退出
        
    try:
        # 切割获取这个模块名称（比如 channel.web.web_channel）和类名称 （比如 WebChannel）
        parts = module_path.rsplit(".", 1)
        module_name, class_name = parts[0], parts[1]
        import importlib
        module = importlib.import_module(module_name) # 反射导入 Python 模块
        wrapper = getattr(module, class_name, None) # 获取到这个被单例装饰过的类对象
        
        # 判断如果它是被装饰器包裹且持有闭包变量的（因它被 @singleton 装饰存了字典），那就清空闭包持有的单例
        if wrapper and hasattr(wrapper, '__closure__') and wrapper.__closure__:
            for cell in wrapper.__closure__: # 迭代包围此函数的闭包变量信息
                try:
                    cell_contents = cell.cell_contents
                    # 把原本存的单例字典清理干净，以便之后再次被调用生成新对象
                    if isinstance(cell_contents, dict):
                        cell_contents.clear()
                        logger.debug(f"[ChannelManager] Cleared singleton cache for {class_name}")
                        break
                except ValueError:
                    pass
    except Exception as e:
        logger.warning(f"[ChannelManager] Failed to clear singleton cache: {e}")


def sigterm_handler_wrap(_signo):
    # 用来拦截程序的停止信号，做一些收尾工作，比如保存用户进程等
    old_handler = signal.getsignal(_signo)

    def func(_signo, _stack_frame):
        logger.info("signal {} received, exiting...".format(_signo))
        conf().save_user_datas() # 把配置文件里的用户动态存储数据落地保存，防止丢失
        if callable(old_handler):  # 检查原来有没有处理该信号的旧函数
            return old_handler(_signo, _stack_frame) # 执行原本的
        sys.exit(0) # 退出应用进程

    # 把信号跟这个包装后的内部回调绑定
    signal.signal(_signo, func)


def run():
    global _channel_mgr
    try:
        # load config
        # 开始尝试加载所有的配置文件进入内存
        load_config()
        
        # 绑定截获 ctrl + c 命令触发退出的清理操作
        sigterm_handler_wrap(signal.SIGINT)
        
        # 绑定截获 kill 指令进程时触发的清理操作
        sigterm_handler_wrap(signal.SIGTERM)

        # Parse channel_type into a list
        # 从加载完毕的配置中，获取用户的 channel_type 选项。默认回落就是 web 端
        raw_channel = conf().get("channel_type", "web")

        # 检查带过来的系统环境命令行参数。如果带了 --cmd 表示只在后台用终端模式进行演示
        if "--cmd" in sys.argv:
            channel_names = ["terminal"]
        else:
            # 正常执行解析配置文件里的参数进行转列表操作
            channel_names = _parse_channel_type(raw_channel)
            if not channel_names:
                channel_names = ["web"]

        # Auto-start web console unless explicitly disabled
        # 如果不是主动去关闭了 web 功能，且目前通道配置里没有包含 web ，则帮用户添加 web 测试台
        web_console_enabled = conf().get("web_console", True)
        if web_console_enabled and "web" not in channel_names:
            channel_names.append("web")

        logger.info(f"[App] Starting channels: {channel_names}")

        # 实例化通道管理器
        _channel_mgr = ChannelManager()
        # 告诉其启动这些对应的接入服务平台通道
        _channel_mgr.start(channel_names, first_start=True)

        # 挂起主线程，不然一旦函数 return 进程就没阻碍销毁退出了
        while True:
            time.sleep(1)
            
    except Exception as e:
        # 万一崩溃打印日志
        logger.error("App startup failed!")
        logger.exception(e)


# 如果这份脚本作为主程序被直接用 Python 启动执行，则调用 run()
if __name__ == "__main__":
    run()
