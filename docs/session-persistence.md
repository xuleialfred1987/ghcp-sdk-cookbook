# GitHub Copilot SDK — Session 持久化与复用（Session Persistence & Resume）

> **抓取版本**：`github-copilot-sdk==0.3.0`（Public Preview）
> **数据来源**：源码 `copilot/session.py` 中 `SessionConfig` / `ResumeSessionConfig` / `InfiniteSessionConfig` + `~/.copilot/` 真实磁盘 + `session-store.db` SQLite schema。
> **配套 notebook**：[`05_byok_and_providers.ipynb`](../05_byok_and_providers.ipynb) §5.5 resume 实战 demo（计划）

---

## 1. 磁盘存储位置

SDK / CLI 会把每个 session 的**完整事件流 + 元数据 + 文件 + 检查点**写到本地，**默认根目录是 `~/.copilot/`**（可用 `config_dir=` 覆写）。

```
~/.copilot/
├── session-store.db                  ← SQLite 总索引（session 列表 / turns / checkpoints / refs）
├── session-state/
│   └── <session-uuid>/               ← 每个 session 一个目录
│       ├── events.jsonl              ⭐ 完整事件日志（append-only JSONL，每条 prompt/tool_call/response）
│       ├── workspace.yaml            ← 元数据（id / cwd / git_root / branch / summary / 时间戳）
│       ├── checkpoints/              ← 自动 compaction 时的快照
│       ├── files/                    ← 该 session 触碰过的文件副本
│       ├── research/                 ← agent 研究产物
│       └── vscode.metadata.json      ← VS Code 集成元数据
├── config.json                       ← 全局配置
├── settings.json                     ← 用户设置
├── permissions-config.json           ← 权限默认值
├── command-history-state.json        ← TUI slash 命令历史
├── logs/                             ← CLI 日志
├── ide/                              ← IDE 桥接数据
├── pkg/                              ← 内置 Copilot CLI 二进制
└── skills/                           ← 全局可用 skill
```

> **`events.jsonl` 是真相之源**：`session.get_messages()` / 重连后的 history 全部从这里反推。一条事件示例（截取）：
>
> ```json
> {"type":"session.start","data":{"sessionId":"d9d2aa76-...","copilotVersion":"1.0.36-0",
>  "selectedModel":"gpt-5.4","context":{"cwd":"...","gitRoot":"...","branch":"main",
>  "headCommit":"aab50cf..."},"alreadyInUse":false,"remoteSteerable":false}, ...}
> {"type":"system.message","data":{"role":"system","content":"You are the GitHub Copilot CLI..."}, ...}
> ```
>
> `workspace.yaml` 示例（同一 session）：
>
> ```yaml
> id: d9d2aa76-023a-4c95-be7d-1218644a1fd3
> cwd: /Users/.../hosted_agent_foundry_ghcp_sdk
> git_root: /Users/.../codebase
> branch: main
> summary_count: 0
> created_at: 2026-05-20T09:23:10.514Z
> updated_at: 2026-05-20T09:23:11.064Z
> summary: 记住一个事实：我叫张三，今年 28 岁。请用一句话确认你已经记住。
> ```

---

## 2. SQLite 索引 `session-store.db`

便于按 cwd / repo / 关键词 / 时间快速 list 出历史 session（事件本身仍在 `events.jsonl`）：

```sql
sessions       (id TEXT PK, cwd, repository, host_type, branch, summary,
                created_at, updated_at)
turns          (id, session_id FK, turn_index, user_message, assistant_response, timestamp,
                UNIQUE(session_id, turn_index))
checkpoints    (id, session_id FK, checkpoint_number, title, overview, history,
                work_done, technical_details, important_files, next_steps, created_at,
                UNIQUE(session_id, checkpoint_number))
session_files  (id, session_id FK, file_path, tool_name, turn_index, first_seen_at,
                UNIQUE(session_id, file_path))
session_refs   (id, session_id FK, ref_type, ...)
schema_version (version INTEGER)
```

### 直接查（无需 SDK）

```bash
# 最近 20 个 session
sqlite3 ~/.copilot/session-store.db \
  "SELECT id, datetime(updated_at,'localtime'), substr(summary,1,40)
   FROM sessions ORDER BY updated_at DESC LIMIT 20;"

# 跟某项目相关的 session
sqlite3 ~/.copilot/session-store.db \
  "SELECT id, summary FROM sessions WHERE cwd LIKE '%cowork_worker%';"

# 看某 session 的事件类型分布
jq -r .type ~/.copilot/session-state/<uuid>/events.jsonl | sort | uniq -c | sort -rn

# 看某 session 改过哪些文件
sqlite3 ~/.copilot/session-store.db \
  "SELECT file_path, tool_name FROM session_files WHERE session_id='<uuid>';"
```

---

## 3. 复用 session 的 4 种姿势

| # | 方法 | 用途 | history 是否回放 |
|---|---|---|---|
| 1 | `client.resume_session(session_id, ...)` | **最常用**：加载已有 session，完整 context 回到 LLM | ✅ |
| 2 | `create_session(session_id='my-id', ...)` | 创建新 session 但自定 id（外部追踪 / 续传） | ❌（是新 session） |
| 3 | `client._rpc.sessions.fork(...)` | 从已有 session 派生分支（"如果当时换个回答"） | ✅ 到分叉点 |
| 4 | `resume_session(..., disable_resume=True)` | 重连但**不触发** `session.resume` 事件 / 相关 hook | ✅ |

### 3.1 `client.resume_session(session_id, **ResumeSessionConfig)`

第一次跑下来记下 id：

```python
async with CopilotClient() as client:
    async with await client.create_session(
        on_permission_request=PermissionHandler.approve_all,
        model='gpt-5.4', provider=azure_provider,
    ) as session:
        await session.send_and_wait('我叫张三')
        my_id = session.session_id           # ← 记下来
```

任意时刻（包括进程重启之后）：

```python
async with CopilotClient() as client:
    async with await client.resume_session(
        my_id,
        on_permission_request=PermissionHandler.approve_all,
        provider=azure_provider,
        # 也可以在 resume 时换 model：
        # model='claude-opus-4.7',
    ) as session:
        r = await session.send_and_wait('我叫什么名字？')
        # → 你叫张三
```

### 3.2 `ResumeSessionConfig` 关键字段（与 `SessionConfig` 大致同集合，**多了** `disable_resume`）

```
client_name  model  reasoning_effort  tools  system_message
available_tools  excluded_tools  provider
on_permission_request  on_user_input_request  on_elicitation_request
hooks  working_directory  config_dir
streaming  include_sub_agent_streaming_events
mcp_servers  custom_agents  default_agent  agent
skill_directories  disabled_skills
infinite_sessions  on_event  commands  create_session_fs_handler
disable_resume                        ← ⭐ 仅 resume 时存在
```

注意 **`session_id`** 不在 `ResumeSessionConfig` 里，因为它是 `resume_session` 的位置参数。

### 3.3 `disable_resume=True` 的语义

- 默认 resume → 触发 `session.resume` 事件 + 任何 `on_session_resume` hook
- `disable_resume=True` → **纯重连**，跳过 resume 通知；适合"短暂断连后无感重连"或自动化重试

### 3.4 fork 一个 session

```python
from copilot.generated.session_rpc import SessionsForkRequest

async with CopilotClient() as client:
    resp = await client._rpc.sessions.fork(
        SessionsForkRequest(sourceSessionId=my_id, ...)
    )
    new_id = resp.sessionId
    # 之后 client.resume_session(new_id, ...) 继续聊
```

---

## 4. `infinite_sessions` —— 自动 compaction + 持久化总开关

定义在 `session.py` 的 `InfiniteSessionConfig`：

```python
class InfiniteSessionConfig(TypedDict, total=False):
    enabled: bool                              # 默认 True
    background_compaction_threshold: float     # 默认 0.80：context 用到 80% 后台压缩
    buffer_exhaustion_threshold: float         # 默认 0.95：用到 95% 阻塞等压缩完
```

### 启用（默认）

什么都不传就是 `enabled=True` + `0.80 / 0.95` —— 你看到的 `~/.copilot/session-state/` 目录就是它写的。

### 显式调参

```python
await client.create_session(
    ...,
    infinite_sessions={
        'enabled': True,
        'background_compaction_threshold': 0.70,   # 更早开始压缩，减少阻塞
        'buffer_exhaustion_threshold': 0.90,
    },
)
```

### 关闭

```python
await client.create_session(
    ...,
    infinite_sessions={'enabled': False},
)
```

关闭后：
- ❌ 不写 `events.jsonl` / `workspace.yaml` / `checkpoints/`
- ❌ session 不可 resume
- ✅ context 接近上限时**不再后台压缩**，需要你自行管理（适合短任务 / 一次性脚本）

---

## 5. 改变存储位置：`config_dir`

`SessionConfig` 和 `ResumeSessionConfig` 都接受 `config_dir: str`：

```python
await client.create_session(
    ...,
    config_dir='/var/lib/copilot-worker/tenant-42',   # 替代 ~/.copilot/
)
```

适合：
- **多租户隔离**：每个 tenant 一个目录，session id 不会撞、文件互不可见
- **容器化部署**：mount 持久化卷到固定路径，重启不丢 session
- **CI 隔离**：每个 job 独立目录，跑完即删

> ⚠️ `config_dir` 不仅放 session-state，**全局 config / 权限默认值 / logs / 已下载 CLI 二进制**都会被这个目录托管。

---

## 6. 跨进程 / 跨机器迁移

**单个 session**只需迁两份东西：

1. `~/.copilot/session-state/<uuid>/` 整个目录
2. `~/.copilot/session-store.db` 里 `sessions` / `turns` / `session_files` / `session_refs` 中所有 `session_id = <uuid>` 的行

```bash
# 源机：导出
SID=d9d2aa76-023a-4c95-be7d-1218644a1fd3
tar czf "$SID.tar.gz" -C ~/.copilot session-state/$SID
sqlite3 ~/.copilot/session-store.db <<SQL > "$SID.sql"
.mode insert
SELECT * FROM sessions WHERE id='$SID';
SELECT * FROM turns WHERE session_id='$SID';
SELECT * FROM session_files WHERE session_id='$SID';
SELECT * FROM session_refs WHERE session_id='$SID';
SELECT * FROM checkpoints WHERE session_id='$SID';
SQL

# 目标机：导入
tar xzf "$SID.tar.gz" -C ~/.copilot
sqlite3 ~/.copilot/session-store.db < "$SID.sql"
# 之后即可 client.resume_session(SID, ...)
```

---

## 7. 删除 / 清理

```bash
# 删单个 session
SID=...
rm -rf ~/.copilot/session-state/$SID
sqlite3 ~/.copilot/session-store.db <<SQL
DELETE FROM turns          WHERE session_id='$SID';
DELETE FROM session_files  WHERE session_id='$SID';
DELETE FROM session_refs   WHERE session_id='$SID';
DELETE FROM checkpoints    WHERE session_id='$SID';
DELETE FROM sessions       WHERE id='$SID';
SQL

# 清理 30 天前的所有 session
sqlite3 ~/.copilot/session-store.db \
  "SELECT id FROM sessions WHERE updated_at < datetime('now','-30 days');" \
| while read sid; do rm -rf "$HOME/.copilot/session-state/$sid"; done
```

---

## 8. 注意事项 & 陷阱

| 项 | 说明 |
|---|---|
| `session_id` 全局命名空间 | 同一 `config_dir` 下所有进程 / worker **共享** sqlite + session-state，可以多 client 看见同一份历史 |
| `cwd` 在创建时定死 | `events.jsonl` 第一条 `session.start` 记录的 `cwd` 是不可变事实；resume 时如果传不同 `working_directory`，仅影响后续工具调用，事件历史里仍是旧 cwd |
| `model` resume 时可改 | `ResumeSessionConfig.model` 与初次创建独立，history 不会重放也不需要原 model 可用 |
| BYOK `provider` 必须再传 | resume 不会从磁盘恢复 provider 配置（含 API key），每次都得显式给 |
| `infinite_sessions=False` 不可 resume | 因为根本没写盘 |
| 大 session 性能 | `events.jsonl` 可能上 MB；resume 会全量读，注意冷启动延迟 |
| 隐私 | `events.jsonl` 含完整 prompt / 工具输出，包括可能的密钥泄漏。生产环境注意权限（默认 `drw-------`）和归档加密 |
| **SQLite 是延迟索引** | `session-store.db` 中 `sessions` 表的写入不是事件发生同步的：**刚创建**的 session 查 `SELECT * FROM sessions WHERE id=?` 可能返回 `None`，但 `~/.copilot/session-state/<sid>/events.jsonl` 已经写了。**以磁盘目录为准**，sqlite 只适合做“老 session 批量查询 / 过滤” |
| **`get_messages()` 返 `SessionEvent` 而非 dict** | `await session.get_messages()` 返回 `list[SessionEvent]`，错误写法 `m['role']` / `m.get('role')` 都会 `AttributeError`。正确写法：`ev.type`（`SessionEventType.USER_MESSAGE` 等）、`ev.data.content`，只在需要“会话历史”时 filter `ev.type` 在 `USER_MESSAGE` / `ASSISTANT_MESSAGE` |

---

## 9. 一行版速查

| 想做什么 | 怎么做 |
|---|---|
| 看 session 存哪 | `ls ~/.copilot/session-state/<uuid>/` |
| 列所有 session | `sqlite3 ~/.copilot/session-store.db "SELECT id, summary FROM sessions;"` |
| 续聊 | `await client.resume_session(my_id, on_permission_request=..., provider=...)` |
| 续聊但不发 resume 事件 | 加 `disable_resume=True` |
| 在 resume 时换 model | 在 `resume_session(..., model='claude-opus-4.7')` 里传 |
| 换存储根目录 | `create_session(..., config_dir='/custom/path')` |
| 彻底关闭持久化 | `infinite_sessions={'enabled': False}` |
| fork 出新分支 | `await client._rpc.sessions.fork(SessionsForkRequest(sourceSessionId=my_id))` |
| 看 session 历史 | `evs = await session.get_messages()` —— 返 `list[SessionEvent]`，用 `ev.type` / `ev.data.content`，不是 dict |
| 中途换 model（同 session 内，无需 resume） | `await session.set_model('claude-opus-4.7')` |
| 只看真正的 user / assistant 轮次 | `[ev for ev in evs if ev.type.name in ('USER_MESSAGE','ASSISTANT_MESSAGE')]` |
