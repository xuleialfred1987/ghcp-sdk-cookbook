# GitHub Copilot SDK — 内建工具能力清单（Built-in Tools Reference）

> **抓取版本**：`github-copilot-sdk==0.3.0`（Public Preview）  
> **数据来源**：`client._rpc.tools.list(ToolsListRequest(model='gpt-5.4'))`  
> **快照文件**：`docs/_builtin_tools_raw.json`（可作为单测 fixture）  
> **统计**：CLI 共暴露 **15 个**内建工具

本文档枚举 GitHub Copilot CLI 自带的所有内建工具：分类速查表 + 完整描述 + JSON Schema。LLM 会自主选用这些工具，开发者通常只需：
- 在 `create_session(working_directory=...)` 设好工作目录
- 用 `on_permission_request` 控制权限
- 必要时用 `available_tools=[...]` / `excluded_tools=[...]` 精细管控

> 💡 想覆写某个工具的实现 → `@define_tool(name='view', overrides_built_in_tool=True)`；详见 `03_custom_tools.ipynb` 第 3 节。

---

## 速查表

| # | 工具名 | 类别 | 一句话用途 | 触发权限 (`kind`) |
|---|---|---|---|---|
| 1 | `bash` | Shell | 在交互式 Bash 会话中执行命令（sync/async） | `SHELL` |
| 2 | `write_bash` | Shell | 向运行中的 Bash 会话发送输入（含方向键） | `SHELL` |
| 3 | `read_bash` | Shell | 读取 Bash 会话累积的输出 | — |
| 4 | `stop_bash` | Shell | 终止 Bash 会话 | — |
| 5 | `list_bash` | Shell | 列出所有活动 Bash 会话 | — |
| 6 | `apply_patch` | 文件改 | **唯一**的写/改/删文件工具（freeform 文本补丁协议） | `WRITE` |
| 7 | `view` | 文件读 | 读文件 / 列目录 / 看图（base64） | `READ`（敏感目录） |
| 8 | `web_fetch` | 网络 | 抓取 URL，返回 markdown 或 HTML | `URL` |
| 9 | `report_intent` | 元 | 上报当前会话意图（在 UI 显示） | — |
| 10 | `fetch_copilot_cli_documentation` | 元 | 取回 Copilot CLI 自身文档 | — |
| 11 | `skill` | 编排 | 调用已注册的 skill | — |
| 12 | `ask_user` | 交互 | 反向问用户（触发 `on_user_input_request`） | — |
| 13 | `rg` | 搜索 | ripgrep 全文搜索 | — |
| 14 | `glob` | 搜索 | glob 文件名匹配 | — |
| 15 | `task` | 编排 | 启动子 agent（explore / task / general-purpose / code-review） | — |

> **重要：没有 `read_file` / `write_file` / `edit_file` / `str_replace_editor`。** 网上很多老示例引用的是早期工具名，已被 `view` + `apply_patch` 替代。

---

## 1. `bash` — 执行 Bash 命令

**用途**：在交互式 Bash 会话里跑命令；支持同步/异步两种模式。

**要点**：
- `command` **不需要** XML 转义
- 可直接跑 `python` / `node` / `go`；可用 `pip` / `npm` / `go` 装包
- `initial_wait` 取值 10–600 秒；若超时未结束，会返回**已有输出**并继续后台运行（用 `read_bash` 续读，`stop_bash` 终止）
- **sync 模式**：命令完成后会话销毁
- **async 模式**：必须设 `detach=true` 让进程在 agent 退出后存活（用于 server/daemon）；否则随 session 关闭被 kill

**参数**：
```json
{
  "type": "object",
  "required": ["command", "description"],
  "properties": {
    "command": "string — Bash 命令与参数",
    "description": "string — ≤100 字符的人类可读简述",
    "shellId": "string (可选) — 复用会话 ID；async 模式会返回自动生成的 shellId",
    "mode": "sync | async",
    "detach": "boolean — 仅 async 有效；true 表示完全后台、独立于 session",
    "initial_wait": "number — sync 模式下首次等待秒数（默认 10）"
  }
}
```

---

## 2. `write_bash` — 向 Bash 会话发送输入

**用途**：向运行中的 Bash / 交互式 CLI 发送按键输入。

**要点**：
- 支持文本与特殊键：`{up}` `{down}` `{left}` `{right}` `{enter}` `{backspace}`
- 配合 `bash` 的 async 模式使用，处理 TUI 程序的选项列表（用方向键 + `{enter}` 选中）
- `delay` 不得小于 10 秒

**参数**：
```json
{
  "required": ["shellId", "delay"],
  "properties": {
    "shellId": "string — 目标会话 ID",
    "input": "string — 要发送的输入文本（含特殊键）",
    "delay": "number — 等待输出的秒数"
  }
}
```

---

## 3. `read_bash` — 读取 Bash 会话输出

**用途**：从 `shellId` 标识的会话读取累积输出。

**要点**：
- 每次调用有 API 成本，`delay` 要合理
- 同一命令运行中可多次调用，返回**累积**输出
- 输出**不**包含 ANSI 控制码

**参数**：
```json
{
  "required": ["shellId", "delay"],
  "properties": {
    "shellId": "string",
    "delay": "number"
  }
}
```

---

## 4. `stop_bash` — 终止 Bash 会话

**用途**：终止整个 Bash 会话和进程（不仅是当前命令）。

**注意**：会话内定义的环境变量都会丢失；若复用相同 `shellId` 启新命令需重新定义。

**参数**：`{ "required": ["shellId"] }`

---

## 5. `list_bash` — 列出所有活动 Bash 会话

**用途**：发现现存的 `shellId`，便于 `read_bash` / `write_bash` / `stop_bash` 使用。

**返回字段**：`shellId`、`command`、`mode`、`PID`、`status`、是否有未读输出。

**参数**：`{}`（无参）

---

## 6. `apply_patch` — 创建/修改/删除文件 ⭐

> 这是 SDK 中**唯一**的写文件工具。**FREEFORM 工具**，参数不是 JSON 对象（注意 `"parameters": null`）。

**补丁格式**（受 Anthropic 启发的纯文本协议）：
```text
*** Begin Patch
*** Add File: path/to/new.txt
+第一行
+第二行
*** End Patch
```

**支持的操作头**：
| 操作头 | 行为 |
|---|---|
| `*** Add File: <path>` | 新建文件；后续 `+` 行为内容 |
| `*** Update File: <path>` | 修改现有文件；上下文行 + `+` 添加 / `-` 删除 |
| `*** Delete File: <path>` | 删除文件 |

**权限**：触发 `PermissionRequestKind.WRITE`；handler 中可读取 `request.path` / `request.file_name` 审计。

**完整示例**：见 [`07_builtin_tools.ipynb`](../07_builtin_tools.ipynb) 第 4.5 节。

---

## 7. `view` — 读文件 / 列目录 / 看图

**用途**：
- **文本文件** → 每行带 `N. ` 行号前缀（如 `1. `、`2. `）
- **图片文件** → 返回 base64 + MIME 类型（视觉模型可直接消费）
- **目录** → 列出 2 层深度的非隐藏文件

**关键限制**：
- `path` **必须是绝对路径**
- 文件 > **50KB** 会被截断，必须用 `view_range` 分段读
- `view_range=[start, end]` **从 1 开始**；`[start, -1]` 表示读到末尾
- 强制读大文件加 `forceReadLargeFiles=true`

**参数**：
```json
{
  "required": ["path"],
  "properties": {
    "path": "string — 绝对路径",
    "view_range": "[int, int] — 1-indexed 行号范围，end=-1 表示到结尾",
    "forceReadLargeFiles": "boolean — 跳过 50KB 截断"
  }
}
```

---

## 8. `web_fetch` — 抓取 URL

**用途**：安全地从 HTML 网页获取最新信息。

**参数**：
```json
{
  "required": ["url"],
  "properties": {
    "url": "string",
    "max_length": "number — 默认 5000，最大 20000",
    "start_index": "number — 分页起点，默认 0",
    "raw": "boolean — true=原始 HTML, false=简化 markdown（默认 false）"
  }
}
```

**分页策略**：内容被截断时用 `start_index = 上次 start_index + max_length` 继续读。

---

## 9. `report_intent` — 上报会话意图

**用途**：把当前任务高级别意图（≤4 词、动名词形式）显示到 UI。

**调用规则**：
- ❗ **不能单独调用**，必须与其它工具一起调用，且放在第一位
- 用户消息触发的第一轮 tool-call 必须包含
- 同一意图不要重复上报

**意图措辞**：
- ✅ 好：`"Exploring codebase"`, `"Creating parser tests"`, `"Fixing homepage CSS"`
- ❌ 太长/无动名词：`"I am going to read the codebase and understand it."`
- ❌ 太低层：`"Writing test1.js"`
- ❌ 太模糊：`"Updating logic"`

**参数**：`{ "required": ["intent"], "properties": { "intent": "string" } }`

---

## 10. `fetch_copilot_cli_documentation` — 获取 CLI 自身文档

**用途**：用户问「你能做什么」「怎么用 Copilot CLI」时，模型应主动调用。

**参数**：`{}`（无参）

---

## 11. `skill` — 调用 skill

**用途**：在主对话中执行已注册的 skill（项目级 / 用户级 / builtin）。

**调用约定**：
- 仅传 skill 名（不传参数）；具体逻辑在 skill 内部
- 可用 skill 列表通过 `<available_skills>` 系统消息注入，并通过 `skill_directories` / `disabled_skills` 控制
- 用户显式 by-name 请求未列出的 skill 也要照常调用

**参数**：`{ "required": ["skill"], "properties": { "skill": "string" } }`

---

## 12. `ask_user` — 反向询问用户 ⭐

**用途**：在执行过程中向用户提问（澄清需求 / 让用户做决策）。会触发 `on_user_input_request` 回调。

**调用规则**：每次**只问一个**问题，不要把多个问题合并。

**参数**：
```json
{
  "required": ["question"],
  "properties": {
    "question": "string — 单一问题",
    "choices": "string[] — （可选）多选项；建议尽量给",
    "allow_freeform": "boolean — 默认 true，允许自由文本"
  }
}
```

> 启用此工具的前提：`create_session(on_user_input_request=...)` 注册了 handler。

---

## 13. `rg` — ripgrep 全文搜索

**用途**：跨文件按正则搜索内容。

**关键参数**：
| 参数 | 类型 | 说明 |
|---|---|---|
| `pattern` ✱ | string | 正则表达式 |
| `paths` | string \| string[] | 搜索目录（默认当前 working_directory）|
| `output_mode` | `content` / `files_with_matches`（默认） / `count` | |
| `glob` | string | 文件名过滤（如 `*.{ts,tsx}`）|
| `type` | string | 文件类型（`js`/`py`/`rust`/`go`/`java` …）|
| `-i` | bool | 忽略大小写 |
| `-A` / `-B` / `-C` | number | 匹配行的后 / 前 / 上下文行数（需 `content` 模式）|
| `-n` | bool | 显示行号（需 `content` 模式）|
| `head_limit` | number | 限制结果前 N 条 |
| `multiline` | bool | 启用跨行匹配 |

> ⚠️ `paths` 传字符串数组时不要拼接；省略字段使用默认值，**不要写 `'undefined'` / `'null'`**。

---

## 14. `glob` — 文件名 glob 匹配

**用途**：用 glob 通配符查找文件。

**参数**：
```json
{
  "required": ["pattern"],
  "properties": {
    "pattern": "string — 如 \"**/*.js\", \"src/**/*.ts\", \"*.{ts,tsx}\"",
    "paths": "string | string[] — 搜索根目录，默认 working_directory"
  }
}
```

**典型组合**：先 `glob` 找文件列表 → 再 `rg` 在结果中搜内容，或直接 `rg` 配 `glob` 参数过滤。

---

## 15. `task` — 启动子 Agent（多角色编排）⭐

**用途**：在独立 context window 中启动专门 agent 处理复杂任务，保持主对话简洁。

**4 种 agent_type**：

| agent_type | 模型 | 适用场景 |
|---|---|---|
| `explore` | Haiku | 并行多线程代码库探索 / 跨模块研究 / 多个无关问题 |
| `task` | Haiku | 跑测试 / build / lint / 装依赖：成功只回简短摘要，失败回完整堆栈 |
| `general-purpose` | Sonnet | 复杂多步任务、需要完整工具集 + 高质量推理 |
| `code-review` | （内置） | 高信噪比代码评审；只报 bug / 安全 / 逻辑问题，不评 style；**只读不改** |

**何时 NOT 用 `task`**（直接用底层工具更轻量）：
- 读已知路径文件 → 直接 `view`
- 单次 `rg` / `glob` 搜索 → 直接调
- 需要 bash 输出全部入 context → 直接 `bash`
- 操作已知文件 → 直接 `apply_patch`

**注意**：
- 子 agent **顺序**执行（不并行）
- 每个子 agent **无状态**，必须在 `prompt` 提供完整上下文
- 子 agent 结果一次性以一条消息返回

**参数**：
```json
{
  "required": ["name", "prompt", "agent_type", "description"],
  "properties": {
    "description": "string — UI 显示的 3–5 词描述",
    "prompt": "string — 给 agent 的完整任务说明",
    "agent_type": "explore | task | general-purpose | code-review",
    "name": "string — 短名（生成可读 agent ID，如 \"math-helper\"）",
    "model": "string — 可选模型覆盖"
  }
}
```

---

## 附：精细化管控（在 `create_session` 中）

```python
async with await client.create_session(
    on_permission_request=PermissionHandler.approve_all,
    model='gpt-5.4',
    provider=...,
    working_directory='/abs/path',          # view / apply_patch / rg / glob / bash 都基于此

    # —— 白名单：仅暴露列表内的内建工具 ——
    available_tools=['view', 'glob', 'rg'],

    # —— 黑名单：屏蔽危险工具（仅当 available_tools 为空时生效）——
    excluded_tools=['bash', 'apply_patch', 'web_fetch'],

    # —— 注册 MCP（外部工具源）——
    mcp_servers={
        'microsoft-learn': {'type': 'http', 'url': '...', 'tools': ['*']},
    },

    # —— 自定义工具（与内建工具并存）——
    tools=[my_custom_tool],
) as session:
    ...
```

| 参数 | 作用 | 是否影响自定义工具 |
|---|---|---|
| `available_tools` | 仅暴露列表内的**内建**工具 | ❌ 不影响 |
| `excluded_tools` | 屏蔽列出的**内建**工具 | ❌ 不影响 |
| `tools=[...]` | 注册自定义工具 | — |
| `mcp_servers={...}` | 注册 MCP 工具源 | — |

---

## 权限 Bypass（Always allow）实战

SDK 0.3.0 的 `PermissionRequestResultKind` Literal 仅暴露 4 个值：
`approve-once` / `reject` / `user-not-available` / `no-result`。

**底层 RPC `PermissionDecisionKind`** 其实有 5 个（多了 `approve-for-session` 和 `approve-for-location`），但 Python wrapper 没正式包出来。

### 3 种实现 bypass 的方案

| # | 方案 | 适用 | 关键代码 |
|---|---|---|---|
| 1 | 全 session 暴力放行 | 脚本 / CI / 内网工具 | `on_permission_request=PermissionHandler.approve_all` |
| 2 | **缓存型 session-scope** ⭐ | 桌面 agent / 用户产品 | 自维护 `set()` 命中即静默 approve |
| 3 | 硬塞 RPC 枚举（hack） | 不推荐 | `kind='approve-for-session'  # type: ignore` |

#### 方案 2 完整代码

```python
from copilot.session import PermissionRequestResult

approved_keys: set[tuple[str, str]] = set()

def cached_session_bypass(request, invocation):
    key = (
        request.kind.value if request.kind else '?',
        request.path or request.full_command_text or '*',
    )
    if key in approved_keys:
        return PermissionRequestResult(kind='approve-once')   # 静默

    # 首次：问真人（可换成 GUI / Slack / Webhook）
    answer = input(f'⚠️  {key} → [y/n/s]? ').strip().lower()
    if answer == 's':
        approved_keys.add(key)               # 记住，下次免问
    return PermissionRequestResult(
        kind='approve-once' if answer in ('y', 's') else 'reject'
    )
```

跑通示例：见 [`07_builtin_tools.ipynb`](../07_builtin_tools.ipynb) §4.5。

### 跳过单个工具的权限（自定义工具专用）

```python
@define_tool(description='read-only', skip_permission=True)   # 完全跳过权限层
async def safe_lookup(...) -> str: ...
```

仅对**自己注册的工具**生效；不能用来跳过内建工具的权限。

---

## 重新生成本文档

```bash
# 重新拉取最新内建工具清单（升级 SDK 后请运行）
python -c "
import asyncio, json
from copilot import CopilotClient
from copilot.generated.rpc import ToolsListRequest

async def main():
    async with CopilotClient() as c:
        tl = await c._rpc.tools.list(ToolsListRequest(model='gpt-5.4'))
        data = [{'name': t.name, 'description': t.description, 'parameters': t.parameters} for t in tl.tools]
        with open('hosted_agent_foundry_ghcp_sdk/docs/_builtin_tools_raw.json', 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

asyncio.run(main())
"
```

随后对比 `_builtin_tools_raw.json` 的 diff，按需更新本文档对应章节即可。
