"""
MagicQuant — Futu API 压力测试 v0.1
Dare to dream. Data to win.

目的：找到 Futu QuoteContext 在你本地的实际频率上限，
     为 Focus 盯盘模式的频率设计提供数据依据。

测试场景：
  阶段 1：单票不同频率(1/5/10/15/30秒)，每个频率跑 20 次
  阶段 2：多票并发(1/2/3/4 只票同时)，频率 5 秒跑 10 次
  阶段 3：K 线拉取测试(1/5 分钟)，不同频率

输出:
  - 每个场景的平均响应时间
  - 失败率(限流/超时/报错)
  - 推荐的安全盯盘频率

跑法:
  cd C:\\MagicQuant
  python -m core.futu_stress_test
"""

import time
import statistics
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from moomoo import OpenQuoteContext, RET_OK, KLType, AuType, SubType
except ImportError:
    from futu import OpenQuoteContext, RET_OK, KLType, AuType, SubType

from config.settings import FUTU_HOST, FUTU_PORT


# ── 测试标的 ──────────────────────────────────────────────────
TEST_TICKERS = ["US.RKLB", "US.TSLA", "US.SOXL", "US.RKLZ"]


def log(msg, level="INFO"):
    """带时间戳的日志"""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    icon = {"INFO": "📋", "OK": "✅", "WARN": "⚠️", "ERR": "❌", "FAIL": "🚨"}.get(level, "·")
    print(f"  [{ts}] {icon} {msg}")


def stage_1_single_ticker(ctx):
    """阶段 1: 单票不同频率"""
    print("\n" + "="*60)
    log("阶段 1:单票频率测试", "INFO")
    print("="*60)

    ticker = TEST_TICKERS[0]
    frequencies = [1, 2, 3, 5, 10, 15, 30]   # 秒
    results = {}

    for freq in frequencies:
        log(f"测试频率 {freq}秒 / 次,共 20 次", "INFO")
        latencies = []
        errors = 0
        t_start = time.time()

        for i in range(20):
            t0 = time.time()
            try:
                ret, snap = ctx.get_market_snapshot([ticker])
                elapsed = (time.time() - t0) * 1000
                if ret == RET_OK:
                    latencies.append(elapsed)
                else:
                    errors += 1
                    log(f"  第 {i+1} 次失败: {snap}", "WARN")
            except Exception as e:
                errors += 1
                log(f"  第 {i+1} 次异常: {e}", "ERR")

            # 等到下一个周期
            sleep_for = freq - (time.time() - t0)
            if sleep_for > 0:
                time.sleep(sleep_for)

        total_time = time.time() - t_start
        if latencies:
            avg = statistics.mean(latencies)
            p95 = sorted(latencies)[int(len(latencies)*0.95)] if len(latencies) >= 5 else max(latencies)
            results[freq] = {
                "avg_ms": avg,
                "p95_ms": p95,
                "success": len(latencies),
                "errors": errors,
                "total_s": total_time,
            }
            log(f"  ✓ 频率 {freq}秒: avg={avg:.0f}ms  p95={p95:.0f}ms  "
                f"成功 {len(latencies)}/20  失败 {errors}", "OK" if errors == 0 else "WARN")
        else:
            results[freq] = None
            log(f"  ✗ 频率 {freq}秒: 全部失败", "ERR")

        # 频率之间休息 2 秒,避免连续压测
        time.sleep(2)

    return results


def stage_2_parallel(ctx):
    """阶段 2: 多票并发(5 秒频率)"""
    print("\n" + "="*60)
    log("阶段 2:多票并发测试(5秒 / 次)", "INFO")
    print("="*60)

    results = {}
    for n_tickers in [1, 2, 3, 4]:
        tks = TEST_TICKERS[:n_tickers]
        log(f"并发 {n_tickers} 只票: {tks}", "INFO")
        latencies = []
        errors = 0

        for i in range(10):
            t0 = time.time()
            try:
                # 并发拉取
                with ThreadPoolExecutor(max_workers=n_tickers) as pool:
                    futs = [pool.submit(ctx.get_market_snapshot, [tk]) for tk in tks]
                    success = 0
                    for fut in as_completed(futs, timeout=10):
                        try:
                            ret, _ = fut.result()
                            if ret == RET_OK:
                                success += 1
                        except:
                            pass

                elapsed = (time.time() - t0) * 1000
                if success == n_tickers:
                    latencies.append(elapsed)
                else:
                    errors += 1
                    log(f"  第 {i+1} 次部分失败: {success}/{n_tickers}", "WARN")
            except Exception as e:
                errors += 1
                log(f"  第 {i+1} 次异常: {e}", "ERR")

            sleep_for = 5 - (time.time() - t0)
            if sleep_for > 0:
                time.sleep(sleep_for)

        if latencies:
            avg = statistics.mean(latencies)
            results[n_tickers] = {
                "avg_ms": avg,
                "success": len(latencies),
                "errors": errors,
            }
            log(f"  ✓ 并发 {n_tickers} 只: avg={avg:.0f}ms  成功 {len(latencies)}/10", 
                "OK" if errors == 0 else "WARN")
        else:
            results[n_tickers] = None
            log(f"  ✗ 并发 {n_tickers} 只: 全部失败", "ERR")

        time.sleep(2)

    return results


def stage_3_kline(ctx):
    """阶段 3: K 线拉取测试"""
    print("\n" + "="*60)
    log("阶段 3:K线拉取测试", "INFO")
    print("="*60)

    ticker = TEST_TICKERS[0]

    # 先订阅
    try:
        ctx.subscribe([ticker], [SubType.K_1M, SubType.K_5M], subscribe_push=False)
        log(f"已订阅 {ticker} 1M/5M K线", "OK")
    except Exception as e:
        log(f"订阅失败: {e}", "ERR")

    results = {}
    for kl_name, kl_type, kl_num in [
        ("1分钟", KLType.K_1M, 30),
        ("5分钟", KLType.K_5M, 30),
    ]:
        log(f"测试 {kl_name} K线 拉取 10 次", "INFO")
        latencies = []
        errors = 0

        for i in range(10):
            t0 = time.time()
            try:
                ret, kl = ctx.get_cur_kline(ticker, kl_num, kl_type, AuType.QFQ)
                elapsed = (time.time() - t0) * 1000
                if ret == RET_OK:
                    latencies.append(elapsed)
                else:
                    errors += 1
                    log(f"  第 {i+1} 次失败: {kl}", "WARN")
            except Exception as e:
                errors += 1
                log(f"  第 {i+1} 次异常: {e}", "ERR")

            time.sleep(3)

        if latencies:
            avg = statistics.mean(latencies)
            results[kl_name] = {"avg_ms": avg, "success": len(latencies), "errors": errors}
            log(f"  ✓ {kl_name}: avg={avg:.0f}ms  成功 {len(latencies)}/10",
                "OK" if errors == 0 else "WARN")
        else:
            results[kl_name] = None

    return results


def summarize(r1, r2, r3):
    """给出推荐配置"""
    print("\n" + "="*60)
    log("📊 测试汇总与推荐", "INFO")
    print("="*60)

    # 找出单票成功率 100% 的最快频率
    safe_freq = None
    for freq in sorted(r1.keys()):
        res = r1.get(freq)
        if res and res["errors"] == 0 and res["avg_ms"] < 500:
            safe_freq = freq
            break

    print()
    print("━━━ 单票稳定性(阶段1)━━━")
    for freq, res in sorted(r1.items()):
        if res:
            status = "✅" if res["errors"] == 0 else f"⚠️ {res['errors']}失败"
            print(f"  {freq:3d} 秒 → avg {res['avg_ms']:.0f}ms  p95 {res['p95_ms']:.0f}ms  {status}")
        else:
            print(f"  {freq:3d} 秒 → ❌ 全失败")

    print("\n━━━ 并发能力(阶段2)━━━")
    for n, res in sorted(r2.items()):
        if res:
            status = "✅" if res["errors"] == 0 else f"⚠️ {res['errors']}失败"
            print(f"  {n} 只并发 → avg {res['avg_ms']:.0f}ms  {status}")
        else:
            print(f"  {n} 只并发 → ❌ 全失败")

    print("\n━━━ K线拉取(阶段3)━━━")
    for k, res in r3.items():
        if res:
            status = "✅" if res["errors"] == 0 else f"⚠️ {res['errors']}失败"
            print(f"  {k} K线 → avg {res['avg_ms']:.0f}ms  {status}")
        else:
            print(f"  {k} K线 → ❌ 全失败")

    print()
    print("━━━ 🎯 推荐 Focus 盯盘配置 ━━━")
    if safe_freq is not None and safe_freq <= 3:
        print(f"  ✅ 激进模式:单票 {safe_freq} 秒 / 次")
        print(f"     适合高活跃波段,多票建议放宽到 {safe_freq * 2} 秒")
    elif safe_freq is not None and safe_freq <= 10:
        print(f"  ✅ 平衡模式:单票 {safe_freq} 秒 / 次")
        print(f"     多票 3~4 只建议 {safe_freq * 2} 秒")
    else:
        print(f"  ⚠️ 保守模式:建议 15~30 秒 / 次")
        print(f"     Futu 本地性能有限,或网络不稳")

    print()
    print("建议配置写入 Focus 模式时参考:")
    print(f"  FOCUS_POLL_INTERVAL_SINGLE  = {safe_freq or 15}  # 单票秒数")
    print(f"  FOCUS_POLL_INTERVAL_MULTI   = {(safe_freq or 15) * 2}  # 多票秒数")
    print(f"  FOCUS_KLINE_FETCH_INTERVAL  = 60   # K 线拉取间隔(5分钟 K 不用每秒拉)")
    print("="*60)


def main():
    print("\n" + "="*60)
    print("  🧪 MagicQuant Futu API 压力测试")
    print("  约 3~5 分钟,请勿中断")
    print("="*60)

    log(f"连接 FutuOpenD {FUTU_HOST}:{FUTU_PORT}...", "INFO")
    try:
        ctx = OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
        log("连接成功", "OK")
    except Exception as e:
        log(f"连接失败: {e}", "FAIL")
        log("请确认 FutuOpenD 正在运行,然后重试", "INFO")
        return

    t_global = time.time()
    try:
        r1 = stage_1_single_ticker(ctx)
        r2 = stage_2_parallel(ctx)
        r3 = stage_3_kline(ctx)
        summarize(r1, r2, r3)
        log(f"总耗时 {time.time()-t_global:.1f} 秒", "OK")
    finally:
        ctx.close()
        log("测试完成,连接已关闭", "OK")


if __name__ == "__main__":
    main()
