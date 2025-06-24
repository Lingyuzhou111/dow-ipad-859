"""
WechatAPI - 微信API客户端模块

这个模块提供了与微信API服务器通信的客户端类和相关工具。
"""

# 导入错误类
from .errors import *

# 导入主要的客户端类
from .Client import WechatAPIClient

# 导入基础类和工具
from .Client.base import WechatAPIClientBase, Proxy, Section

# 版本信息
__version__ = "1.0.0"
__author__ = "WX859 Team"

# 导出的公共接口
__all__ = [
    'WechatAPIClient',
    'WechatAPIClientBase', 
    'Proxy',
    'Section',
    # 错误类会通过 from .errors import * 自动导出
]
