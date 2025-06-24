import json
import os
from datetime import datetime


class Singleton(type):
    """单例模式的元类。

    用于确保一个类只有一个实例。

    Attributes:
        _instances (dict): 存储类的实例的字典
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        """创建或返回类的单例实例。

        Args:
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            object: 类的单例实例
        """
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class Protect(metaclass=Singleton):
    """保护类，风控保护机制。

    使用单例模式确保全局只有一个实例。

    Attributes:
        login_stat_path (str): 登录状态文件的路径
        login_stat (dict): 登录状态信息
        login_time (int): 最后登录时间戳
        login_device_id (str): 最后登录的设备ID
    """

    def __init__(self):
        """初始化保护类实例。

        创建或加载登录状态文件，初始化登录时间和设备ID。
        """
        self.login_stat_path = os.path.join(os.path.dirname(__file__), "login_stat.json")

        if not os.path.exists(self.login_stat_path):
            default_config = {
                "login_time": 0,
                "device_id": ""
            }
            with open(self.login_stat_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(default_config, indent=4, ensure_ascii=False))
            self.login_stat = default_config
        else:
            with open(self.login_stat_path, "r", encoding="utf-8") as f:
                self.login_stat = json.loads(f.read())

        self.login_time = self.login_stat.get("login_time", 0)
        self.login_device_id = self.login_stat.get("device_id", "")

    def check(self, second: int) -> bool:
        """检查是否在指定时间内，风控保护。

        Args:
            second (int): 指定的秒数

        Returns:
            bool: 如果当前时间与上次登录时间的差小于指定秒数，返回True；否则返回False
        """
        now = datetime.now().timestamp()
        return now - self.login_time < second

    def update_login_status(self, device_id: str = ""):
        """更新登录状态。

        如果设备ID发生变化，更新登录时间和设备ID，并保存到文件。

        Args:
            device_id (str, optional): 设备ID. Defaults to "".
        """
        if device_id == self.login_device_id:
            return
        self.login_time = int(datetime.now().timestamp())
        self.login_stat["login_time"] = self.login_time
        self.login_stat["device_id"] = device_id
        with open(self.login_stat_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.login_stat, indent=4, ensure_ascii=False))


protector = Protect()
