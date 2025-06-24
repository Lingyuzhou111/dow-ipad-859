class MarshallingError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class UnmarshallingError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class MMTLSError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class PacketError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class ParsePacketError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class DatabaseError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class LoginError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class UserLoggedOut(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class BanProtection(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
