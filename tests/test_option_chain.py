"""
Futu/Moomoo 期权链字段探测 — 打印真实列名，判断 OI/volume 是否在 chain 里。
用法: python tests/test_option_chain.py
"""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    from dotenv import load_dotenv
    load_dotenv(BASE / ".env")
except Exception:
    pass

try:
    from moomoo import OpenQuoteContext, RET_OK
    SDK = "moomoo"
except ImportError:
    from futu import OpenQuoteContext, RET_OK
    SDK = "futu"

try:
    from config.settings import FUTU_HOST, FUTU_PORT
except Exception:
    import os
    FUTU_HOST = os.getenv("FUTU_HOST", "127.0.0.1")
    FUTU_PORT = int(os.getenv("FUTU_PORT", "11111"))


def main():
    print(f"SDK: {SDK}   host: {FUTU_HOST}:{FUTU_PORT}\n")
    ctx = OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    try:
        # ── 1. expiration date ─────────────────────────────────
        print("── STEP 1: get_option_expiration_date ─────")
        ret, df = ctx.get_option_expiration_date(code="US.RKLB")
        print(f"  ret={ret}")
        if ret != RET_OK or df is None or df.empty:
            print(f"  FAILED: {df}")
            return
        print(f"  columns: {list(df.columns)}")
        print(df.head(3).to_string(index=False))

        col = "strike_time" if "strike_time" in df.columns else df.columns[0]
        nearest = sorted(df[col].dropna().unique())[0]
        if len(str(nearest)) > 10:
            nearest = str(nearest)[:10]
        print(f"\n  nearest expiry: {nearest}\n")

        # ── 2. option chain ────────────────────────────────────
        print("── STEP 2: get_option_chain ───────────────")
        ret, df2 = ctx.get_option_chain(code="US.RKLB", start=nearest, end=nearest)
        print(f"  ret={ret}")
        if ret != RET_OK or df2 is None or df2.empty:
            print(f"  FAILED: {df2}")
            return
        print(f"  rows: {len(df2)}")
        print(f"  columns: {list(df2.columns)}")
        print("\n  first 3 rows (subset):")
        keep_cols = [c for c in df2.columns
                     if any(k in c.lower() for k in
                            ['code', 'name', 'type', 'strike', 'volume', 'open_interest', 'oi', 'price'])]
        print(df2.head(3)[keep_cols].to_string(index=False))

        oi_cols   = [c for c in df2.columns if 'open' in c.lower() or c.lower() in ('oi',) or 'interest' in c.lower()]
        vol_cols  = [c for c in df2.columns if 'vol' in c.lower() or 'turnover' in c.lower()]
        print(f"\n  potential OI cols: {oi_cols}")
        print(f"  potential vol cols: {vol_cols}")

        # ── 3. 没 OI 字段则试 get_market_snapshot ─────────────
        if not oi_cols or all(df2[c].fillna(0).sum() == 0 for c in oi_cols):
            print("\n── STEP 3: chain 无 OI 字段，试 get_market_snapshot ──")
            codes = df2['code'].head(6).tolist() if 'code' in df2.columns else []
            print(f"  sample codes: {codes}")
            if codes:
                ret3, df3 = ctx.get_market_snapshot(codes)
                print(f"  ret={ret3}")
                if ret3 == RET_OK and df3 is not None and not df3.empty:
                    print(f"  columns: {list(df3.columns)}")
                    oi3 = [c for c in df3.columns if 'open' in c.lower() or 'interest' in c.lower() or c.lower() in ('oi',)]
                    vol3 = [c for c in df3.columns if 'vol' in c.lower()]
                    print(f"  snapshot OI cols: {oi3}")
                    print(f"  snapshot vol cols: {vol3}")
                    keep3 = [c for c in df3.columns if any(k in c.lower() for k in
                            ['code', 'option_open_interest', 'open_interest', 'volume', 'last_price', 'strike'])][:8]
                    print(df3[keep3].head(3).to_string(index=False))
                else:
                    print(f"  snapshot failed: {df3}")
    finally:
        ctx.close()


if __name__ == "__main__":
    main()


import unittest


class TestOptionChainManualProbe(unittest.TestCase):
    @unittest.skip("Manual Futu/Moomoo API probe; run tests/test_option_chain.py directly.")
    def test_manual_probe(self):
        main()
