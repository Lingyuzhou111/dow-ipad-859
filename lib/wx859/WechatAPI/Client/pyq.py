import aiohttp

from .base import *
from .protect import protector
from ..errors import *
# from loguru import logger

class PyqMixin(WechatAPIClientBase):
    async def get_pyq_list(self, wxid: str = None, max_id: int = 0) -> dict:
        """获取朋友圈首页列表。

        Args:
            wxid (str, optional): 用户wxid. Defaults to None.
            max_id (int, optional): 朋友圈ID，用于分页获取. Defaults to 0.

        Returns:
            dict: 用户信息字典

        Raises:
            UserLoggedOut: 未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid and not wxid:
            raise UserLoggedOut("请先登录")

        if not wxid:
            wxid = self.wxid

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": wxid,"Fristpagemd5": "", "Maxid": max_id}
            # response = await session.post(f'http://{self.ip}:{self.port}/api/Login/GetCacheInfo', data=json_param)
            response = await session.post(f'http://{self.ip}:{self.port}/api/FriendCircle/GetList', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                # logger.info("账号信息:{}",json_resp.get("Data"))
                return json_resp.get("Data")
            else:
                self.error_handler(json_resp)

    async def get_pyq_detail(self, wxid: str = None, Towxid: str = None, max_id: int = 0) -> dict:
        """获取特定人朋友圈。

        Args:
            wxid (str, optional): 用户wxid. Defaults to None.
            Towxid (str, optional): 目标用户wxid. Defaults to None.
            max_id (int, optional): 朋友圈ID，用于分页获取. Defaults to 0.

        Returns:
            dict: 特定人朋友圈字典

        Raises:
            UserLoggedOut: 未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid and not wxid:
            raise UserLoggedOut("请先登录")

        if not wxid:
            wxid = self.wxid

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": wxid, "Fristpagemd5": "", "Maxid": max_id, "Towxid": Towxid}
            # 使用正确的GetDetail接口获取特定用户的朋友圈
            response = await session.post(f'http://{self.ip}:{self.port}/api/FriendCircle/GetDetail', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                # logger.info("账号信息:{}",json_resp.get("Data"))
                return json_resp.get("Data")
            else:
                self.error_handler(json_resp)

    async def put_pyq_comment(self, wxid: str = None,id:str = None,Content:str = None,type:int =0,ReplyCommnetId:int=0) -> str:
        """朋友圈点赞/评论。

        Args:
            wxid (str, optional): 用户wxid. Defaults to None.
            id (str, optional): id. 朋友圈ID.
            Content (str, optional): Content. Defaults to None.
            type (int, optional): type. Defaults to 0.
            ReplyCommnetId (int, optional): ReplyCommnetId. Defaults to 0.

        Returns:
            dict: 成功信息

        Raises:
            UserLoggedOut: 未登录时调用
            BanProtection: 风控保护: 新设备登录后4小时内请挂机
            根据error_handler处理错误
        """
        if not self.wxid and not wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": wxid, "Id": id,"Content":Content,"Type":type,"ReplyCommnetId":ReplyCommnetId}
            response = await session.post(f'http://{self.ip}:{self.port}/api/FriendCircle/Comment', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data")
            else:
                self.error_handler(json_resp)

    async def pyq_sync(self, wxid: str = None) -> bool:
        """朋友圈同步。

        Args:
            wxid (str, optional): 用户wxid. Defaults to None.

        Returns:
            bool: 已登录返回True，未登录返回False
        """
        if not self.wxid and not wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": wxid, "Synckey": ""}
            response = await session.post(f'http://{self.ip}:{self.port}/api/FriendCircle/MmSnsSync', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data")
            else:
                self.error_handler(json_resp)