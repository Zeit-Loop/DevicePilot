# Decisions

## Same-origin API

Frontend 默认调用 `/api`。Vite 和 nginx 分别处理开发与生产代理，避免在 bundle 中硬编码部署域名，并让默认部署无需开放 CORS。

## Single-instance rate limiter

Diagnosis 使用按客户端 IP 的进程内 sliding window limiter，默认每分钟 5 次。它足以保护当前单实例 MVP 的 LLM 调用成本；多实例版本应使用共享存储或 API Gateway。

## SQLite persistence

当前继续使用 SQLite，并在 Docker 中挂载 named volume。它降低 Demo 部署复杂度；PostgreSQL 保留为扩展路线。

## Explicit demo seed

演示数据由 `python -m scripts.seed_demo` 显式、幂等生成。普通应用启动不隐式污染数据库；Compose 为作品演示会在 Backend 启动前运行该命令。

## Backend-only configurable AI provider

`LLM_API_KEY`、prompt 和 LiteLLM provider 调用只存在于 Backend。Frontend 只接收经过 JSON 解析和 Pydantic 验证的结构化结果。当前只运行一个环境变量配置的模型，不引入 Router、fallback chain 或 provider registry。

`supports_response_schema()` 是 capability hint，不是 endpoint compatibility 的充分
保证。真实 `deepseek/deepseek-v4-flash` Chat Completion 会拒绝 `json_schema`，但
支持 `json_object`；因此 structured-output strategy 在调用前确定为：DeepSeek 使用
`json_object`，schema-capable non-DeepSeek 使用 `json_schema`，其余使用
prompt-only JSON。DeepSeek 同时显式禁用 thinking。三种模式都只调用一次模型，并以
`json.loads()` 和 `DiagnosisResult.model_validate()` 作为最终验证边界，不做付费
retry 或模型 fallback。

## CPU-only PyTorch for production Docker

Production Docker defaults to CPU embeddings because the current CI/VPS deployment does
not require GPU inference. The Backend image installs `torch==2.13.0+cpu` from the
official PyTorch CPU index before resolving the shared requirements. A Docker-only
constraint keeps the second resolver pass on that exact CPU build; post-install checks
verify the torch/CUDA state, reject CUDA, NVIDIA, and Triton distributions, and run
`pip check`. Keeping the same public PyTorch version while changing only its build
variant minimizes behavior risk and prevents `sentence-transformers` from selecting the
default Linux CUDA wheel and its GPU runtime dependencies.

This is intentionally a Docker-only dependency decision. The shared
`requirements.txt` remains platform-neutral, so a local developer may use a compatible
GPU PyTorch build. The embedding model remains
`intfloat/multilingual-e5-small`, the production threshold remains `0.143`, and RAG,
Diagnosis, API, and Frontend behavior are unchanged. GPU container deployment is out of
scope for the MVP.

## Bounded local RAG

采用固定链路 `DocumentLoader -> deterministic chunker -> E5 EmbeddingProvider ->
persistent cosine Chroma -> RetrievalService -> DiagnosisService -> LiteLLM`，不引入
LangGraph、Agent、MCP、reranker、hybrid search、Graph RAG、web search、memory 或
upload UI。只支持带 `title` 与 `equipment_type` front matter 的 UTF-8 Markdown/TXT；
PDF 是明确限制。

`intfloat/multilingual-e5-small` 只在真实 indexing/retrieval 时延迟初始化。
`query: ` 与 `passage: ` 前缀只由 EmbeddingProvider 添加。chunk 默认 600 字符、
重叠 80 字符；stable identity 包含 source、normalized equipment type、chunk index
和 content。普通索引会协调 changed/deleted source，`--rebuild` 才先清空 collection。

Chroma collection 显式使用 cosine distance，数值越小越相关。历史上的离线
deterministic evaluation 使用 `0.55`：其临时 fake embedding 五用例中，四个相关
用例距离为 `0.0`、`0.0`、`0.0`、`0.292893`，无关打印机用例最近距离为 `1.0`。
这只能证明离线夹具的可重复性，不能把 fake 距离转移为生产阈值。

首次真实五用例测量仍使用 `0.55`，结果为 4/5：相关 nearest distance 分别为
`0.0858945847`、`0.0890958905`、`0.1017355919`、`0.1076521873`，无关用例为
`0.1584613323`。扩展后的真实十二用例在 `0.55` 下为 8/12；八个正例的最大
nearest distance 是 `0.14008313417434692`（均值 `0.11413395404815674`），四个
反例的最小 nearest distance 是 `0.14624953269958496`（均值
`0.16222026944160461`）。

因此生产 `RAG_MAX_DISTANCE` 默认值选择 `0.143`，接近这两个边界的中点：它比
max positive 高约 `0.002917`，比 min negative 低约 `0.003250`，在约
`0.006166` 的间隙中取得近似对称的 margin。这个 separation 很 narrow，且只对
当前 Demo 语料、模型和十二用例成立；它不是通用质量或 benchmark 声明。语料、
embedding model 或检索行为发生实质变化后，必须重新做真实测量和阈值选择。

## RAG provider data boundary

索引链路 `knowledge text -> local E5 embedding -> vectors` 不调用 Chat provider。
Diagnosis 链路为 `Local Knowledge Base -> Retrieval -> thresholded Top-K Retrieved
Chunks -> LiteLLM Provider -> external or local LLM`。只发送当前诊断需要的 Top-K
chunk text，不发送整份文件、vector store 或额外 source metadata。选择 hosted
`LLM_MODEL` 时 retrieved text 会离开本机；选择 `ollama/` 等 local provider 时
final model call 可保持本地。

当前授权仅覆盖仓库内原创模拟 Demo/Portfolio 知识。未来 internal、sensitive、
company 或 customer knowledge 必须由部署者依据 Provider 的数据使用、保留和组织
政策重新评审。Retrieved text 与 fault report 始终是不可信数据，不能覆盖 system
rules 或可信数据库事实。日志仅记录安全的运行状态/计数，不记录完整 chunks、API
keys 或完整 fault descriptions。API sources 仅允许 safe relative `document` 与
`chunk_index`，不得暴露绝对路径。

## Bounded deterministic LangGraph diagnostic workflow

Phase 6 使用一个固定、无环的 LangGraph StateGraph 替换默认 Diagnosis orchestration，
但保留现有 RetrievalService、`RAG_MAX_DISTANCE=0.143`、LiteLLMDiagnosisProvider、
structured-output strategy 和 Backend source reconstruction。采用 LangGraph 的目的仅是
显式化条件分支、执行状态和终止边界；不引入开放式 ReAct、Router LLM、MCP、memory、
checkpointer、tool registry 或自动修复。

Fault history routing 使用集中 deterministic 语义规则。只有 symptoms 明确包含时间、
重复、趋势或历史比较语义时，才执行一次只读查询：按 `created_at DESC, id DESC`
取最多 5 条，每条 description 最多 500 字符。RAG 在启用且 RetrievalService 可用时
默认尝试一次，不通过人为规则跳过有价值的检索。

History 和 Retrieval 使用独立的 `NOT_REQUESTED`、`EMPTY`、`LOADED`、`UNAVAILABLE`
状态；`need_fault_history` 与 `use_rag` 是核心布尔决策，不维护会随组合增长的 route
枚举。SQLAlchemy Session、Provider、RetrievalService、clients 和 secrets 都不进入
Graph State。Fault history 与 retrieved chunks 均作为 untrusted prompt data。

Graph 的硬边界为 Fault query <= 1、RAG retrieval <= 1、成功路径 Provider call == 1、
database writes == 0、loops == 0。内部 safe trace 不进入公开 API response，现有
Diagnosis endpoint、rate limit、HTTP error mapping、DiagnosisResult 和 Frontend contract
保持不变。

## MCP as a read-only external boundary

Phase 7.1 采用官方 `mcp>=2,<3` Python SDK 和 stdio transport，把 MCP 定位为 external
Host/Client 的 interoperability boundary。Server 只暴露 `get_device`、最多 5 条的
`get_recent_faults` 和复用现有 RetrievalService 的 `search_knowledge`。MCPServer v2
自动提供 Tools/Resources/Prompts discovery；Resources、resource templates 与 Prompts
保持空列表，不为展示协议 primitive 而重复 Tool 能力。

生产 DiagnosticAgent 不改为 MCP Client。same-project MCP round trip 会增加 latency、
协议序列化、进程生命周期与额外 failure modes，却不改善内部 testability；直接 Python
service call 仍是正确边界。

MCP 数据库读取使用每次 operation 独立 Session，只执行 SELECT、从不 commit，并在
retrieval 前关闭 Session。Knowledge search 继续使用
`intfloat/multilingual-e5-small`、现有 Chroma collection、现有 Top-K 配置和
`RAG_MAX_DISTANCE=0.143`，对外最多返回 3 个 sanitized chunks。Full document、title、
distance、embedding vector、absolute path、raw metadata 与 exception detail 均不暴露。

Domain failures 使用 MCP Tool execution error / `is_error`，稳定 code 为
`DEVICE_NOT_FOUND`、`RAG_DISABLED`、`RAG_UNAVAILABLE` 与
`DATABASE_READ_FAILED`。Remote Streamable HTTP 与 authentication/authorization 被明确
延后，不增加 Compose MCP service。

## External Skill as bounded procedural guidance

Phase 8.1 将 DevicePilot Troubleshooting Skill 定位为 external MCP Host 中的 procedural
usage layer，而不是第二个 LangGraph 或新的 execution runtime。Internal LangGraph 继续
拥有生产 Diagnosis orchestration、RAG context 与 LiteLLM call；MCP Server 继续只负责
三个 read-only capabilities 的 discovery/invocation；Skill 只规定外部 Agent 何时、为何、
按什么边界使用这些 Tools。

第一版只支持 exactly one `device_id` 的 fault investigation。Tool allowlist 固定为
`get_device`、`get_recent_faults`、`search_knowledge`，每个最多一次、总调用最多三次，且
无 retry 或 loop。History 由 temporal/repetition/trend/comparison intent 决定；只有存在
meaningful current symptoms 才执行一次 knowledge search。这些限制避免把 Skill 演变成
production Agent 的文本副本，也防止 future MCP discovery 中的 write/execution Tool
扩大当前授权。

Skill 采用分层证据模型：Device fields 仅是可信的 DevicePilot-recorded state，不保证
physical ground truth；user symptoms、Fault natural-language text 与 retrieved knowledge
均为 untrusted data；最终判断只属于 inference。Knowledge provenance 只允许使用 MCP
实际返回的 `document` 与 `chunk_index`。Operational safety 禁止绕过 interlock/protection、
拆除 guard 或危险 live/rotating/hot inspection，并在存在危险时转向 site procedures 或
qualified personnel。

Canonical asset 位于 `skills/devicepilot-troubleshooting/SKILL.md`，十四个可重复行为场景
位于同目录 `EVALS.md`。正文保持 Host-neutral；不同 MCP Host 的 Skill discovery/install
机制留给 future adapter，不假设 project-local path 会被自动发现。

## Phase 9.1 single-node production boundary

- Use official Caddy `2.11.4-alpine` as the only public edge on `80/443`. It owns automatic TLS and whole-site Basic Auth; `/healthz` is the sole unauthenticated path.
- Keep nginx between Caddy and FastAPI. This preserves same-origin `/api` routing and creates an explicit network bridge while preventing Caddy from joining the internal backend network.
- Treat Caddy as the only public client-IP authority: overwrite public forwarding headers, pass the generated XFF through nginx unchanged, and strip `Authorization` before application ingress.
- Continue with SQLite and one backend process for the productionized MVP. A database/platform migration is not justified by the current demo scale; WAL, Alembic, multi-instance workers, and complex infrastructure remain deferred.
- Keep `/data/devicepilot.db`, `/data/chroma`, and `/data/huggingface` in the stable named volume but classify only SQLite as authoritative. Chroma is rebuilt from Git-tracked knowledge and the model cache is re-downloaded.
- Disable automatic production seed. Operators may run the existing idempotent seed exactly when demo data is desired.
- Use immutable local image tags from required `APP_VERSION`; retain current and previous images and roll application code back by switching the tag. Never restore SQLite for an ordinary application rollback.
- Store production backend and Caddy environments outside Git as root-owned mode-`0600` files. Repository examples contain placeholders only.
- CI validates and builds but never deploys, pushes images, holds VPS credentials, or invokes a real LLM. Remote MCP and hosted troubleshooting Skill services are explicitly excluded from production Compose.

## Bounded Fault lifecycle

Fault 状态更新使用专门的 FaultStatusUpdate，只接受必填 status（open、investigating、resolved），其他字段拒绝；不修改 ORM model 或增加生命周期时间字段。API 允许设置三个合法状态（包括幂等同状态更新），UI 提供开始调查、直接解决和重新打开的主要业务路径，不增加审批或转换权限系统。

Resolved 是保留历史的完成状态；DELETE 仅用于错误/测试数据清理，经 UI 明确确认后只删除目标 Fault。设备历史与 AI/MCP 的最近历史读取继续包含 resolved，不改变上下文路由或检索语义。

Dashboard KPI 从完整已加载数据统计 open + investigating；最近故障默认先过滤待处理再取最新五条，全部视图仍显示最近五条历史。趋势继续按故障创建时间统计，解决故障不会抹去过去事件。页面返回时重新读取服务端数据，不引入全局状态管理库。
