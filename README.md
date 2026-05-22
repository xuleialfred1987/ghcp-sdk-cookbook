# GHCP SDK Cookbook

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![SDK](https://img.shields.io/badge/github--copilot--sdk-0.3.0-green.svg)](https://pypi.org/project/github-copilot-sdk/)
[![Status](https://img.shields.io/badge/status-Public%20Preview-orange.svg)](#)

一套**可直接运行**的 Jupyter notebook，系统讲解 **GitHub Copilot SDK (Python)** 的核心概念、事件模型、工具系统、权限层、BYOK provider 切换，以及如何把它作为 "harness" 嵌入到自己的产品里。

> SDK 状态：**Public Preview**，API 可能 breaking change。  
> 包名：`pip install github-copilot-sdk` （顶层模块 `copilot`）  
> Python ≥ 3.11；Copilot CLI 由 Python 包 bundled，无需单独装。

## Quickstart

```bash
# 1. clone
git clone https://github.com/xuleialfred1987/ghcp-sdk-cookbook.git
cd ghcp-sdk-cookbook

# 2. venv + 依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. 配置 BYOK（推荐）
cp .env.example .env
#   编辑 .env，填入 AZURE_OPENAI_ENDPOINT_GPT_5_4 / AZURE_OPENAI_API_KEY_GPT_5_4
#   或者 OPENAI_API_KEY / ANTHROPIC_API_KEY

# 4. 打开 notebook
jupyter lab   # 或在 VS Code 直接打开 .ipynb
```

从 [`01_sdk_quickstart.ipynb`](01_sdk_quickstart.ipynb) 顺着编号往下读即可。

---

## 1. SDK 心智模型

```
你的应用
  ↓ (in-process Python API)
copilot.CopilotClient   ──spawn──▶  copilot CLI (server 模式)
  ↓ create_session                       │
copilot.CopilotSession  ◀──JSON-RPC──────┘
  ↓ session.on(handler) / session.send(...)
事件流：assistant.message(.delta) · tool.execution* · session.idle · permission.* …
```

关键概念：

| 概念 | 作用 |
|---|---|
| `CopilotClient` | 启动/管理 CLI 子进程；多 session 复用 |
| `CopilotSession` | 一次会话，含历史、工具、权限 |
| `define_tool` / Pydantic | 注册自定义工具（自动 JSON Schema） |
| `on_permission_request` | 每次工具调用前裁决（approve/reject） |
| `system_message` (append/replace) | 注入系统提示 |
| `hooks` (pre/post tool, session.start…) | 生命周期钩子 |
| `infinite_sessions` | 自动 context 压缩 + workspace 目录 |
| `provider`（BYOK） | OpenAI / Azure OpenAI / Anthropic |
| streaming events | `assistant.message.delta` 流式输出 |
| skills / custom_agents / mcp_servers | 一等公民配置 |

---

## 2. Notebook 顺序

| # | 文件 | 主题 |
|---|---|---|
| 01 | `01_sdk_quickstart.ipynb` | 安装、首次跑通、async context manager、`session.idle` |
| 02 | `02_events_and_streaming.ipynb` | 事件订阅模式、delta vs final、async generator 封装 |
| 03 | `03_custom_tools.ipynb` | `@define_tool` + Pydantic、低阶 `Tool` API、`skip_permission` |
| 04 | `04_permissions_and_hooks.ipynb` | `on_permission_request`、`hooks`、`on_user_input_request` |
| 05 | `05_byok_and_providers.ipynb` | Azure OpenAI / OpenAI / Ollama BYOK，模型切换 |
| 07 | `07_builtin_tools.ipynb` | 内建工具发现 (`tools.list`)、`view` / `glob` / `rg` / `bash` / `apply_patch`、白名单/黑名单 |

每个 notebook 自包含：`pip install` → import → 跑一个最小例子 → 关键点列表。

📁 **`docs/` 文件夹** — 长期维护的参考文档（非教学型）：

| 文件 | 内容 |
|---|---|
| [`docs/builtin-tools.md`](docs/builtin-tools.md) | **15 个内建工具完整能力清单**：分类速查表 + 描述 + JSON Schema + 调用约定 |
| [`docs/session-persistence.md`](docs/session-persistence.md) | **Session 持久化与复用**：`~/.copilot/` 磁盘布局 + `session-store.db` schema + `resume_session` / `fork` / `infinite_sessions` / `config_dir` |
| `docs/_builtin_tools_raw.json` | SDK `tools.list` RPC 的原始 JSON 快照（可作 fixture / diff 对比用）|

---

## 3. 认证

按优先级：

1. `github_token=` 显式传入
2. 环境变量 `COPILOT_GITHUB_TOKEN` > `GH_TOKEN` > `GITHUB_TOKEN`
3. 已登录用户（`copilot` CLI `login` 后的 OAuth 凭证）
4. **BYOK** —— 通过 `provider=` 指定自己的 LLM 端点，**不需要 GitHub 鉴权**

> Notebook 中建议使用 BYOK + 本地 `.env`（指向 Azure OpenAI），
> 这样无需为每个开发者准备 Copilot 订阅。

---

## 4. SDK 实战发现（Lessons Learned）

> 这些是 notebook 调试过程中踩到的「文档与实际不一致」或「不显眼但很关键」的细节。
> SDK 版本：`github-copilot-sdk==0.3.0`（Public Preview，API 可能仍在变动）。

### 4.1 `session.send(...)` 返回的是 message ID，**不是**回复文本

```python
# ❌ 直觉式（错误）：以为能拿回模型文本
text = await session.send('Hello')     # text 实际是一个 UUID 字符串

# ✅ 正确：用高层 helper send_and_wait，发送 + 阻塞至 idle + 返回最终消息
response = await session.send_and_wait('Hello', timeout=60.0)
if response and hasattr(response.data, 'content'):
    print(response.data.content)        # 真正的 LLM 文本回复

# ✅ 也可订阅事件：on AssistantMessageData / on SessionIdleData
```

- `session.send` 只是把消息投递给 CLI（异步、解耦），返回的是消息流水 ID
- 真正的回复永远走事件流：`AssistantMessageData`（完整）/ `AssistantMessageDeltaData`（流式）

### 4.2 工具返回事件中 `text_result_for_llm` 已重命名为 `content`

- **入参侧**（自己写工具时）：`ToolResult(text_result_for_llm=...)` 仍是这个字段名
- **出参侧**（订阅 `ToolExecutionCompleteData` 事件时）：序列化后字段叫 `.content`

```python
case ToolExecutionCompleteData() as d:
    text = getattr(d.result, 'content', 'N/A') if d.result else 'N/A'  # ✅
    # 不要用 d.result.text_result_for_llm —— AttributeError
```

### 4.3 `on_permission_request` handler 签名是**两个**参数

```python
from copilot.session import PermissionRequestResult
from copilot.generated.session_events import PermissionRequestKind

def my_handler(request, invocation):           # ✅ 两个参数
    # request.kind ∈ {WRITE, READ, SHELL, MCP, URL, MEMORY, CUSTOM_TOOL, HOOK}
    # request.path / request.file_name        — 文件改动目标
    # request.full_command_text               — shell 完整命令文本
    # request.tool_name                       — 自定义工具时才有
    if request.kind == PermissionRequestKind.WRITE:
        return PermissionRequestResult(kind='approve-once')
    return PermissionRequestResult(kind='reject')
```

- `kind` 只接受 4 个字面量：`'approve-once'` / `'reject'` / `'user-not-available'` / `'no-result'`
- 返回 `dict({'kind': ...})` 不会工作，必须用 `PermissionRequestResult` 数据类
- 若 handler 抛异常或签名错误，CLI 会默认按 `USER_NOT_AVAILABLE` 处理 → **工具被拒**（看起来"莫名其妙地无响应"）

#### 🚦 Bypass / "Always allow" 怎么做

**⚠️ 协议有 ≠ Python SDK 有**：
- 底层 `PermissionDecisionKind` Enum 有 **5 个**值（含 `approve-for-session` / `approve-for-location`）
- 但 Python 包装层 `PermissionRequestResultKind` Literal **只暴露 4 个**（缺 session/location）

3 种实战方案：

| # | 方案 | 适用 |
|---|---|---|
| 1 | `on_permission_request=PermissionHandler.approve_all` | 整段 session 全放行，脚本/CI |
| 2 | **自维护 `set()` 缓存**（推荐）| `key=(kind, path)` 命中即静默 approve；首次问真人 |
| 3 | `return PermissionRequestResult(kind='approve-for-session')  # type: ignore` | hack，能跑但类型报红且未来可能 break |

方案 2 完整示例：
```python
approved_keys: set[tuple[str, str]] = set()

def cached_bypass(request, invocation):
    key = (request.kind.value, request.path or request.full_command_text or '*')
    if key in approved_keys:
        return PermissionRequestResult(kind='approve-once')   # silent
    # 首次问真人 (input / GUI / Slack 都行)，选了 session-wide 就加入缓存
    answer = input(f'⚠️  {key} — [y/n/s]? ').strip().lower()
    if answer == 's':
        approved_keys.add(key)
    return PermissionRequestResult(
        kind='approve-once' if answer in ('y', 's') else 'reject'
    )
```

跑通示例：见 [`07_builtin_tools.ipynb`](07_builtin_tools.ipynb) §4.5。

### 4.4 CLI 实际内建的 15 个工具（与文档常见示例不同）

通过 `client._rpc.tools.list(ToolsListRequest(model=...))` 实际拉到的清单：

| 类别 | 工具 |
|---|---|
| Shell | `bash`, `write_bash`, `read_bash`, `stop_bash`, `list_bash` |
| 文件 | `view`（读）, `apply_patch`（**唯一**的写/改/删，freeform 文本协议）|
| 搜索 | `rg`（ripgrep）, `glob` |
| 网络 | `web_fetch` |
| 编排 | `report_intent`, `skill`, `task`（子 agent）, `ask_user` |
| 元数据 | `fetch_copilot_cli_documentation` |

⚠️ **重要：没有 `read_file` / `write_file` / `edit_file`**——网上很多老示例引用的是早期工具名。
要读文件用 `view`，要写/改文件用 `apply_patch`，要执行 shell 用 `bash`（+ `read_bash`/`stop_bash` 控制）。

📖 **每个工具的完整描述 + JSON Schema** 见 [`docs/builtin-tools.md`](docs/builtin-tools.md)。

### 4.5 `apply_patch` 补丁格式（freeform 文本协议）

```text
*** Begin Patch
*** Add File: path/to/new.txt
+第一行
+第二行
*** End Patch
```

也支持 `*** Update File:` / `*** Delete File:` 操作头。LLM 会自主生成完整 patch；
我们只需在 `on_permission_request` 中按 `PermissionRequestKind.WRITE` 放行即可。

### 4.6 MCP 接入：**用原生 `mcp_servers={...}`**，不要手写 JSON-RPC 桥

```python
async with await client.create_session(
    mcp_servers={
        # 远程 HTTP/SSE
        'microsoft-learn': {
            'type': 'http',
            'url': 'https://learn.microsoft.com/api/mcp',
            'tools': ['*'],       # 或白名单 ['search_docs', ...]
        },
        # 本地 stdio
        'fs': {
            'type': 'stdio',
            'command': 'npx',
            'args': ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'],
            'tools': ['*'],
        },
    },
    ...,
) as session:
    ...
```

CLI 会自动拉起 stdio 进程 / 连接 HTTP 端点，完成 `tools/list` 发现与 `tools/call`
路由。**完全不用**自己写 `MockMCPService` + JSON-RPC 转发。

### 4.7 内建工具的白名单/黑名单不影响**自定义**工具

`available_tools=[...]` / `excluded_tools=[...]` 仅作用于 CLI 内建工具集合。
通过 `tools=[...]` 注册的自定义工具始终对 LLM 可见，不受这两个参数过滤。
要禁用某个自定义工具，只需从 `tools=[...]` 中移除即可。

### 4.8 覆写内建工具必须显式 opt-in

```python
@define_tool(
    name='view',                           # 与内建工具同名
    overrides_built_in_tool=True,          # ✨ 必须显式声明
)
async def custom_view(params): ...
```

若忘写 `overrides_built_in_tool=True`，SDK 会因命名冲突直接抛错而非"静默替换"，这是有意的安全设计。

### 4.9 `skip_permission=True` 真的会绕过 `on_permission_request`

可用「故意 deny_all 的 handler + 工具仍执行成功」来验证这个开关：

```python
@define_tool(description='read-only', skip_permission=True)
async def safe_lookup(params): ...

async def deny_all(req, inv):
    return PermissionRequestResult(kind='reject')

# 用 deny_all 作为 handler，safe_lookup 仍能成功执行
```

适合只读 / 安全工具，提升交互体验；危险工具切勿设置。

### 4.10 Declaration-only 工具（`handler=None`）

适合慢工具 / 跨进程 / 人在回路场景。订阅 `ExternalToolRequestedData` 事件
→ 异步执行 → 用 `session.rpc.tools.handle_pending_tool_call(...)` 回填结果。
完整可运行示例见 `03_custom_tools.ipynb` 第 6 节。

### 4.11 `client.list_models()` 在某些模型缺 `billing.multiplier` 时整批崩

SDK 0.3.0 `ModelBilling.from_dict()` 要求 `multiplier` 字段必填，但 GitHub Copilot
返回的 `models.list` 里某些新模型（如 `gpt-5.5`、`claude-opus-4.7-1m-internal`）
不带该字段 → 整个 list 调用抛 `ValueError`。

解决：跳过 SDK 包装，直接走底层 RPC：
```python
async with CopilotClient() as client:
    raw = await client._rpc._client.request('models.list', {})
    for m in raw['models']:
        print(m['id'], m['name'])
```
跑通示例：见 `05_byok_and_providers.ipynb` §6。

### 4.12 BYOK Azure：`azure.api_version` 可省（但仍建议显式）

文档强调必须设 `azure={'api_version': '...'}`，但 SDK 0.3.0 实测：**漏写也能跑通**
（内部用默认 api_version）。仍建议显式声明，避免 SDK 默认值变化导致行为漂移。

跑通示例：见 `05_byok_and_providers.ipynb` §6.1 故意配错对照。

### 4.13 `CopilotSession` 公共 API 远不止 `send` 一个

`dir(CopilotSession)` 里这几个常被忽略但很有用：

| 方法/属性 | 用途 |
|---|---|
| `session.set_model(model, reasoning_effort=...)` | 中途换 model，history 保留（无须 destroy+recreate）|
| `session.get_messages()` | 读 session history（list of dict）|
| `session.abort()` | 优雅取消当前回合 |
| `session.workspace_path` | 当前 session 的 working directory |
| `session.log()` / `session.ui` / `session.capabilities` | 推日志、UI elicitation、能力位 |
| `client.resume_session(session_id, ...)` | 复用 `session_id` 续聊 |

跳通示例：见 `05_byok_and_providers.ipynb` §5.0（单 session `set_model` + `get_messages`）。

### 4.14 `create_session` 完整参数清单（30 个）

SDK 0.3.0 的 `CopilotClient.create_session` 实际暴露达 **30 个参数**：

```
on_permission_request  model  session_id  client_name  reasoning_effort
tools  system_message  available_tools  excluded_tools
on_user_input_request  hooks  working_directory  provider  model_capabilities
streaming  include_sub_agent_streaming_events
mcp_servers  custom_agents  default_agent  agent
config_dir  enable_config_discovery
skill_directories  disabled_skills
infinite_sessions  on_event  commands
on_elicitation_request  create_session_fs_handler  github_token
```

容易被忽略却很重要的：
- **`custom_agents` + `agent`** — 多 agent 编排
- **`system_message`** — 3 种模式（append/replace/customize + SYSTEM_PROMPT_SECTIONS）
- **`infinite_sessions`** — 自动 context 压缩（默认开），高级 worker 可以 `{'enabled': False}` 关掉手动管
- **`commands`** — TUI slash 命令
- **`reasoning_effort`** — GPT-5.x / Claude Opus 4.7 等推理模型的 effort level
- **`on_elicitation_request`** — 表单式 UI 弹窗（比 `on_user_input_request` 更结构化）

完整签名查询：
```python
import inspect; from copilot import CopilotClient
print(inspect.signature(CopilotClient.create_session))
```

### 4.15 Session **完全持久化到磁盘**，`resume_session` 可跨进程续聊

默认情况下（`infinite_sessions.enabled=True`，开箱即开）每个 session 全量落盘到 `~/.copilot/`：

```
~/.copilot/
├── session-store.db                  ← SQLite 索引（sessions / turns / checkpoints / session_files / session_refs）
├── session-state/<session-uuid>/
│   ├── events.jsonl                  ⭐ 完整事件流（append-only）
│   ├── workspace.yaml                ← 元数据（id / cwd / git_root / branch / summary）
│   ├── checkpoints/                  ← 自动 compaction 快照
│   ├── files/    research/    vscode.metadata.json
├── config.json / settings.json / permissions-config.json
└── logs/  ide/  pkg/  skills/
```

**复用方式**：

```python
# 第 1 次
async with await client.create_session(...) as s:
    await s.send_and_wait('我叫张三')
    my_id = s.session_id           # ← 记下

# 进程重启后
async with await client.resume_session(
    my_id,
    on_permission_request=..., provider=...,  # provider 不会自动恢复，必须重传
    # model='claude-opus-4.7',                # 可换 model
    # disable_resume=True,                    # 跳过 session.resume 事件
) as s:
    r = await s.send_and_wait('我叫啥？')      # → 你叫张三
```

关键 API：

| API | 用途 |
|---|---|
| `client.resume_session(session_id, **ResumeSessionConfig)` | 最常用：复活 session |
| `client._rpc.sessions.fork(SessionsForkRequest(...))` | 从已有 session 派生分支 |
| `create_session(session_id='my-id', ...)` | 自定义 id 创建新 session（不复活） |
| `config_dir='/custom/path'` | 替代 `~/.copilot/`（多租户隔离 / 容器持久化） |
| `infinite_sessions={'enabled': False}` | **关掉持久化**（不写盘、不可 resume，适合一次性脚本） |

命令行直接查 / 找 session（**无需 SDK**）：

```bash
sqlite3 ~/.copilot/session-store.db \
  "SELECT id, datetime(updated_at,'localtime'), substr(summary,1,40) \
   FROM sessions ORDER BY updated_at DESC LIMIT 20;"

jq -r .type ~/.copilot/session-state/<uuid>/events.jsonl | sort | uniq -c
```

陷阱：
- `session_id` 在 `config_dir` 下是**全局命名空间**——多进程 / 多 worker 共享 sqlite + state，能看到同一份历史
- `cwd` 在 `session.start` 事件里定死，resume 时改 `working_directory` 只影响后续工具调用
- BYOK `provider` 不会从磁盘恢复 API key，每次 resume 都必须重传
- `infinite_sessions={'enabled': False}` 的 session **不可 resume**（根本没写盘）
- `events.jsonl` 含完整 prompt + 工具输出，注意密钥泄漏 / 归档加密
- **`events.jsonl` 才是真相之源**：SQLite `session-store.db` 是**延迟同步**的索引，刚创建的 session 查 `sessions` 表可能返回 `None`；resume / list 请以磁盘目录为准
- **`session.get_messages()` 返回 `list[SessionEvent]`**（**不是** `list[dict]`）：访问用 `ev.type` / `ev.data.content`，不是 `m['role']`；包含 `SESSION_START` / `SYSTEM_MESSAGE` / `USER_MESSAGE` / `ASSISTANT_MESSAGE` / `SESSION_SHUTDOWN` / `SESSION_RESUME` 等完整事件流

跨进程 resume 跑通示例（事实验证）：见 `05_byok_and_providers.ipynb` §5.5。完整说明（disk layout / SQLite schema / fork / 跨机器迁移 / 清理）见 [`docs/session-persistence.md`](docs/session-persistence.md)。

