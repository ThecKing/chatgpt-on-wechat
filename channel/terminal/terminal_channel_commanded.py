import sys # 导入 sys 模块，用于处理系统级输入输出（如 sys.stdout, sys.exit）

from bridge.context import * # 从 bridge.context 导入所有类和变量（如 Context, ContextType）
from bridge.reply import Reply, ReplyType # 从 bridge.reply 导入返回对象类和返回类型枚举
from channel.chat_channel import ChatChannel, check_prefix # 从 chat_channel 导入聊天频道基类和前缀检查函数
from channel.chat_message import ChatMessage # 导入标准聊天消息对象的基类
from common.log import logger # 导入日志记录模块
from config import conf # 导入配置管理模块，获取系统当前配置


class TerminalMessage(ChatMessage):
    # TerminalMessage 类继承自 ChatMessage，用于终端通道下消息的封装
    def __init__(
        self,
        msg_id, # 消息ID
        content, # 消息内容
        ctype=ContextType.TEXT, # 消息类型，默认为文本
        from_user_id="User", # 发送者ID，在终端里默认叫做 "User"
        to_user_id="Chatgpt", # 接收者ID，在终端里默认叫做 "Chatgpt"
        other_user_id="Chatgpt", # 会话组的对端ID，同样给一个默认值
    ):
        # 将传入的参数绑定到当前对象的属性上
        self.msg_id = msg_id # 绑定消息ID
        self.ctype = ctype # 绑定消息类型
        self.content = content # 绑定消息内容文本
        self.from_user_id = from_user_id # 绑定发送者ID
        self.to_user_id = to_user_id # 绑定接收者ID
        self.other_user_id = other_user_id # 绑定会话对端ID


class TerminalChannel(ChatChannel):
    # TerminalChannel 继承自 ChatChannel（也就是包含队列和并发线程池的核心频道基类）
    # 定义终端不支持发送语音类型的回复
    NOT_SUPPORT_REPLYTYPE = [ReplyType.VOICE]

    def send(self, reply: Reply, context: Context):
        # 覆写基类的发送方法，用于真正在终端里打印大模型回给用户的数据
        print("\nBot:") # 先换行打印 "Bot:" 提示接下来是机器人说的话
        if reply.type == ReplyType.IMAGE: # 如果回答的类型是图片（比如在本地生成的图片对象）
            from PIL import Image # 延迟导入 Python 图像处理库 PIL

            image_storage = reply.content # 获取内存中的图片二进制数据 (如 BytesIO)
            image_storage.seek(0) # 将二进制流的读取指针移回到文件开头
            img = Image.open(image_storage) # 使用 PIL 打开这串二进制数据流变成图片对象
            print("<IMAGE>") # 在终端打印一个提示符表示这是一张图片
            img.show() # 调用系统默认的图片浏览器弹出显示这张图片
        elif reply.type == ReplyType.IMAGE_URL:  # 如果回答的类型是从网络下载图片的 URL 链接
            import io # 导入 IO 基础模块用于处理内存字节流

            import requests # 导入 requests 库发起 HTTP 请求
            from PIL import Image # 同样导入 PIL

            img_url = reply.content # 从回复内容中提取出真实的图片 URL
            pic_res = requests.get(img_url, stream=True) # 发起 GET 请求下载这张图，开启 stream 流模式防止占用过多内存
            image_storage = io.BytesIO() # 创建一个存在内存中的二进制流对象
            for block in pic_res.iter_content(1024): # 每次以 1024 字节（1KB）为单位分块读取网络上的图片数据
                image_storage.write(block) # 将读取的字节块写入到内存流中
            image_storage.seek(0) # 写入完成后将读取指针搬回起点
            img = Image.open(image_storage) # 用 PIL 打开该内存对象转换为图片
            print(img_url) # 在终端打印出这张图的原始 URL 供用户复制查看
            img.show() # 调用系统图片查看软件弹出这幅图
        else:
            # 如果不是图片，那就是普通文本或者别的（如报错），直接将内容打印到控制台
            print(reply.content)
        print("\nUser:", end="") # 回复完毕后，紧接着另起一行打印 "User:"，且末尾不换行，提示用户继续输入
        sys.stdout.flush() # 强制刷新标准输出缓冲区，确保上面的 print 立即显示在屏幕上
        return # 发送完毕退出函数

    def startup(self):
        # 这个方法会在项目刚启动时，被 app.py 的 ChannelManager 的守护线程所调用
        context = Context() # 生成一个空的上下文对象 (其实这里只做初始化，后面会被复写)
        logger.setLevel("WARN") # 终端模式下不需要打印太多 DEBUG 废话影响沟通，强制改成 WARN 级别日志
        print("\nPlease input your question:\nUser:", end="") # 打印引导用户说话的初始提示
        sys.stdout.flush() # 立刻刷新缓冲区，让光标停在这里
        msg_id = 0 # 维护一个递增的消息 ID 计数器，从 0 开始
        while True: # 进入死循环，使终端程序常驻、持续监听用户的键盘输入
            try:
                # 尝试通过自建的 get_input 获取用户命令行输入的一行文本
                prompt = self.get_input()
            except KeyboardInterrupt: # 如果捕获到用户在终端里按下了 Ctrl+C 快捷键
                print("\nExiting...") # 打印退出提示
                sys.exit() # 彻底结束当前 Python 控制台进程
            msg_id += 1 # 每次用户回车，消息 ID 自增 1
            trigger_prefixs = conf().get("single_chat_prefix", [""]) # 从配置文件读取私聊的唤醒词前缀（终端属于私聊模拟）
            # 判断检查用户刚才敲的字里有没有带触发词
            if check_prefix(prompt, trigger_prefixs) is None:
                # 终端是个本地系统，就算没带触发词也理应回答，所以如果用户没加，直接利用配置切片的第一个前缀强行给他补上
                prompt = trigger_prefixs[0] + prompt  # 给没触发的消息加上触发前缀

            # 把构建好的终端消息放入内部的 _compose_context 去清洗组装成 Context 引擎流通对象
            context = self._compose_context(ContextType.TEXT, prompt, msg=TerminalMessage(msg_id, prompt))
            context["isgroup"] = False # 强制将终端会话标为私聊
            if context:
                self.produce(context) # 使用 Channel 基类的生产者消费者模型，将这句聊天扔进后端排队池，去触发大模型
            else:
                # 如果从 _compose_context 清理后返回了 None，说明报错了或者拦截了
                raise Exception("context is None")

    def get_input(self):
        """
        Multi-line input function
        多行/单行输入获取函数
        """
        sys.stdout.flush() # 再次确保标准输出干净
        line = input() # 阻塞地捕获用户在键盘上敲的内容直到按回车
        return line # 把读取到的一整行字符串返回
