# DevicePilot Architecture

## Frontend

React + TypeScript 提供设备总览、设备详情、故障登记和 AI 诊断界面。所有请求通过集中 API client 发出；默认使用同源 `/api`，开发环境由 Vite proxy 转发，Docker 由 nginx 转发。

## Backend

FastAPI 暴露 Device、Fault 和 Diagnosis API。Route handler 使用短生命周期 SQLAlchemy Session；Pydantic Schema 独立于 ORM Model。现有 `create_app()` 注入边界仅用于测试数据库、Diagnosis 替身和 limiter。

## Database

```text
React → FastAPI → SQLAlchemy → SQLite
```

SQLite 文件路径由 `DATABASE_URL` 配置。Docker 使用同一命名卷分别持久化
`/data/devicepilot.db` 与 `/data/chroma`；普通启动不自动索引知识。它适合当前
单实例 MVP；未来可保持 ORM/API 边界迁移到 PostgreSQL。

## AI Diagnosis

```text
React
  → FastAPI Diagnosis endpoint
  → per-client rate limiter
  → bounded LangGraph Diagnostic Agent
  → deterministic context planning
  → optional recent Fault history (read-only, latest 5)
  → optional existing RetrievalService
  → LiteLLMDiagnosisProvider
  → LiteLLM Provider
  → external or local LLM selected by LLM_MODEL
  → Structured Pydantic Result
  → React
```

Frontend 不直接访问任何 LLM Provider，原因是 `LLM_API_KEY` 必须保留在服务端，输入与结构化输出也必须经过统一验证和安全错误映射。

Provider 使用 LiteLLM 的统一 Chat Completion 格式，并在调用前选择一个固定模式：
`deepseek/*` 使用 `json_object`，其他明确支持 native schema 的模型使用
`json_schema`，能力未知或不支持的模型使用 prompt-only JSON。DeepSeek 的实际
Chat Completion endpoint 优先于 `supports_response_schema()` capability hint，并为
当前低延迟诊断显式关闭 thinking。所有模式都只发起一次 completion，最终统一执行
`json.loads()` 和 `DiagnosisResult.model_validate()`。无 retry、Router、fallback
chain 或 provider registry。

### Bounded Diagnostic Agent

```text
START
  → plan_context
  → [need history?] load_recent_faults / skip
  → [RAG available?] retrieve_knowledge / skip
  → generate_diagnosis
  → finalize_result
  → END
```

`plan_context` 是 deterministic helper 驱动的 node，不调用额外 LLM。只有症状明确表达
时间、重复、趋势或历史比较时才读取 Fault；查询按 `created_at DESC, id DESC` 排序并
使用 `LIMIT 5`，每条 description 最多 500 字符。History 和 Retrieval 分别使用
`NOT_REQUESTED`、`EMPTY`、`LOADED`、`UNAVAILABLE` 状态，避免用空列表混淆未请求、
无结果和失败。

RAG 启用且现有 RetrievalService 成功初始化时默认尝试一次。Fault 读取或 RAG 失败
均安全降级；Provider failure 仍是 hard failure。所有成功路径只调用 Provider 一次。
Graph 无 loop、checkpointer、memory、tool registry 或动态工具执行，并且不执行任何
数据库写入。Session、Provider、RetrievalService 和 secrets 是 request/runtime
dependencies，不进入业务 State。安全 trace 只在内部 State 中存在，不修改公开
`DiagnosisResult`。

## Local RAG Boundary

```text
Indexing:
Knowledge Markdown/TXT
  → safe loader
  → deterministic chunks
  → local multilingual-e5-small passage embeddings
  → persistent cosine Chroma vectors

Diagnosis:
trusted Device facts + untrusted fault report
  → local multilingual-e5-small query embedding
  → normalized device-type filter
  → maximum cosine-distance threshold
  → Top-K untrusted Retrieved Chunks
  → LiteLLM Provider
  → external or local LLM
```

Indexing and embedding are local and do not call the Chat provider. The final diagnosis
prompt contains only the thresholded Top-K text, not whole documents or the vector store.
That Top-K text is sent to the provider configured by `LLM_MODEL`; it stays local only
when a local provider such as Ollama is selected. Current content is original simulated
Demo/Portfolio material. Future internal, sensitive, company, or customer knowledge
requires deployer review against the provider's data and retention policy.

Retrieved chunks and the user report remain untrusted data. System rules and trusted
database device facts take precedence on conflict. Retrieval errors are logged only as
safe operational failures and degrade to the original non-RAG prompt. API sources are
deduplicated server-side from safe relative `document` plus `chunk_index`; retrieved text,
absolute paths, credentials, and full fault reports are neither logged nor exposed as
source metadata.

## MCP Read-only Interoperability Boundary

```text
External MCP Host
  → official MCP v2 Client
  → stdio
  → DevicePilot MCPServer
  → per-operation SQLAlchemy Session / existing RetrievalService
```

Phase 7.1 的 MCP Server 是外部互操作边界，不是内部 service bus。它不 import FastAPI
app、不依赖 request context，也不调用 LiteLLM、LangGraph 或 Diagnosis API。生产
DiagnosticAgent 继续直接调用 `SQLAlchemyFaultHistoryReader` 与 `RetrievalService`，避免
同项目 MCP round trip 的额外 latency、序列化和故障模式。

Server 只注册 `get_device`、`get_recent_faults`、`search_knowledge` 三个 Tool。
MCPServer v2 会自动广告 Tools/Resources/Prompts capability，但 Phase 7.1 的
`resources/list`、resource templates 与 `prompts/list` 均为空。不存在 write、shell、
filesystem、HTTP、web、remediation 或 MCP chaining Tool。

每次数据库读取创建并关闭独立 Session；Session、ORM object、Engine 和异常细节不进入
MCP payload，Tool 不调用 `commit()`。最近故障固定按 `created_at DESC, id DESC`，最多
5 条且 description 最多 500 字符。Knowledge Tool 先读取可信 Device type 并关闭 DB
Session，再按需初始化现有 E5/Chroma RetrievalService；返回最多 3 个 sanitized chunks，
不返回 title、distance、vector、absolute path 或 raw metadata。

stdio 是唯一 Phase 7.1 transport。Remote Streamable HTTP 必须与 authentication、
authorization、TLS、rate limiting 与 data policy 一起设计，当前不实现。

## External Troubleshooting Skill Boundary

```text
User fault report for one device
  → External MCP-capable Agent loads DevicePilot Troubleshooting Skill
  → get_device (once)
  → optional get_recent_faults(limit=5) (once)
  → optional search_knowledge (once)
  → evidence-bounded response
  → STOP
```

Phase 8.1 的 `skills/devicepilot-troubleshooting/SKILL.md` 是 portable procedural
guidance，不是新的 runtime 或 Backend component。它只处理单个设备的故障调查；简单
status/metadata lookup 和 DevicePilot administration 不触发完整流程。缺少或存在歧义的
`device_id` 会在任何 MCP 调用前停止并要求用户确认。

Skill 的 allowlist 固定为当前三个 read-only Tools，每个最多调用一次、总数最多三次，
没有 retry、loop、write、automatic remediation 或额外 Tool fallback。History 仅在明确
时间、重复、趋势、历史比较或显式 history intent 时读取；没有有意义的当前症状时跳过
knowledge search。Fault natural-language text 与 retrieved chunks 始终是不可信数据，
不能改变 Tool policy、引发执行动作或覆盖终止条件。设备字段仅作为 DevicePilot-recorded
state 可信，不等同于已验证的现场物理状态。

三层边界保持独立：Internal LangGraph 是 Backend-owned production diagnosis；MCP
Server 是 capability discovery/invocation boundary；Troubleshooting Skill 是 external
Agent 的 usage guidance。项目内路径是 canonical Skill asset，但 Host-specific discovery
和安装机制属于适配工作，不假设所有 MCP Host 会自动发现该目录。

## Configuration

`app/config.py` 从环境读取数据库、CORS、限流、可信代理、LLM 和 RAG 配置。RAG 默认关闭；知识目录、Chroma 路径、collection、Top-K、最大 cosine distance、chunk size/overlap 和文件上限均可显式配置。模型由 LiteLLM identifier 选择；除明确的本地 Ollama 模型外，Provider Key 必须配置。默认同源部署不需要 CORS；分域部署必须显式列出 origins。

## Testing

Backend 使用 Pytest + TestClient 和临时 SQLite；Frontend 使用 Vitest + Testing Library。LiteLLM 测试 mock 唯一的外部 completion 边界，不调用真实付费模型，不持久化 Diagnosis，也不会创建 Fault。

## Deployment

Production Docker defaults to CPU embeddings. The Backend build installs a pinned
CPU-only wheel from the official PyTorch CPU index before the shared Python requirements,
constrains the second resolver pass to the same CPU build, and then verifies the installed
torch/CUDA state, forbidden distributions, and `pip check`. This deployment choice does
not change the E5 model, RAG retrieval, threshold, Diagnosis behavior, or API. The shared
`requirements.txt` remains platform-neutral, so local development may continue to use a
compatible GPU PyTorch build.

Backend image 以非 root 用户运行 FastAPI。Frontend image 使用多阶段构建，并由 nginx 提供静态文件和 `/api` reverse proxy。Compose 在 Backend 启动前幂等 seed 演示数据，并通过 named volume 保留 SQLite。

Diagnosis limiter 是单进程内存实现。若扩展为多个 Backend 实例，应将限流迁移到共享存储或网关层。

## Single-node production topology

```text
Internet
  -> Caddy :80/:443 (TLS + whole-site Basic Auth; sanitize proxy headers)
  -> frontend nginx :80 (no host port; forward Caddy XFF unchanged)
  -> FastAPI :8000 (no host port; one process; trusted proxy mode)
  -> SQLAlchemy -> /data/devicepilot.db
```

Caddy and frontend share the `edge` network. Frontend and backend share the internal `app` network. Caddy is deliberately absent from `app`, so it cannot bypass nginx to reach FastAPI. No Docker socket, database port, Chroma port, or remote MCP service is exposed.

The stable `devicepilot_data` volume contains three logical persistence classes: authoritative SQLite at `/data/devicepilot.db`, rebuildable Chroma data at `/data/chroma`, and a re-downloadable Hugging Face cache at `/data/huggingface`. The design retains SQLite and exactly one backend process for the MVP; it does not enable WAL, add Alembic, or change RAG behavior. Backups leave `/data` through the maintenance-only backup service into the independent host path `/var/backups/devicepilot`.

At the trust boundary, Caddy replaces public forwarding headers with the direct client identity. nginx forwards Caddy's `X-Forwarded-For` value unchanged, and FastAPI trusts it only because production sets `TRUST_PROXY_HEADERS=true` behind this closed proxy chain. Caddy removes `Authorization` before forwarding so application code never receives the Basic Auth credential.

Production backend containers run as fixed UID/GID `10001:10001`, drop all capabilities, forbid privilege escalation, use a read-only root filesystem, and provide only bounded `/tmp` plus the writable data volume. Docker uses bounded local logs. Caddy and nginx are not given Docker access or unvalidated hardening that would break their runtime.