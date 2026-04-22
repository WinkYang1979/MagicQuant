"""
MagicQuant Risk Engine — 配置加载器
Dare to dream. Data to win.

所有阈值从 config/risk_config.json 读取,不在代码里写死.
这样明天 v0.3.6 实盘数据回来后,只改 JSON 就能调参.
"""

import json
import os


_config_cache = None
_config_mtime = 0


DEFAULT_CONFIG = {
    # ── PDT ──
    "pdt_limit":                     3,          # 5 日内最多 3 次
    
    # ── 资金风险 ──
    "daily_loss_limit_usd":          -400.0,     # 单日最多亏 $400 (账户 2%)
    "max_drawdown_pct":              -8.0,       # 最大回撤 8%
    "consecutive_losses_limit":      3,          # 连亏 3 笔熔断
    "cash_safety_margin":            10.0,       # 现金安全垫
    
    # ── 仓位 ──
    "max_effective_leverage":        1.8,        # 有效杠杆上限
    "max_concentration_pct":         40.0,       # 单票占比上限
    
    # ── 费用 / RR ──
    "min_net_profit_usd":            5.0,        # 最低净利
    "min_profit_over_fee_multiplier":2.0,        # 净利/费用最低 2 倍
    "min_rr_ratio":                  1.5,        # RR 比最低
    
    # ── 价差 ──
    "max_spread_pct":                0.5,        # 最大价差 0.5%
    
    # ── 信号质量 ──
    "min_confidence":                0.60,       # AI 信心最低 60%
    
    # ── 财报 ──
    "pre_earnings_warn_days":        2,          # 财报前 2 天提示
    
    # ── 日志 ──
    "log_to_jsonl":                  True,
    "log_max_bytes":                 10 * 1024 * 1024,  # 10 MB
}


def _get_config_path() -> str:
    """找到 risk_config.json 的路径"""
    # 尝试几个常见位置
    candidates = []
    
    # 1. 通过 settings.BASE_DIR
    try:
        from config.settings import BASE_DIR
        candidates.append(os.path.join(BASE_DIR, "config", "risk_config.json"))
    except ImportError:
        pass
    
    # 2. 相对当前文件
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "..", "..", "config", "risk_config.json"))
    
    # 3. 环境变量
    env_path = os.environ.get("MQ_RISK_CONFIG")
    if env_path:
        candidates.insert(0, env_path)
    
    for p in candidates:
        if os.path.exists(p):
            return p
    
    return candidates[0] if candidates else "config/risk_config.json"


def get_risk_config(force_reload: bool = False) -> dict:
    """
    获取风控配置. 自动检测文件修改时间, 热重载.
    """
    global _config_cache, _config_mtime
    
    path = _get_config_path()
    
    if not os.path.exists(path):
        # 文件不存在, 用默认值
        if _config_cache is None:
            _config_cache = dict(DEFAULT_CONFIG)
        return _config_cache
    
    try:
        mtime = os.path.getmtime(path)
        if force_reload or _config_cache is None or mtime > _config_mtime:
            with open(path, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
            # 合并默认和文件
            merged = dict(DEFAULT_CONFIG)
            merged.update(file_cfg)
            _config_cache = merged
            _config_mtime = mtime
    except Exception as e:
        print(f"  [risk_config] load err: {e}, 使用默认")
        if _config_cache is None:
            _config_cache = dict(DEFAULT_CONFIG)
    
    return _config_cache


def save_default_config(path: str = None):
    """生成默认配置文件(首次部署用)"""
    if path is None:
        path = _get_config_path()
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    return path


if __name__ == "__main__":
    # python config_loader.py 生成默认配置
    p = save_default_config()
    print(f"✅ 默认配置已保存: {p}")
