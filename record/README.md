# 行情采集清单

- `hedge-markets.json`：公开市场 API 已确认的同名有效市场组合，作为采集启动清单。当前6个标的、11组配对；挂牌状态不等于套利收益或合约经济条款完全相同。
- `hedge-candidates.json`：OAI/OPENAI、ANTH/ANTHROPIC、TCNT/TENCENT 等异名候选，以及下架、未匹配标的。合约单位和规则尚待核对，不由此启动器采集。

推荐使用单进程入口。它读取列表中 `collection_enabled: true` 的配对，在一个异步事件循环中运行多个只读引擎，每组仍独立追加原来的CSV：

```sh
.venv/bin/python tools/collect.py --list record/hedge-markets.json --check
.venv/bin/python tools/collect.py --list record/hedge-markets.json
```

`--check`只验证配置，不联网、不启动采集；不加此选项即前台运行。列表沿用 `hedge-markets.json` 的 `schema_version: 1` 和 `pairs` 格式，至少需要每组的 `symbol`、`entropy_symbol`、`hedge_symbol`、`hedge_venue`、`config`、`csv`、`collection_enabled`；其中路径相对项目根目录。也可用 `--list` 传入另一份同格式JSON。修改列表后需要重启，停止时发送 SIGTERM 或按 Ctrl-C，程序会收尾并写出当前分钟的数据。

后台运行可使用：

```sh
nohup .venv/bin/python tools/collect.py --list record/hedge-markets.json >> logs/collector.log 2>&1 &
```

新入口只采集公共行情，不加载 `.env`，启动时清除交易凭据环境变量，所有引擎固定 `record_only=True`。日志含配对标识；某组初始化失败会独立重试，不中断其他组。所有配对锁在启动时一起获取，任一冲突则整个新进程退出，防止两个采集器写同一个CSV。切换进程时应先正常停止旧采集器，等下一分钟再启动，以免同一CSV出现两行相同的分钟时间戳。

单进程减少解释器的重复内存，仍保留每组的行情连接，不合并同一标的的订阅。整个进程退出会影响全部组，目前没有自动重启服务。

旧的每组一进程启动器仍可使用，和新入口共用配对锁。验证配置、输出路径与旧进程：

```sh
.venv/bin/python tools/start_recorders.py
```

启动缺失的采集进程（重复执行会跳过已运行组合）：

```sh
.venv/bin/python tools/start_recorders.py --start
```

旧启动器固定使用 `--record-only --env-file /dev/null --no-dashboard`，并移除传递给进程的交易凭据环境变量。每组CSV、运行日志、PID和锁文件按交易场所与标的区分，写入 `logs/`；已有分钟数据追加保留。完整分钟通常在下一分钟切换时落盘。

本次没有增加定时任务或开机服务。机器重启、采集器退出后可重新运行启动命令。新增清单前应先刷新公开市场状态，并核对标的、配置与唯一CSV路径。
