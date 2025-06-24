from typing import Union

import aiohttp

from .base import *
from .protect import protector
from ..errors import *


class FriendMixin(WechatAPIClientBase):
    async def accept_friend(self, scene: int, v1: str, v2: str) -> bool:
        """接受好友请求

        主动添加好友单天上限如下所示：1小时内上限为 5个，超过上限时，无法发出好友请求，也收不到好友请求。

        - 新账号：5/天
        - 注册超过7天：10个/天
        - 注册满3个月&&近期登录过该电脑：15/天
        - 注册满6个月&&近期经常登录过该电脑：20/天
        - 注册满6个月&&近期频繁登陆过该电脑：30/天
        - 注册1年以上&&一直登录：50/天
        - 上一次通过好友到下一次通过间隔20-40s
        - 收到加人申请，到通过好友申请（每天最多通过300个好友申请），间隔30s+（随机时间）

        Args:
            scene: 来源 在消息的xml获取
            v1: v1key
            v2: v2key

        Returns:
            bool: 操作是否成功
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")
        elif not self.ignore_protect and protector.check(14400):
            raise BanProtection("风控保护: 新设备登录后4小时内请挂机")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "Scene": scene, "V1": v1, "V2": v2}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Friend/PassVerify', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return True
            else:
                self.error_handler(json_resp)

    async def get_contact(self, wxid: Union[str, list[str]]) -> Union[dict, list[dict]]:
        """获取联系人信息

        Args:
            wxid: 联系人wxid, 可以是多个wxid在list里，也可查询chatroom

        Returns:
            Union[dict, list[dict]]: 单个联系人返回dict，多个联系人返回list[dict]
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        if isinstance(wxid, list):
            wxid = ",".join(wxid)

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "RequestWxids": wxid}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Friend/GetContact', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                contact_list = json_resp.get("Data").get("ContactList")
                if len(contact_list) == 1:
                    return contact_list[0]
                else:
                    return contact_list
            else:
                self.error_handler(json_resp)

    async def get_contract_detail(self, wxid: Union[str, list[str]], chatroom: str = "") -> list:
        """获取联系人详情

        Args:
            wxid: 联系人wxid
            chatroom: 群聊wxid

        Returns:
            list: 联系人详情列表
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        if isinstance(wxid, list):
            if len(wxid) > 20:
                raise ValueError("一次最多查询20个联系人")
            wxid = ",".join(wxid)


        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "Towxids": wxid, "Chatroom": chatroom}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Friend/GetContractDetail', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data").get("ContactList")
            else:
                self.error_handler(json_resp)

    async def get_contract_list(self, wx_seq: int = 0, chatroom_seq: int = 0) -> dict:
        """获取联系人列表

        Args:
            wx_seq: 联系人序列
            chatroom_seq: 群聊序列

        Returns:
            dict: 联系人列表数据
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {"Wxid": self.wxid, "CurrentWxcontactSeq": wx_seq, "CurrentChatroomContactSeq": chatroom_seq}
            response = await session.post(f'http://{self.ip}:{self.port}/api/Friend/GetContractList', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data")
            else:
                self.error_handler(json_resp)

    async def get_total_contract_list(self, wx_seq: int = 0, chatroom_seq: int = 0, offset: int = 0, limit: int = 0) -> dict:
        """获取全部通讯录好友[全新API]

        Args:
            wx_seq: 联系人序列，没有的情况下请填写0
            chatroom_seq: 群聊序列，没有的情况下请填写0
            offset: 偏移量
            limit: 限制数量

        Returns:
            dict: 联系人列表数据
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            json_param = {
                "Wxid": self.wxid,
                "CurrentWxcontactSeq": wx_seq,
                "CurrentChatRoomContactSeq": chatroom_seq,
                "Offset": offset,
                "Limit": limit
            }
            response = await session.post(f'http://{self.ip}:{self.port}/api/Friend/GetTotalContractList', json=json_param)
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data")
            else:
                self.error_handler(json_resp)

    async def get_nickname(self, wxid: Union[str, list[str]]) -> Union[str, list[str]]:
        """获取用户昵称

        Args:
            wxid: 用户wxid，可以是单个wxid或最多20个wxid的列表

        Returns:
            Union[str, list[str]]: 如果输入单个wxid返回str，如果输入wxid列表则返回对应的昵称列表
        """
        data = await self.get_contract_detail(wxid)

        if isinstance(wxid, str):
            try:
                return data[0].get("NickName").get("string")
            except:
                return ""
        else:
            result = []
            for contact in data:
                try:
                    result.append(contact.get("NickName").get("string"))
                except:
                    result.append("")
            return result
