# Leon QA 本地执行器：第二阶段

统一启停、`./leonqa doctor`、网页“运行诊断”及异常排查见 [第六阶段运维手册](README_QA_OPERATIONS.md)。以下保留底层执行器命令，日常使用优先从平台根目录的 `./leonqa` 进入。

本阶段将 `leon-qa-kit` 的固定资金划转套件接入平台后端，提供持久化任务、独立执行器和真实报告读取。本页保留第二阶段说明；已完成的第三阶段网页入口与操作流程见 [网页使用说明](README_QA_RUNNER_UI.md)。

## 运行结构

```text
登录用户 → 平台任务 API → MySQL 任务表 → 独立 Python worker
                                            ↓
                             本任务专属进程组 → Go 套件
                                            ↓
                       临时 MySQL + 本地合成服务 + 独立报告目录
                                            ↓
                         协议 / 退出码 / 断言 / 来源核对 → 任务结果
```

平台后端继续使用本机已有数据库。套件另建带任务标签的临时 MySQL，不向平台数据库写测试余额，不访问真实交易所、不需要交易所 API Key，也没有接入远程 CI。

## 启动与停止

先启动 Docker 和原有平台服务。当前本地入口为网页 `http://127.0.0.1:18170`、后端 `http://127.0.0.1:18171`；均为本机入口。

在终端执行：

```bash
cd /path/to/leon-qa/backend

# 首次登记，或更换工具包位置后执行。只能由本地操作者配置。
.venv/bin/python scripts/qa_runner.py configure \
  --project-root '/path/to/your-project

# 仅创建执行器自己使用的三张任务表，不重建平台原表。
.venv/bin/python scripts/qa_runner.py init

.venv/bin/python scripts/qa_runner.py start
.venv/bin/python scripts/qa_runner.py status
.venv/bin/python scripts/qa_runner.py stop
```

`start` 启动后台进程，关闭当前终端不会把 worker 变成网页后端的子任务。每个运行目录只允许一个 worker；本阶段串行领取任务。`stop` 会处理正在执行的任务及其资源后退出。不要用 `killall python`、全局 Docker 清理或删除整个 `.runtime` 来停止任务。

worker 会校验工具包协议 Schema 与固定套件登记。更新工具包、协议或登记路径后应停止并重新启动 worker。固定协议版本为 `1.0.0`，当前允许套件为 `funds-transfer-v1`，执行类型为 `regression` / `selftest`。

登记时固定本机 Docker Unix socket，执行和清理使用同一个地址；随后切换终端 Docker context 不会让任务跑到其他机器。更换 Docker socket 后需要重新 configure，再重启 worker。不接受 SSH/TCP 远程 Docker 地址。

## 提交和查询任务

API 前缀：`/api/v1/Ntesterc_qa_runner`。使用平台正常登录返回的 `Bearer` 令牌。`project_id` 是当前用户已加入的平台项目 ID；任务仅允许提交者本人访问，同时每次核对项目成员身份。

请求示例：

```http
POST /api/v1/Ntesterc_qa_runner/jobs
Authorization: Bearer <平台登录令牌>
Content-Type: application/json

{
  "project_id": 1,
  "project_key": "leon-qa-kit",
  "suite_id": "funds-transfer-v1",
  "run_kind": "regression",
  "request_key": "transfer_release_20261121_001",
  "timeout_seconds": 300
}
```

`project_id: 1` 只是格式示例，应使用自己的项目 ID。`request_key` 必须为 8–80 位小写字母、数字、下划线或连字符，以字母或数字开头。同一项目、同一用户、同一键与相同参数返回原任务（HTTP 200）；换参数复用原键返回 409。首次创建返回 202。要复测请换键，不覆盖历史任务。

任务 API 不接受 shell 命令、项目路径、环境变量、目标 URL、输出目录或测试过滤器；未知字段返回 422。超时允许 1–900 秒，针对开始执行后的耗时，排队时间不计入；终止与资源清理还需要少量时间。

| 操作 | 方法与路径（相对于前缀） | 说明 |
|---|---|---|
| 套件与执行器状态 | `GET /catalog` | 登记内容、在线/离线/阻塞情况 |
| 提交任务 | `POST /jobs` | 持久化后立即返回，不阻塞到测试结束 |
| 自己的历史记录 | `GET /jobs?project_id=1&limit=50` | 最近任务，最多 100 条 |
| 任务详情 | `GET /jobs/{id}` | 生命周期、测试结论、清理状态、错误 |
| 取消 | `POST /jobs/{id}/cancel` | 排队直接取消；执行中先进入 cancelling |
| 状态事件 | `GET /jobs/{id}/events?after=0&limit=100` | 使用 `next_after` 继续读取，最多 200 条 |
| 执行日志 | `GET /jobs/{id}/logs?stream=stderr&offset=0&limit=65536` | 使用字节 `next_offset`，允许 stderr/stdout/supervisor |
| 已导入报告 | `GET /jobs/{id}/report` | 完整报告未就绪时返回 409 |
| 下载证据 | `GET /jobs/{id}/artifacts/{relative}` | 仅报告清单内文件；禁止越界和软链接 |

## 怎样判断执行结果

生命周期与测试结论是两个字段，不能只看任务是否结束。

| 字段 | 取值 | 含义 |
|---|---|---|
| `status` | queued / running / cancelling | 排队、执行、正在取消 |
| `status` | completed | 进程执行和结果处理已结束，不等于业务通过 |
| `status` | cancelled / timed_out / interrupted | 已取消、超时或中断，不计通过 |
| `result_status` | PASS / FAIL / ENV_ERROR / NO_TESTS | 正常完成任务的测试结论 |
| `result_status` | null | 取消、中断等情况没有可采信结论 |
| `cleanup_status` | clean / not_required / failed 等 | 本次任务资源清理状态 |

常规回归须完成固定的 14 个业务用例，核对完整报告、实际退出码、stdout 与文件的一致性、用例身份、断言值、源文件前后摘要。缺少必跑项、断言自相矛盾、来源变化或非法产物不能判为 PASS。

`selftest` 故意注入少记一最小单位的缺陷。自检的 PASS 表示余额、资金守恒、对账三项精确断言成功检出该缺陷；内部 `gate_result.status` 应当是 FAIL。这不等于业务回归通过，自检与常规回归保留独立运行身份。

## 取消、恢复与资源边界

- 排队任务取消不启动进程；执行中取消会核对专属 supervisor 的命令、随机标记、进程创建时间和进程组，再终止该组。
- 临时容器必须同时匹配 owner、run_id、job_token 三个标签才会删除，删除前再次核对。不使用 `docker prune`。
- worker 重启时查找上次 running/cancelling 及清理失败记录，处理本次遗留资源，标为 interrupted 或 cancelled；不自动重跑，不把残留报告判为通过。
- worker 持久化 PID 前发生中断时，还可按该任务的 supervisor 标记发现进程。发现身份不明或清理失败会阻塞领取新任务，保留错误和证据，供本地排查。
- 后端重启不结束独立 worker。任务、事件和已导入报告保存在数据库，日志和原始产物保存在每个运行目录。

默认目录：`/path/to/leon-qa/.runtime/qa-runner`。`projects.json` 是操作者登记；`worker.log` 是 worker 日志；`runs/job_<id>/` 保存该次 launch、stdout、stderr、退出、清理记录及 `report/`。本地控制文件为仅当前用户可读写权限；不要把运行目录或登录令牌提交到 Git。

本阶段不自动删除历史报告，也不实现多机分布式调度、操作系统开机自启或远程托管。Docker/数据库异常导致阻塞时，先查 `status`、`worker.log` 与对应 `cleanup.json`，确认资源归属并处理故障后再重启，不直接把状态改成通过。

## 验收与下一阶段

第二阶段验收索引：`.runtime/phase2-acceptance-path.txt`。它指向实际 HTTP 检查、原始日志、各任务报告及隔离的故障注入副本。验收账号使用合成用户；验证了原生 JWT 与成员隔离，没有声称验证浏览器登录流程。故障注入只修改隔离副本，交付时恢复到原工具包登记。

2026-11-21 本地验收：新增执行器单元测试 27 项、原有 Web3 回归 23 项通过；Go 常规回归产生 80 个通过事件（含子测试、14 个必跑业务用例）。集成验收覆盖四类测试结论、取消、超时、硬中断恢复、PID 未写回恢复、后端重启持久化、幂等、身份隔离、日志和产物读取，逐项结果见验收 JSON。最终导入器再次核对了真实 PASS / 自检 / FAIL / ENV_ERROR / NO_TESTS 五份历史报告。源码快照和选择性回退清单由 `.runtime/phase2-delivery-path.txt` 定位。

第三阶段接入网页：套件选择、提交/取消、状态与历史列表、日志、业务断言与证据下载，全部调用以上 API，不在前端另写业务通过规则。现货、合约、DEX 的新套件及真实测试环境适配仍按后续业务阶段评审。
