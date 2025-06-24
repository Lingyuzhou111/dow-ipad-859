from typing import Union, Any

import aiohttp

from .base import *
from .protect import protector
from ..errors import *


class ChatroomMixin(WechatAPIClientBase):
    async def add_chatroom_member(self, chatroom: str, wxid: str) -> bool:
        """添加群成员(群聊最多40人)

        Args:
            ChatRoomName: 群聊wxid
            wxid: 要添加的wxid

        Returns:
            bool: 成功返回True, 失败False或者报错
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")
        elif not self.ignore_protect and protector.check(14400):
            raise BanProtection("风控保护: 新设备登录后4小时内请挂机")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "ChatRoomName": chatroom, "ToWxids": wxid}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Group/AddChatroomMember', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return True
            else:
                self.error_handler(json_resp)

    async def get_chatroom_announce(self, chatroom: str) -> dict:
        """获取群聊公告

        Args:
            QID: 群聊id

        Returns:
            dict: 群聊信息字典
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "QID": chatroom}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Group/GetChatroomInfoDetail', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                data = dict(json_resp.get("Data"))
                data.pop("BaseResponse")
                return data
            else:
                self.error_handler(json_resp)

    async def get_chatroom_info(self, chatroom: str) -> dict:
        """获取群聊信息

        Args:
            QID: 群聊id

        Returns:
            dict: 群聊信息字典
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")
        elif not self.ignore_protect and protector.check(14400):
            raise BanProtection("风控保护: 新设备登录后4小时内请挂机")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "QID": chatroom}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Group/GetChatroomInfo', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data").get("ContactList")[0]
            else:
                self.error_handler(json_resp)

    async def get_chatroom_member_list(self, chatroom: str) -> list[dict]:
        """获取群聊成员列表

        Args:
            QID: 群聊id

        Returns:
            list[dict]: 群聊成员列表
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "QID": chatroom}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Group/GetChatroomMemberDetail', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data").get("NewChatroomData").get("ChatRoomMember")
            else:
                self.error_handler(json_resp)

    async def get_chatroom_qrcode(self, chatroom: str) -> dict[str, Any]:
        """获取群聊二维码

        Args:
            QID: 群聊id

        Returns:
            dict: {"base64": 二维码的base64, "description": 二维码描述}
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")
        elif not self.ignore_protect and protector.check(86400):
            raise BanProtection("获取二维码需要在登录后24小时才可使用")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "QID": chatroom}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Group/GetQRCode', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                data = json_resp.get("Data")
                return {"base64": data.get("qrcode").get("buffer"), "description": data.get("revokeQrcodeWording")}
            else:
                self.error_handler(json_resp)

    async def invite_chatroom_member(self, wxid: Union[str, list], chatroom: str) -> bool:
        """邀请群聊成员(群聊大于40人)

        Args:
            ToWxids: 要邀请的用户wxid或wxid列表
            ChatRoomName: 群聊id

        Returns:
            bool: 成功返回True, 失败False或者报错
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")
        elif not self.ignore_protect and protector.check(14400):
            raise BanProtection("风控保护: 新设备登录后4小时内请挂机")

        if isinstance(wxid, list):
            wxid = ",".join(wxid)

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "ChatRoomName": chatroom, "ToWxids": wxid}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Group/InviteChatroomMember', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return True
            else:
                self.error_handler(json_resp)
