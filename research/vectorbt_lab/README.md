# MagicQuant VectorBT Lab

VERSION : v0.2.0  
DEPENDS : Futu/Moomoo OpenAPI, pandas, pyarrow, vectorbt

隔离研究模块，只用于拉取 1m K 线和验证 `breakout_core` 模板。  
不修改 `core/focus/`，不接入 Telegram，不改变实盘 watchlist。

## 1. 拉取 60 个交易日 1m K 线

```powershell
python research\vectorbt_lab\fetch_1m_data.py --trading-days 60
```

默认标的：

```text
RKLB,LUNR,ASTS,IONQ
```

输出：

```text
research/vectorbt_lab/data/{SYMBOL}/1m/{SYMBOL}_1m.parquet
research/vectorbt_lab/data/manifest.json
```

统一 schema：

```text
timestamp, open, high, low, close, volume, symbol
```

`timestamp` 为 UTC。

## 2. 扫描候选股

```powershell
python research\vectorbt_lab\run_candidate_scan.py
```

v0.2 口径：

- RKLB train 段挑参数。
- 同一组 RKLB 参数横扫所有候选股 test 段。
- 入场按 next-bar open，不用信号 bar close。
- 单边滑点默认 `8 bps`。
- 输出 OOS 结果，不再用每只股票各自最优参数做主结论。

输出：

```text
research/vectorbt_lab/output/candidate_scan.csv
research/vectorbt_lab/output/candidate_summary.md
```

## 3. 研究边界

- 只研究 `RKLB / LUNR / ASTS / IONQ`
- 只实现一个模板：`breakout_core`
- 排名优先看 OOS 手续费后收益 `oos_pnl`
- 候选股只研究，不实盘
- 如果 RKLB OOS 没跑正，报告不得给出“谁最像 RKLB 且适合复制打法”的结论。
