from dataclasses import dataclass

from WechatAPI.errors import *


@dataclass
class Proxy:
    """代理(无效果，别用！)

    Args:
        ip (str): 代理服务器IP地址
        port (int): 代理服务器端口
        username (str, optional): 代理认证用户名. 默认为空字符串
        password (str, optional): 代理认证密码. 默认为空字符串
    """
    ip: str
    port: int
    username: str = ""
    password: str = ""


@dataclass
class Section:
    """数据段配置类

    Args:
        data_len (int): 数据长度
        start_pos (int): 起始位置
    """
    data_len: int
    start_pos: int


class WechatAPIClientBase:
    """微信API客户端基类

    Args:
        ip (str): 服务器IP地址
        port (int): 服务器端口

    Attributes:
        wxid (str): 微信ID
        nickname (str): 昵称
        alias (str): 别名
        phone (str): 手机号
        ignore_protect (bool): 是否忽略保护机制
        api_path_prefix (str): API路径前缀，例如 /api 或 /VXAPI
    """
    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.api_path_prefix = "/api"  # 默认前缀

        self.wxid = ""
        self.nickname = ""
        self.alias = ""
        self.phone = ""

        self.ignore_protect = False

        # 调用所有 Mixin 的初始化方法
        super().__init__()

    def set_api_path_prefix(self, prefix: str):
        """设置API路径前缀"""
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        if prefix.endswith("/"):
            prefix = prefix[:-1]
        self.api_path_prefix = prefix

    def _get_full_url(self, endpoint: str) -> str:
        """根据api_path_prefix和endpoint构建完整的URL"""
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        return f"http://{self.ip}:{self.port}{self.api_path_prefix}{endpoint}"

    @staticmethod
    def error_handler(json_resp):
        """处理API响应中的错误码

        Args:
            json_resp (dict): API响应的JSON数据

        Raises:
            ValueError: 参数错误时抛出
            MarshallingError: 序列化错误时抛出
            UnmarshallingError: 反序列化错误时抛出
            MMTLSError: MMTLS初始化错误时抛出
            PacketError: 数据包长度错误时抛出
            UserLoggedOut: 用户已退出登录时抛出
            ParsePacketError: 解析数据包错误时抛出
            DatabaseError: 数据库错误时抛出
            Exception: 其他类型错误时抛出
        """
        code = json_resp.get("Code")
        if code == -1:  # 参数错误
            raise ValueError(json_resp.get("Message"))
        elif code == -2:  # 其他错误
            raise Exception(json_resp.get("Message"))
        elif code == -3:  # 序列化错误
            raise MarshallingError(json_resp.get("Message"))
        elif code == -4:  # 反序列化错误
            raise UnmarshallingError(json_resp.get("Message"))
        elif code == -5:  # MMTLS初始化错误
            raise MMTLSError(json_resp.get("Message"))
        elif code == -6:  # 收到的数据包长度错误
            raise PacketError(json_resp.get("Message"))
        elif code == -7:  # 已退出登录
            raise UserLoggedOut("Already logged out")
        elif code == -8:  # 链接过期
            raise Exception(json_resp.get("Message"))
        elif code == -9:  # 解析数据包错误
            raise ParsePacketError(json_resp.get("Message"))
        elif code == -10:  # 数据库错误
            raise DatabaseError(json_resp.get("Message"))
        elif code == -11:  # 登陆异常
            raise UserLoggedOut(json_resp.get("Message"))
        elif code == -12:  # 操作过于频繁
            raise Exception(json_resp.get("Message"))
        elif code == -13:  # 上传失败
            raise Exception(json_resp.get("Message"))
