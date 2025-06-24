import aiohttp

from .base import *
from .protect import protector
from ..errors import *
# from loguru import logger

class UserMixin(WechatAPIClientBase):
    async def get_profile(self, wxid: str = None) -> dict:
        """获取用户信息。

        Args:
            wxid (str, optional): 用户wxid. Defaults to None.

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
            json_param = {"wxid": wxid}
            # response = await session.post(f'http://{self.ip}:{self.port}/api/Login/GetCacheInfo', data=json_param)
            response = await session.post(f'http://{self.ip}:{self.port}/api/User/GetContractProfile', data=json_param)
            json_resp = await response.json()
            
            if json_resp.get("Success"):
                # logger.info("账号信息:{}",json_resp.get("Data"))
                return json_resp.get("Data")
            else:
                self.error_handler(json_resp)

    async def get_my_qrcode(self, style: int = 0) -> str:
        """获取个人二维码。

        Args:
            style (int, optional): 二维码样式. Defaults to 0.

        Returns:
            str: 图片的base64编码字符串

        Raises:
            UserLoggedOut: 未登录时调用
            BanProtection: 风控保护: 新设备登录后4小时内请挂机
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")
        elif protector.check(14400) and not self.ignore_protect:
            raise BanProtection("风控保护: 新设备登录后4小时内请挂机")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "Style": style}
            response = await session.post(f'http://{self.ip}:{self.port}/api/User/GetQRCode', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data").get("qrcode").get("buffer")
            else:
                self.error_handler(json_resp)

    async def is_logged_in(self, wxid: str = None) -> bool:
        """检查是否登录。

        Args:
            wxid (str, optional): 用户wxid. Defaults to None.

        Returns:
            bool: 已登录返回True，未登录返回False
        """
        if not wxid:
            wxid = self.wxid
        try:
            await self.get_profile(wxid)
            return True
        except:
            return False
        
    async def get_label_list(self, wxid: str = None) -> dict:
        """获取标签列表。

        Args:
            wxid (str, optional): 用户wxid. Defaults to None.

        Returns:
            dict: 标签列表字典

        Raises:
            UserLoggedOut: 未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid and not wxid:
            raise UserLoggedOut("请先登录")

        if not wxid:
            wxid = self.wxid

        async with aiohttp.ClientSession() as session:
            json_param = {"wxid": wxid}
            # response = await session.post(f'http://{self.ip}:{self.port}/api/Login/GetCacheInfo', data=json_param)
            response = await session.post(f'http://{self.ip}:{self.port}/api/Label/GetList', data=json_param)
            json_resp = await response.json()
            
            if json_resp.get("Success"):
                # logger.info("账号信息:{}",json_resp.get("Data"))
                return json_resp.get("Data").get("labelPairList")
            else:
                self.error_handler(json_resp)