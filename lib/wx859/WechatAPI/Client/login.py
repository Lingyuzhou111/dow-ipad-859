import hashlib
import string
from random import choice
from typing import Union

import aiohttp
import qrcode

from .base import *
from .protect import protector
from ..errors import *


class LoginMixin(WechatAPIClientBase):
    async def is_running(self) -> bool:
        """检查API服务是否运行

        Returns:
            bool: 如果服务正在运行返回True，否则返回False
        """
        try:
            async with aiohttp.ClientSession() as session:
                response = await session.get(self._get_full_url("/"))
                return response.status < 500
        except Exception:
            return False

    async def get_qr_code(self, device_name: str, device_id: str = "", proxy: Proxy = None, print_qr: bool = False) -> tuple[str, str]:
        """获取登录二维码。

        Args:
            device_name (str): 设备名称
            device_id (str, optional): 设备ID. Defaults to "".
            proxy (Proxy, optional): 代理信息. Defaults to None.
            print_qr (bool, optional): 是否在控制台打印二维码. Defaults to False.

        Returns:
            tuple[str, str]: 返回登录二维码的UUID和URL

        Raises:
            根据error_handler处理错误
        """
        async with aiohttp.ClientSession() as session:
            json_param = {'DeviceName': device_name, 'DeviceID': device_id}
            if proxy:
                json_param['Proxy'] = {'ProxyIp': f'{proxy.ip}:{proxy.port}',
                                       'ProxyPassword': proxy.password,
                                       'ProxyUser': proxy.username}

            # 修改为859协议的标准iPad二维码获取接口
            response = await session.post(self._get_full_url("/Login/LoginGetQR"), json=json_param)
            json_resp = await response.json()
            
            if (json_resp.get("Code") == 0 or json_resp.get("Success")) and json_resp.get("Data"):
                data = json_resp.get("Data", {})
                uuid = data.get("Uuid", "") or data.get("uuid", "")
                qr_url = data.get("QrUrl", "")
                
                if print_qr and uuid:
                    try:
                        qr = qrcode.QRCode(
                            version=1,
                            error_correction=qrcode.constants.ERROR_CORRECT_L,
                            box_size=10,
                            border=4,
                        )
                        qr.add_data(f'http://weixin.qq.com/x/{uuid}')
                        qr.make(fit=True)
                        print("\n=== 请用微信扫描以下二维码登录 ===")
                        qr.print_ascii()
                        print("=====================================\n")
                    except Exception as e:
                        print(f"[ERROR] 生成ASCII二维码失败: {e}")

                return uuid, qr_url if qr_url else f'http://weixin.qq.com/x/{uuid}' if uuid else ""
            else:
                return "", ""

    async def check_login_uuid(self, uuid: str, device_id: str = "") -> tuple[bool, Union[dict, int]]:
        """检查登录的UUID状态。

        Args:
            uuid (str): 登录的UUID
            device_id (str, optional): 设备ID. Defaults to "".

        Returns:
            tuple[bool, Union[dict, int]]: 如果登录成功返回(True, 用户信息)，否则返回(False, 过期时间)

        Raises:
            根据error_handler处理错误
        """
        async with aiohttp.ClientSession() as session:
            # 修改为859协议的标准登录检查接口
            response = await session.post(self._get_full_url(f"/Login/LoginCheckQR?uuid={uuid}"))
            
            if response.content_type == 'application/json':
                json_resp = await response.json()
                
                if json_resp and (json_resp.get("Success") or json_resp.get("Code") == 0):
                    data = json_resp.get("Data", {})
                    status = data.get("status", 0)
                    
                    if status == 1:
                        # 登录成功，提取用户信息
                        nickname = data.get("nickName", "")
                        head_img_url = data.get("headImgUrl", "")
                        wxid = ""
                        
                        # 优先检查acctSectResp字段（849协议的成功方法）
                        if data.get("acctSectResp"):
                            acct_resp = data.get("acctSectResp")
                            wxid = acct_resp.get("userName", "")
                            if not nickname:
                                nickname = acct_resp.get("nickName", "")
                        
                        # 通过昵称映射获取真实微信ID
                        if not wxid and nickname:
                            real_wxid = self._get_wxid_by_nickname(nickname)
                            if real_wxid:
                                wxid = real_wxid
                        
                        # 如果仍然没有微信ID，使用UUID作为临时标识
                        if not wxid:
                            wxid = f"temp_{uuid[:12]}"
                        
                        self.wxid = wxid
                        self.nickname = nickname
                        
                        # 构建返回的用户信息
                        user_info = {
                            "wxid": wxid,
                            "userName": wxid,
                            "nickName": nickname,
                            "headImgUrl": head_img_url,
                            "status": status,
                            "uuid": uuid
                        }
                        
                        # 兼容主程序的数据结构
                        if wxid.startswith("temp_"):
                            user_info["acctSectResp"] = {
                                "userName": wxid,
                                "nickName": nickname
                            }
                        
                        protector.update_login_status(device_id=device_id)
                        return True, user_info
                    
                    elif status == 0:
                        # 等待扫码
                        expired_time = data.get("expiredTime", 0)
                        return False, expired_time
                    
                    else:
                        return False, f"未知状态: {status}"
                        
                else:
                    return False, "API调用失败"
            else:
                return False, "响应格式错误"

    async def log_out(self) -> bool:
        """登出当前账号。

        Returns:
            bool: 登出成功返回True，否则返回False

        Raises:
            UserLoggedOut: 如果未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            response = await session.post(self._get_full_url(f"/Login/LogOut?wxid={self.wxid}"))
            json_resp = await response.json()

            if json_resp.get("Success"):
                return True
            elif json_resp.get("Success"):
                return False
            else:
                self.error_handler(json_resp)

    async def awaken_login(self, wxid: str = "") -> str:
        """唤醒登录。

        Args:
            wxid (str, optional): 要唤醒的微信ID. Defaults to "".

        Returns:
            str: 返回新的登录UUID

        Raises:
            Exception: 如果未提供wxid且未登录
            LoginError: 如果无法获取UUID
            根据error_handler处理错误
        """
        if not wxid and not self.wxid:
            raise Exception("Please login using QRCode first")

        if not wxid and self.wxid:
            wxid = self.wxid

        async with aiohttp.ClientSession() as session:
            # 修改为859协议的唤醒登录接口（使用ExtDeviceLoginConfirmGet）
            json_param = {"Wxid": wxid}
            response = await session.post(self._get_full_url("/Login/ExtDeviceLoginConfirmGet"), json=json_param)
            json_resp = await response.json()

            # 安全的数据访问，避免NoneType错误
            if json_resp and json_resp.get("Success"):
                data = json_resp.get("Data")
                if data and isinstance(data, dict):
                    qr_response = data.get("QrCodeResponse")
                    if qr_response and isinstance(qr_response, dict):
                        uuid = qr_response.get("Uuid")
                        if uuid:
                            return uuid
            
            # 如果任何步骤失败，返回空字符串
            return ""

    async def twice_login(self, wxid: str = "") -> str:
        """二次登录。

        Args:
            wxid (str, optional): 二次的微信ID. Defaults to "".

        Returns:
            str: 返回登录信息

        Raises:
            Exception: 如果未提供wxid且未登录
            LoginError: 如果无法获取UUID
            根据error_handler处理错误
        """
        if not wxid and not self.wxid:
            raise Exception("Please login using QRCode first")

        if not wxid and self.wxid:
            wxid = self.wxid

        async with aiohttp.ClientSession() as session:
            # 修改为859协议的二次登录接口
            response = await session.post(self._get_full_url(f"/Login/LoginTwiceAutoAuth?wxid={wxid}"))
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data")
            else:
                # self.error_handler(json_resp)
                return ""

    async def get_cached_info(self, wxid: str = "") -> dict:
        """获取登录缓存信息。

        Args:
            wxid (str, optional): 要查询的微信ID. Defaults to None.

        Returns:
            dict: 返回缓存信息，如果未提供wxid且未登录返回空字典
        """
        async with aiohttp.ClientSession() as session:
            # 尝试859协议的查询参数格式
            try:
                response = await session.post(self._get_full_url(f"/Login/GetCacheInfo?wxid={wxid}"))
                json_resp = await response.json()
                if json_resp.get("Success"):
                    return json_resp.get("Data")
            except Exception:
                pass
            
            # 尝试849协议的表单数据格式
            try:
                json_param = {"wxid": wxid}
                response = await session.post(self._get_full_url("/Login/GetCacheInfo"), data=json_param)
                json_resp = await response.json()
                if json_resp.get("Success"):
                    return json_resp.get("Data")
            except Exception:
                pass
            
            return None

    async def heartbeat(self) -> bool:
        """发送心跳包。

        Returns:
            bool: 成功返回True，否则返回False

        Raises:
            UserLoggedOut: 如果未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            response = await session.post(self._get_full_url(f"/Login/HeartBeat?wxid={self.wxid}"))
            json_resp = await response.json()

            if json_resp.get("Success") and json_resp.get("Data").get("status") == 0:
                return True
            else:
                return False

    async def start_auto_heartbeat(self) -> bool:
        """开始自动心跳。

        Returns:
            bool: 成功返回True，否则返回False

        Raises:
            UserLoggedOut: 如果未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            # 修改为859协议的自动心跳开启接口
            response = await session.post(self._get_full_url(f"/Login/AutoHeartBeat?wxid={self.wxid}"))
            json_resp = await response.json()

            if json_resp.get("Success"):
                return True
            else:
                # self.error_handler(json_resp)
                return False

    async def stop_auto_heartbeat(self) -> bool:
        """停止自动心跳。

        Returns:
            bool: 成功返回True，否则返回False

        Raises:
            UserLoggedOut: 如果未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            # 修改为859协议的关闭自动心跳接口
            response = await session.post(self._get_full_url(f"/Login/CloseAutoHeartBeat?wxid={self.wxid}"))
            json_resp = await response.json()

            if json_resp.get("Success"):
                return True
            else:
                self.error_handler(json_resp)

    async def get_auto_heartbeat_status(self) -> bool:
        """获取自动心跳状态。

        Returns:
            bool: 如果正在运行返回True，否则返回False

        Raises:
            UserLoggedOut: 如果未登录时调用
            根据error_handler处理错误
        """
        if not self.wxid:
            raise UserLoggedOut("请先登录")

        async with aiohttp.ClientSession() as session:
            # 修改为859协议的自动心跳状态查询接口
            response = await session.post(self._get_full_url(f"/Login/AutoHeartBeatLog?wxid={self.wxid}"))
            json_resp = await response.json()

            if json_resp.get("Success"):
                return json_resp.get("Data").get("status", False)
            else:
                return False

    def _get_wxid_by_nickname(self, nickname: str) -> str:
        """通过昵称获取真实的微信ID
        
        Args:
            nickname: 用户昵称
            
        Returns:
            str: 真实的微信ID，如果未找到返回空字符串
        """
        try:
            import json
            import os
            
            mapping_file = "nickname_wxid_mapping.json"
            
            # 如果文件不存在，创建默认文件
            if not os.path.exists(mapping_file):
                default_mapping = {
                    "晓艾": "wxid_7yzw5x3vqw0d29",
                    "_comment": "昵称到微信ID的映射缓存，格式: {\"昵称\": \"真实微信ID\"}"
                }
                with open(mapping_file, "w", encoding="utf-8") as f:
                    json.dump(default_mapping, f, indent=2, ensure_ascii=False)
            
            # 读取映射文件
            with open(mapping_file, "r", encoding="utf-8") as f:
                mapping = json.load(f)
            
            return mapping.get(nickname, "")
            
        except Exception:
            return ""
    
    def _update_nickname_mapping(self, nickname: str, wxid: str):
        """更新昵称到微信ID的映射
        
        Args:
            nickname: 用户昵称
            wxid: 真实的微信ID
        """
        try:
            import json
            import os
            
            mapping_file = "nickname_wxid_mapping.json"
            
            # 读取现有映射
            mapping = {}
            if os.path.exists(mapping_file):
                with open(mapping_file, "r", encoding="utf-8") as f:
                    mapping = json.load(f)
            
            # 更新映射
            if nickname and wxid and not wxid.startswith("temp_"):
                mapping[nickname] = wxid
                
                # 保存映射
                with open(mapping_file, "w", encoding="utf-8") as f:
                    json.dump(mapping, f, indent=2, ensure_ascii=False)
            
        except Exception:
            pass
    
    def add_nickname_mapping(self, nickname: str, wxid: str):
        """手动添加昵称到微信ID的映射
        
        Args:
            nickname: 用户昵称
            wxid: 真实的微信ID
        """
        self._update_nickname_mapping(nickname, wxid)

    @staticmethod
    def create_device_name() -> str:
        """生成一个随机的设备名。

        Returns:
            str: 返回生成的设备名
        """
        first_names = [
            "Oliver", "Emma", "Liam", "Ava", "Noah", "Sophia", "Elijah", "Isabella",
            "James", "Mia", "William", "Amelia", "Benjamin", "Harper", "Lucas", "Evelyn",
            "Henry", "Abigail", "Alexander", "Ella", "Jackson", "Scarlett", "Sebastian",
            "Grace", "Aiden", "Chloe", "Matthew", "Zoey", "Samuel", "Lily", "David",
            "Aria", "Joseph", "Riley", "Carter", "Nora", "Owen", "Luna", "Daniel",
            "Sofia", "Gabriel", "Ellie", "Matthew", "Avery", "Isaac", "Mila", "Leo",
            "Julian", "Layla"
        ]

        last_names = [
            "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
            "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
            "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
            "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
            "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill",
            "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell",
            "Mitchell", "Carter", "Roberts", "Gomez", "Phillips", "Evans"
        ]

        return choice(first_names) + " " + choice(last_names) + "'s Pad"

    @staticmethod
    def create_device_id(s: str = "") -> str:
        """生成设备ID。

        Args:
            s (str, optional): 用于生成ID的字符串. Defaults to "".

        Returns:
            str: 返回生成的设备ID
        """
        if s == "" or s == "string":
            s = ''.join(choice(string.ascii_letters) for _ in range(15))
        md5_hash = hashlib.md5(s.encode()).hexdigest()
        return "49" + md5_hash[2:]
