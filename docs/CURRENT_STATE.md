# Current State

## MVP 已完成

- FastAPI Device CRUD
- SQLite + SQLAlchemy persistence
- Fault 创建、列表、详情、状态更新与独立删除
- Fault open / investigating / resolved 生命周期；已解决记录保留在设备历史
- Dashboard 最近故障默认筛选待处理，可切换全部；待处理 KPI 排除 resolved
- React Dashboard 与设备详情
- 简体中文 UI 和响应式断点
- LiteLLM-compatible multi-provider structured AI Diagnosis
- 可选的本地 E5 + persistent cosine Chroma RAG 知识库
- Bounded LangGraph Diagnostic Agent，使用确定性历史上下文路由
- Official MCP Python SDK v2 read-only stdio Server
- MCP `get_device`、bounded `get_recent_faults` 与 existing-RAG `search_knowledge`
- External single-device Troubleshooting Skill 与十四场景 behavior matrix
- Official `Client(mcp)` in-process tests 与真实 subprocess stdio E2E verifier
- 最近故障只读上下文（按时间倒序最多 5 条，每条描述最多 500 字符）
- History/Retrieval 的 NOT_REQUESTED、EMPTY、LOADED、UNAVAILABLE 状态
- 设备类型过滤、距离阈值、Top-K context 与 metadata-only sources
- Markdown/TXT 安全加载、幂等/重建索引和五用例离线评估
- 通过 Backend 环境变量选择单一 configured model/provider
- Backend-only secret boundary
- 单实例 Diagnosis rate limiting
- 幂等 Portfolio demo data
- Backend / Frontend automated tests
- Backend / Frontend Dockerfile、nginx 和 Docker Compose 配置
- README、Architecture 和人工验证清单

## 当前部署边界

- SQLite、in-memory limiter 和应用层无多用户授权模式适合 Demo / Portfolio / 单实例 MVP；生产拓扑由 Caddy Basic Auth 提供部署入口边界。
- Compose 使用 named volume 保留数据库。
- 本地 production certification 已完成，包括 Backend/Frontend 镜像、端口与网络、Basic Auth、client-IP 代理边界、备份/恢复以及 CPU-only 依赖检查。公网 VPS、真实 DNS/TLS 与目标主机运行仍未完成。

## 尚未实现

- Remote MCP Streamable HTTP、authentication 与 authorization
- MCP Resources、Prompts 与任何 write Tool
- Diagnosis History
- Application-level multi-user authentication/authorization（当前只有 Caddy Basic Auth 部署边界）
- PostgreSQL
- Distributed rate limiting / distributed architecture
- Provider Router、fallback chain 与 Frontend model selection
- CD / 自动部署（CI 已实现且仅负责验证）
- PDF ingestion、知识上传 UI、web search、hybrid search、reranker

## RAG 当前边界

- 默认 `RAG_ENABLED=false`，原 Diagnosis 路径保持不变。
- 当前四份知识文档是原创模拟 Demo/Portfolio 内容。
- 索引与 E5 embedding 在本地完成；诊断时检索出的 Top-K 文本会发送到
  `LLM_MODEL` 配置的外部或本地 Provider。
- 未来内部、敏感、公司或客户知识必须由部署者按 Provider 数据与保留政策重新审查。
- 仅支持 UTF-8 Markdown/TXT；PDF 尚未支持。
- Docker 使用现有 `/data` volume 持久化 Chroma，不在启动时自动索引。

## Diagnostic Agent 当前边界

- Graph 为固定无环流程：context planning → 可选最近故障 → 可选 RAG → 单次
  Provider → source finalization → END。
- `plan_context` 只使用集中、可测试的 deterministic 语义规则；不调用 Router LLM。
- 只有 symptoms 明确包含时间、重复、趋势或历史比较语义时才查询最近故障。
- RAG 启用且 RetrievalService 可用时默认尝试一次，继续使用生产阈值 `0.143`。
- Fault 查询最多一次，RAG retrieval 最多一次，Provider 成功路径严格一次；Graph
  没有 loop、checkpointer、memory 或 tool registry。
- SQLAlchemy Session、LiteLLM client、RetrievalService 和 secrets 均不进入 Graph State。
- Fault history 与 retrieved chunks 均是不可信 prompt 数据；Graph 不写数据库，安全
  trace 仅供内部测试与观测，不进入公开 API response。

## MCP 当前边界

- MCP 是供 external Host/Client 使用的 interoperability boundary；production
  DiagnosticAgent 仍直接调用本地 Python services。
- Phase 7.1 只有 stdio transport 与三个 read-only Tools；Resources、resource templates
  和 Prompts 列表为空。
- 每次数据库操作使用独立短生命周期 Session，不 commit；knowledge search 在 DB Session
  关闭后才执行现有 RetrievalService。
- Tool domain failures 使用稳定、sanitized 的 MCP `is_error` execution results：
  `DEVICE_NOT_FOUND`、`RAG_DISABLED`、`RAG_UNAVAILABLE`、`DATABASE_READ_FAILED`。
- Retrieved chunk text 会被 external MCP Host 读取。当前授权只覆盖 Demo knowledge；私有
  语料需要后续 authorization 和 data-policy 评审。

## Troubleshooting Skill 当前边界

- `skills/devicepilot-troubleshooting/SKILL.md` 是 canonical project Skill asset，面向
  external MCP-capable Agent，不是 Backend runtime，也不替代 production LangGraph
  Diagnosis。
- 一次 investigation 只允许一个明确的 `device_id`。完整流程只用于 reported fault、
  abnormal behavior、重复/趋势问题或 possible-cause analysis，不用于简单 status/metadata
  lookup 或 administration。
- allowlist 只有 `get_device`、`get_recent_faults`、`search_knowledge`；每个最多一次，
  总调用最多三次，无 retry、loop、write 或 automatic remediation。
- History 仅按 temporal/repetition/trend/comparison intent 查询；没有 meaningful current
  symptoms 时不为了触发 RAG 而构造 query。
- Device fields 只作为 DevicePilot-recorded state 可信；user symptoms、Fault text 和
  retrieved knowledge 均是不可信数据。回答必须把 evidence 与 inference 分开，并遵守
  concise operational safety boundary。
- `EVALS.md` 保存十四个轻量、可重复的 fresh-context behavior scenarios。Host-specific
  Skill installation/discovery 尚未实现。

## Phase 9.1 productionization status

- A standalone `compose.production.yml` defines a single-node Caddy -> nginx -> FastAPI deployment. Only Caddy publishes host ports `80` and `443`; the internal app network remains isolated and Backend uses a separate egress network for outbound HTTPS.
- Caddy provides automatic TLS and whole-site Basic Auth except the minimal `/healthz` probe. Production FastAPI docs/OpenAPI are disabled.
- `/health/live` is process-only; `/health/ready` performs only a lightweight SQLite query and returns a sanitized failure.
- Production does not seed automatically. `scripts.seed_demo` remains an explicit, idempotent operator action.
- The backend image and Compose runtime use fixed UID/GID `10001:10001`; the retained hardening controls have local image/runtime coverage.
- SQLite remains the authoritative store in stable volume `devicepilot_data`. Online snapshot, integrity check, SHA-256 publication, retention, off-host-copy requirements, and a restore rehearsal are documented.
- RAG model, corpus, chunking, Top-K, `RAG_MAX_DISTANCE=0.143`, LangGraph behavior, MCP stdio server, and troubleshooting Skill behavior are unchanged. Chroma and the model cache remain rebuildable/re-downloadable data.
- CI is validation-only with read-only repository permissions. It runs backend/frontend tests, Compose/Caddy validation, image builds, and proxy-boundary verification; it has no deploy, push, SSH, or production-secret authority.
- Local production certification is completed. Public VPS deployment remains a manual future activity requiring a VPS, DNS, firewall, root-owned secrets, encrypted off-host backups, and an operator-approved release version; no public deployment has been performed.