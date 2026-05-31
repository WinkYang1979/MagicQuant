"""
MagicQuant recent deal query.
VERSION: v0.1.0
DATE: 2026-05-23
DEPENDS: config.settings, moomoo/futu OpenSecTradeContext

Read-only trade/deal export for review. / 只读导出成交与订单用于复盘。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import FUTU_HOST, FUTU_PORT  # noqa: E402

try:
    from moomoo import OpenSecTradeContext, TrdEnv, TrdMarket, RET_OK
    try:
        from moomoo import SecurityFirm
        SEC_FIRM = SecurityFirm.FUTUAU
    except Exception:
        SEC_FIRM = None
except ImportError:
    from futu import OpenSecTradeContext, TrdEnv, TrdMarket, RET_OK
    try:
        from futu import SecurityFirm
        SEC_FIRM = SecurityFirm.FUTUAU
    except Exception:
        SEC_FIRM = None


def _df_records(df):
    try:
        return json.loads(df.to_json(orient="records", force_ascii=False, date_format="iso"))
    except Exception:
        return []


def main() -> int:
    kwargs = dict(filter_trdmarket=TrdMarket.US, host=FUTU_HOST, port=FUTU_PORT)
    if SEC_FIRM is not None:
        kwargs["security_firm"] = SEC_FIRM
    ctx = OpenSecTradeContext(**kwargs)
    out = {
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "host": FUTU_HOST,
        "port": FUTU_PORT,
        "deals": [],
        "orders": [],
        "errors": [],
    }
    try:
        ret, deals = ctx.deal_list_query(trd_env=TrdEnv.REAL)
        if ret == RET_OK:
            out["deals"] = _df_records(deals)
        else:
            out["errors"].append(f"deal_list_query: {deals}")
        try:
            ret, orders = ctx.history_order_list_query(trd_env=TrdEnv.REAL)
            if ret == RET_OK:
                out["orders"] = _df_records(orders)
            else:
                out["errors"].append(f"history_order_list_query: {orders}")
        except Exception as exc:
            out["errors"].append(f"history_order_list_query exception: {exc}")
    finally:
        ctx.close()

    review_dir = ROOT / "data" / "review" / datetime.now().strftime("%Y-%m-%d")
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_dir / "futu_recent_deals.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"saved {path}")
    print(f"deals={len(out['deals'])} orders={len(out['orders'])} errors={len(out['errors'])}")
    for row in out["deals"][:20]:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
