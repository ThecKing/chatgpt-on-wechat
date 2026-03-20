"""
Unified chat message class for different channel implementations.
为不同频道实现（如微信、飞书、QQ等）提供统一的聊天消息封装基类。

填好必填项(群聊6个，非群聊8个)，即可接入ChatChannel，并支持插件，参考TerminalChannel
只要各个频道的实现将这些必填字段填好，就能无缝接入基类 ChatChannel，并且自动获得插件机制的支持。

ChatMessage
msg_id: 消息id (必填)
create_time: 消息创建时间

ctype: 消息类型 : ContextType (必填)
content: 消息内容, 如果是声音/图片，这里是文件路径 (必填)

from_user_id: 发送者id (必填)
from_user_nickname: 发送者昵称
to_user_id: 接收者id (必填)
to_user_nickname: 接收者昵称

other_user_id: 对方的id，如果你是发送者，那这个就是接收者id，如果你是接收者，那这个就是发送者id，如果是群消息，那这一直是群id (必填)
other_user_nickname: 同上

is_group: 是否是群消息 (群聊必填)
is_at: 是否被at

- (群消息时，一般会存在实际发送者，是群内某个成员的id和昵称，下列项仅在群消息时存在)
actual_user_id: 实际发送者id (群聊必填)
actual_user_nickname：实际发送者昵称
self_display_name: 自身的展示名，设置群昵称时，该字段表示群昵称

_prepare_fn: 准备函数，用于准备消息的内容，比如下载图片等,
_prepared: 是否已经调用过准备函数
_rawmsg: 原始消息对象

"""


class ChatMessage(object):
    # 消息的全局唯一标识 ID
    msg_id = None
    # 消息产生的时间戳或时间对象
    create_time = None

    # 封装的消息上下文类型（如文字、图片、语音，枚举来自于 ContextType）
    ctype = None
    # 消息的具体内容。如果是文本就是字符串；如果是图片/语音，通常保存的是本地临时文件路径
    content = None

    # 这条消息是从哪个用户 ID 发来的
    from_user_id = None
    # 发送这条消息的用户昵称
    from_user_nickname = None
    # 这条消息要发给哪个用户 ID（通常就是机器人的 ID）
    to_user_id = None
    # 接收消息的用户昵称（机器人的名字）
    to_user_nickname = None
    # 聊天对端的 ID（私聊中指对方用户 ID，群聊中始终指代所在的群组 ID）
    other_user_id = None  # TODO 看下这两个other什么时候用到了
    # 聊天对端的昵称名称（也就是群名或者对方用户名）
    other_user_nickname = None
    # 标识这条消息是否是机器人自己发给自己的（防止自言自语产生死循环响应）
    my_msg = False
    # 机器人在当前平台/群组中对外展示的名字
    self_display_name = None

    # 布尔值：当前消息是不是来自一个群聊
    is_group = False  # TODO 是否可以把这个机器人加到我们自己群里？
    # 布尔值：如果是在群聊中，机器人有没有被明确地 @
    is_at = False
    # 当 is_group 为 True 时有效，代表具体是群里哪个成员的真实 ID 说的这句话
    actual_user_id = None
    # 当 is_group 为 True 时有效，代表该发言群成员的真实群昵称
    actual_user_nickname = None
    # 记录该条消息里究竟 @ 了哪些人的列表集合
    at_list = None

    # 一个回调函数钩子，允许延后处理较重的内容（例如消息虽然收到了但包含网络网络图片附件，可以用此函数延后发起下载）
    _prepare_fn = None
    # 布尔状态位：标记这个准备函数是不是已经被触发调用过了，防止重复执行下载等耗资源的操作
    _prepared = False
    # 存储底层平台（如 wechatpy 或 dingtalk_stream）抛过来的极为原始且未经格式集成的原生 JSON/字典对象
    _rawmsg = None

    def __init__(self, _rawmsg):
        # 类的构造函数，实例化时强制要求传入最原汁原味的平台底层消息对象
        self._rawmsg = _rawmsg

    def prepare(self):
        # 触发预处理机制的方法，通常在处理该消息前（如在 chat_channel.py 真正开始跑前）被调起
        # 检查有没有绑定预处理函数，且是不是还没执行过
        if self._prepare_fn and not self._prepared:
            # 立刻将状态标为已预备，防止并发情况下其它线程重复触发
            self._prepared = True
            # 真正开始执行该函数操作（例如启动耗时的图片本体或语音媒体块的拉取下载到本地服务器）
            self._prepare_fn()

    def __str__(self):
        # Python 魔术方法覆写，使得在使用 print(msg) 或 logging 时，
        # 能直接把该消息所有的属性打平输出为可读字符串，这对快速排查平台数据 Bug 极大有帮助
        return "ChatMessage: id={}, create_time={}, ctype={}, content={}, from_user_id={}, from_user_nickname={}, to_user_id={}, to_user_nickname={}, other_user_id={}, other_user_nickname={}, is_group={}, is_at={}, actual_user_id={}, actual_user_nickname={}, at_list={}".format(
            self.msg_id,
            self.create_time,
            self.ctype,
            self.content,
            self.from_user_id,
            self.from_user_nickname,
            self.to_user_id,
            self.to_user_nickname,
            self.other_user_id,
            self.other_user_nickname,
            self.is_group,
            self.is_at,
            self.actual_user_id,
            self.actual_user_nickname,
            self.at_list
        )
