"""
MagicQuant Focus — 标的配对配置
Dare to dream. Data to win.

关键:定义主标的(信号源)和跟随标的(交易工具)的关系
格式:
    "主标的": {
        "long":  ["做多工具列表"],    # RKLB 涨时买这些
        "short": ["做空工具列表"],    # RKLB 跌时买这些
        "atr_usd_target": 0.5,        # 每股波动目标(美元)
    }
"""

FOCUS_PAIRS = {
    # Rocket Lab 主标的
    "US.RKLB": {
        "long":  ["US.RKLX"],           # 2倍做多 RKLB ETF (RKLB 涨时买)
        "short": ["US.RKLZ"],           # 2倍做空 RKLB ETF (RKLB 跌时买)
        "name":  "Rocket Lab",
    },

    # Tesla 主标的(预留)
    "US.TSLA": {
        "long":  ["US.TSLL"],           # 1.5倍做多 TSLA ETF
        "short": ["US.TSLR"],           # 2倍做空 TSLA ETF
        "name":  "Tesla",
    },

    # Nvidia 主标的(预留)
    "US.NVDA": {
        "long":  ["US.NVDL"],           # 2倍做多 NVDA
        "short": ["US.NVDQ"],           # 2倍做空 NVDA
        "name":  "NVIDIA",
    },

    # AMD 主标的(预留)
    "US.AMD": {
        "long":  ["US.AMDL"],           # 2倍做多 AMD
        "short": ["US.AMDD"],           # 1倍做空 AMD
        "name":  "AMD",
    },
}


def get_pair_config(master: str) -> dict:
    """获取主标的配对配置"""
    if not master.startswith("US."):
        master = "US." + master
    return FOCUS_PAIRS.get(master, {"long": [], "short": [], "name": master})


def get_long_tools(master: str) -> list:
    """获取做多工具列表"""
    return get_pair_config(master).get("long", [])


def get_short_tools(master: str) -> list:
    """获取做空工具列表"""
    return get_pair_config(master).get("short", [])


def get_all_followers(master: str) -> list:
    """获取所有跟随标的(做多 + 做空)"""
    cfg = get_pair_config(master)
    return cfg.get("long", []) + cfg.get("short", [])


def classify_follower(master: str, follower: str) -> str:
    """
    判断跟随标的的方向
    返回: "long"  — 该标的在主标涨时获利
         "short" — 该标的在主标跌时获利
         "unknown"
    """
    cfg = get_pair_config(master)
    if follower in cfg.get("long", []):
        return "long"
    if follower in cfg.get("short", []):
        return "short"
    return "unknown"
