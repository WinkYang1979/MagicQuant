"""
MagicQuant 诊断脚本 — 夜盘行情定位
放到 C:\MagicQuant\ 根目录,命令行运行:
    python diag_overnight.py US.RKLZ

目的:
  1) 打印 get_market_snapshot 返回的所有列,定位夜盘价字段名
  2) 打印订阅 K_1M 的最近 3 根,看 timestamp 是否覆盖当前时间
  3) 对比 last_price 和其他价格字段,找出夜盘实时价在哪
"""
import sys
import time
from datetime import datetime

try:
    from moomoo import OpenQuoteContext, RET_OK, SubType, KLType
except ImportError:
    from futu import OpenQuoteContext, RET_OK, SubType, KLType

from config.settings import FUTU_HOST, FUTU_PORT


def diag(ticker: str):
    print(f"\n{'='*70}")
    print(f"  诊断 {ticker}  @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    ctx = OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)

    # ── 1. Snapshot 全字段转储 ──────────────────────────────────────
    print("【1】get_market_snapshot — 所有字段:")
    ret, snap = ctx.get_market_snapshot([ticker])
    if ret != RET_OK:
        print(f"  ❌ snapshot 失败: {snap}")
    else:
        row = snap.iloc[0]
        # 把所有列打印出来,重点看含 price / pre / post / after / overnight / ext 的字段
        print(f"  可用列数: {len(row.index)}")
        for col in row.index:
            val = row[col]
            # 只打印带 price / time / status 或非零非空的关键字段
            lc = col.lower()
            if any(k in lc for k in ['price', 'time', 'status', 'pre', 'post',
                                       'after', 'overnight', 'ext', 'last', 'volume',
                                       'change', 'amplitude', 'turnover']):
                print(f"    {col:35s} = {val}")

    # ── 2. 订阅 + 拉 K_1M,看是否有夜盘数据 ─────────────────────────
    print("\n【2】订阅 K_1M + 最近 5 根 K 线:")
    try:
        ret_sub, err_sub = ctx.subscribe([ticker], [SubType.K_1M])
        if ret_sub != RET_OK:
            print(f"  ⚠️ subscribe 失败: {err_sub}")
        else:
            print(f"  ✅ subscribe OK, 等待 2 秒让数据到位...")
            time.sleep(2)

            ret_k, kline = ctx.get_cur_kline(ticker, 5, KLType.K_1M)
            if ret_k != RET_OK:
                print(f"  ❌ get_cur_kline 失败: {kline}")
            else:
                print(f"  最近 {len(kline)} 根 1M K 线:")
                for _, r in kline.iterrows():
                    print(f"    {r['time_key']}  O={r['open']:.3f}  "
                          f"H={r['high']:.3f}  L={r['low']:.3f}  "
                          f"C={r['close']:.3f}  V={int(r['volume'])}")
    except Exception as e:
        print(f"  ❌ 订阅/K线异常: {e}")

    # ── 3. 尝试带扩展时段的 snapshot(如果 API 支持) ─────────────────
    print("\n【3】尝试 get_rt_data (实时分时线):")
    try:
        ret_rt, rt = ctx.get_rt_data(ticker)
        if ret_rt == RET_OK and rt is not None and len(rt) > 0:
            # 只看最后 3 条
            print(f"  共 {len(rt)} 条 tick,最近 3 条:")
            for _, r in rt.tail(3).iterrows():
                cols_to_show = [c for c in ['time', 'data_status', 'price',
                                              'last_close', 'avg_price', 'volume']
                                if c in r.index]
                snippet = "  ".join(f"{c}={r[c]}" for c in cols_to_show)
                print(f"    {snippet}")
        else:
            print(f"  ⚠️ get_rt_data 无数据或失败: ret={ret_rt}")
    except Exception as e:
        print(f"  ⚠️ get_rt_data 不支持或异常: {e}")

    ctx.close()
    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["US.RKLZ", "US.RKLB"]
    for tk in tickers:
        diag(tk)
