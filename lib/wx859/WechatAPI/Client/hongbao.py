import aiohttp

from .base import *
from ..errors import *


class HongBaoMixin(WechatAPIClientBase):
    async def get_hongbao_detail(self, xml: str, encrypt_key: str, encrypt_userinfo: str) -> dict:
        """获取红包详情

        Args:
            xml: 红包 XML 数据
            encrypt_key: 加密密钥
            encrypt_userinfo: 加密的用户信息

        Returns:
            dict: 红包详情数据
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "Xml": xml, "EncryptKey": encrypt_key, "EncryptUserinfo": encrypt_userinfo,"InWay": "1"}
            response = await session.post(f'http://{self.ip}:{self.port}/api/TenPay/Receivewxhb', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data")
            else:
                self.error_handler(json_resp)
