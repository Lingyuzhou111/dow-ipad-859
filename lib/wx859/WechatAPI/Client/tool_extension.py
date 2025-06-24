import aiohttp
import base64
from .base import WechatAPIClientBase
from ..errors import UserLoggedOut
from loguru import logger

class ToolExtensionMixin(WechatAPIClientBase):
    async def get_msg_image(self, aeskey: str, cdnmidimgurl: str) -> bytes:
        """通过 CDN 下载高清图片（新版接口）。

        Args:
            aeskey (str): 图片的AES密钥
            cdnmidimgurl (str): 图片的CDN URL

        Returns:
            bytes: 图片的二进制数据

        Raises:
            UserLoggedOut: 未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "FileAesKey": aeskey, "FileNo": cdnmidimgurl}
            logger.info(f"调用CDN高清图片下载接口: {json_param}")
            response = await session.post(f'http://{self.ip}:{self.port}/api/Tools/CdnDownloadImage', json=json_param)
            try:
                json_resp = await response.json()
                if json_resp.get("Success"):
                    data = json_resp.get("Data")
                    if isinstance(data, str):
                        return base64.b64decode(data)
                    elif isinstance(data, dict):
                        if "buffer" in data:
                            return base64.b64decode(data["buffer"])
                        elif "Image" in data:
                            return base64.b64decode(data["Image"])
                        else:
                            logger.error(f"未知的图片数据格式: {type(data)} {data}")
                    else:
                        logger.error(f"未知的图片数据格式: {type(data)} {data}")
                else:
                    error_msg = json_resp.get("Message", "Unknown error")
                    logger.error(f"CDN下载高清图片失败: {error_msg}")
                    self.error_handler(json_resp)
            except Exception as e:
                logger.error(f"解析CDN图片下载响应失败: {e}")
            return b""
