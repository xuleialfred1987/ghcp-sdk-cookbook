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

