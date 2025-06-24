import base64
import io
import os
from typing import Union

import aiohttp
import pysilk
from pydub import AudioSegment
from loguru import logger

from .base import *
from .protect import protector
from ..errors import *


class ToolMixin(WechatAPIClientBase):
    async def download_image(self, aeskey: str, cdnmidimgurl: str) -> str:
        """CDN下载高清图片（新版接口）。

        Args:
            aeskey (str): 图片的AES密钥
            cdnmidimgurl (str): 图片的CDN URL

        Returns:
            str: 图片的base64编码字符串

        Raises:
            UserLoggedOut: 未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "FileAesKey": aeskey, "FileNo": cdnmidimgurl}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Tools/CdnDownloadImage', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data")
            else:
                self.error_handler(json_resp)

    async def download_voice(self, msg_id: str, voiceurl: str, length: int) -> str:
        """下载语音文件。

        Args:
            msg_id (str): 消息的msgid
            voiceurl (str): 语音的url，从xml获取
            length (int): 语音长度，从xml获取

        Returns:
            str: 语音的base64编码字符串

        Raises:
            UserLoggedOut: 未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "MsgId": msg_id, "Voiceurl": voiceurl, "Length": length}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Tools/DownloadVoice', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data").get("data").get("buffer")
            else:
                self.error_handler(json_resp)

    async def download_attach(self, attach_id: str) -> dict:
        """下载附件。

        Args:
            attach_id (str): 附件ID

        Returns:
            dict: 附件数据

        Raises:
            UserLoggedOut: 未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            # 设置请求超时时间为5分钟，以处理大文件
            timeout = aiohttp.ClientTimeout(total=300)  # 5分钟

            json_param = {"Wxid": self.wxid, "AttachId": attach_id}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Tools/DownloadAttach', json=json_param,timeout=timeout)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data").get("data").get("buffer")
            else:
                self.error_handler(json_resp)

    async def download_video(self, msg_id) -> str:
        """下载视频。

        Args:
            msg_id (str): 消息的msg_id

        Returns:
            str: 视频的base64编码字符串

        Raises:
            UserLoggedOut: 未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "MsgId": msg_id}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Tools/DownloadVideo', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data").get("data").get("buffer")
            else:
                self.error_handler(json_resp)

    async def set_step(self, count: int) -> bool:
        """设置步数。

        Args:
            count (int): 要设置的步数

        Returns:
            bool: 成功返回True，失败返回False

        Raises:
            UserLoggedOut: 未登录时调用
            BanProtection: 风控保护: 新设备登录后4小时内请挂机
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")
        elif not self.ignore_protect and protector.check(14400):
            raise BanProtection("风控保护: 新设备登录后4小时内请挂机")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "StepCount": count}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Tools/SetStep', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return True
            else:
                self.error_handler(json_resp)

    async def set_proxy(self, proxy: Proxy) -> bool:
        """设置代理。

        Args:
            proxy (Proxy): 代理配置对象

        Returns:
            bool: 成功返回True，失败返回False

        Raises:
            UserLoggedOut: 未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid,
                          "Proxy": {"ProxyIp": f"{proxy.ip}:{proxy.port}",
                                    "ProxyUser": proxy.username,
                                    "ProxyPassword": proxy.password}}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Tools/SetProxy', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return True
            else:
                self.error_handler(json_resp)

    async def check_database(self) -> bool:
        """检查数据库状态。

        Returns:
            bool: 数据库正常返回True，否则返回False
        """
        async with aiohttp.ClientSession() as session:
            response = await session.get(f'http://{self.ip}:{self.port}/api/Tools/CheckDatabaseOK')
            json_resp = await response.json()

            if json_resp.get("Running"):
                return True
            else:
                return False

    @staticmethod
    def base64_to_file(base64_str: str, file_name: str, file_path: str) -> bool:
        """将base64字符串转换为文件并保存。

        Args:
            base64_str (str): base64编码的字符串
            file_name (str): 要保存的文件名
            file_path (str): 文件保存路径

        Returns:
            bool: 转换成功返回True，失败返回False
        """
        try:
            os.makedirs(file_path, exist_ok=True)

            # 拼接完整的文件路径
            full_path = os.path.join(file_path, file_name)

            # 移除可能存在的 base64 头部信息
            if ',' in base64_str:
                base64_str = base64_str.split(',')[1]

            # 解码 base64 并写入文件
            with open(full_path, 'wb') as f:
                f.write(base64.b64decode(base64_str))

            return True

        except Exception as e:
            return False

    @staticmethod
    def file_to_base64(file_path: str) -> str:
        """将文件转换为base64字符串。

        Args:
            file_path (str): 文件路径

        Returns:
            str: base64编码的字符串
        """
        with open(file_path, 'rb') as f:
            return base64.b64encode(f.read()).decode()

    @staticmethod
    def base64_to_byte(base64_str: str) -> bytes:
        """将base64字符串转换为bytes。

        Args:
            base64_str (str): base64编码的字符串

        Returns:
            bytes: 解码后的字节数据
        """
        # 移除可能存在的 base64 头部信息
        if ',' in base64_str:
            base64_str = base64_str.split(',')[1]

        return base64.b64decode(base64_str)

    @staticmethod
    def byte_to_base64(byte: bytes) -> str:
        """将bytes转换为base64字符串。

        Args:
            byte (bytes): 字节数据

        Returns:
            str: base64编码的字符串
        """
        return base64.b64encode(byte).decode("utf-8")

    @staticmethod
    async def silk_byte_to_byte_wav_byte(silk_byte: bytes) -> bytes:
        """将silk字节转换为wav字节。

        Args:
            silk_byte (bytes): silk格式的字节数据

        Returns:
            bytes: wav格式的字节数据
        """
        return await pysilk.async_decode(silk_byte, to_wav=True)

    @staticmethod
    def wav_byte_to_amr_byte(wav_byte: bytes) -> bytes:
        """将WAV字节数据转换为AMR格式。

        Args:
            wav_byte (bytes): WAV格式的字节数据

        Returns:
            bytes: AMR格式的字节数据

        Raises:
            Exception: 转换失败时抛出异常
        """
        try:
            # 从字节数据创建 AudioSegment 对象
            audio = AudioSegment.from_wav(io.BytesIO(wav_byte))

            # 设置 AMR 编码的标准参数
            audio = audio.set_frame_rate(8000).set_channels(1)

            # 创建一个字节缓冲区来存储 AMR 数据
            output = io.BytesIO()

            # 导出为 AMR 格式
            audio.export(output, format="amr")

            # 获取字节数据
            return output.getvalue()

        except Exception as e:
            raise Exception(f"转换WAV到AMR失败: {str(e)}")

    @staticmethod
    def wav_byte_to_amr_base64(wav_byte: bytes) -> str:
        """将WAV字节数据转换为AMR格式的base64字符串。

        Args:
            wav_byte (bytes): WAV格式的字节数据

        Returns:
            str: AMR格式的base64编码字符串
        """
        return base64.b64encode(ToolMixin.wav_byte_to_amr_byte(wav_byte)).decode()

    @staticmethod
    async def wav_byte_to_silk_byte(wav_byte: bytes) -> bytes:
        """将WAV字节数据转换为silk格式。

        Args:
            wav_byte (bytes): WAV格式的字节数据

        Returns:
            bytes: silk格式的字节数据
        """
        # get pcm data
        audio = AudioSegment.from_wav(io.BytesIO(wav_byte))
        pcm = audio.raw_data
        return await pysilk.async_encode(pcm, data_rate=audio.frame_rate, sample_rate=audio.frame_rate)

    @staticmethod
    async def wav_byte_to_silk_base64(wav_byte: bytes) -> str:
        """将WAV字节数据转换为silk格式的base64字符串。

        Args:
            wav_byte (bytes): WAV格式的字节数据

        Returns:
            str: silk格式的base64编码字符串
        """
        return base64.b64encode(await ToolMixin.wav_byte_to_silk_byte(wav_byte)).decode()

    @staticmethod
    async def silk_base64_to_wav_byte(silk_base64: str) -> bytes:
        """将silk格式的base64字符串转换为WAV字节数据。

        Args:
            silk_base64 (str): silk格式的base64编码字符串

        Returns:
            bytes: WAV格式的字节数据
        """
        return await ToolMixin.silk_byte_to_byte_wav_byte(base64.b64decode(silk_base64))

    async def upload_file(self, file_data: Union[str, bytes, os.PathLike]) -> dict:
        """上传文件到服务器。

        Args:
            file_data (Union[str, bytes, os.PathLike]): 文件数据，支持base64字符串，字节数据或文件路径

        Returns:
            dict: 包含上传文件信息的字典，包括MD5和总长度

        Raises:
            UserLoggedOut: 未登录时调用
            ValueError: 文件数据格式不正确
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        # 处理不同类型的输入
        if isinstance(file_data, str):
            # 如果是字符串，假定是base64编码或文件路径
            if os.path.exists(file_data):
                # 如果是文件路径
                with open(file_data, 'rb') as f:
                    file_base64 = base64.b64encode(f.read()).decode()
            else:
                # 假定是base64字符串
                file_base64 = file_data
        elif isinstance(file_data, bytes):
            # 如果是字节数据，转换为base64
            file_base64 = base64.b64encode(file_data).decode()
        elif isinstance(file_data, os.PathLike):
            # 如果是文件路径对象
            with open(file_data, 'rb') as f:
                file_base64 = base64.b64encode(f.read()).decode()
        else:
            raise ValueError("文件数据必须是base64字符串、字节数据或文件路径")

        # 发送请求上传文件
        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "Base64": file_base64}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Tools/UploadFile', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                # 返回数据，可能在Data中或直接在根层级
                data = json_resp.get("Data") or json_resp
                return data
            else:
                self.error_handler(json_resp)

    async def download_emoji(self, md5: str) -> dict:
        """下载表情。

        Args:
            md5 (str): 表情的MD5值

        Returns:
            dict: 返回下载结果

        Raises:
            UserLoggedOut: 未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "Md5": md5}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Tools/EmojiDownload', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                logger.info("下载表情: MD5:{}", md5)
                return json_resp
            else:
                self.error_handler(json_resp)