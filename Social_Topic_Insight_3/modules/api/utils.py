from typing import Any

def resp_200(data: Any = None, msg: str = "success"):
    return {
        "code": 200,
        "msg": msg,
        "data": data
    }

def resp_400(msg: str = "bad request"):
    return {
        "code": 400,
        "msg": msg,
        "data": None
    }