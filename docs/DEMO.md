# DevicePilot 求职 Live Demo

面向 AI 应用开发工程师面试；目标 5～8 分钟。只演示现有能力，不把模拟设备当作真实工业部署，不把测试通过率当作诊断准确率。

## 当前验证状态（2026-09-09）

**NEEDS WORK：真实 Provider 诊断与页面 Sources 尚未验证。** 自动审批阻止向现有 api.deepseek.com 发送 Demo 设备、历史、症状及检索上下文，等待明确授权。没有发出本轮真实诊断调用，不能声称 Provider 故障。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Dashboard | PASS | 实际 Chrome 加载 KPI、趋势、状态分布、最近故障、AI 入口、设备表 |
| Device Detail | PASS | 点击 DEMO-PUMP-001，显示名称、类型、位置、状态 |
| Fault History | PASS | 泵有 1 条“轴承温度升高”，高 / 调查中 |
| 症状输入 | PASS | 指定输入后“开始诊断”可用；未点击发送 |
| Diagnosis | FAIL（审批阻塞） | 尚未取得本轮真实结构化返回 |
| RAG Source 页面 | FAIL（依赖诊断） | 尚未取得本轮页面参考知识 |
| 刷新 | 部分 PASS | 详情和 Dashboard 刷新通过；诊断重跑尚未验证 |
| Seed / Graph 测试 | PASS | Reality Checker：18 passed，精确症状历史路由 True |
| 真实 RAG evaluator | PASS | E5 + Chroma，配置阈值 0.143，12/12 当前用例通过 |

浏览器验证使用现有 Chrome 的 Playwright headless 模式，访问真实本地 Vite/FastAPI，无 mock、响应替换或页面数据注入。原浏览器工具因 Windows sandbox 初始化错误不可用。尚未进行人工投屏彩排。

## 演示前准备

1. 保留现有 `.env`，不复制覆盖、不投屏、不输出密钥。当前配置已检测到模型与密钥，RAG 已开启、索引存在。真实调用使用现有 DeepSeek 配置；选中的 Demo 上下文会发送给该 Provider。
2. 使用本地服务，不启动 production Compose、不连接 VPS。准备浏览器 `http://127.0.0.1:5173`，关闭开发者工具，建议 1440×1100 或相近分辨率。
3. 对照以下 seed 数据；已有额外用户数据时，以实际统计为准，不删除、不改日期、不重置数据来美化图表。
4. 演示前完成一次真实诊断，保存当天症状、结果和参考知识截图。当前此项待授权完成。
5. 提前运行真实 evaluator，预热本地模型，避免现场下载；准备本文件、截图及 `DEMO_RAG_EVALUATION.md`。

### 数据与幂等性

| 设备 | 序列号 | 初始状态 | 初始 Fault |
| --- | --- | --- | --- |
| 循环水离心泵 | DEMO-PUMP-001 | active | 轴承温度升高；high / investigating |
| 仓储温度传感器 | DEMO-TEMP-002 | inactive | 读数间歇中断；medium / open |
| 装配线工业电机 | DEMO-MOTOR-003 | maintenance | 负载运行时振动异常；critical / open |
| 质检视觉控制器 | DEMO-VISION-004 | active | 无 |

`python -m scripts.seed_demo` 按 serial_number 查设备、按 device_id + title 查 Fault，只插入缺失项。当前库首次执行新增 4 台 / 3 条，第二次新增 0 / 0；不删除或覆盖已有数据。不支持 reset；用户修改过记录时不会自动还原。不要并发运行 seed。无需增加 reset。

泵的历史描述是温升和轻微摩擦异响，没有已记录的历史振动。当前症状中的“之前类似振动”是用户报告，不能解释为数据库已经证实。active 是登记状态，不代表现场绝对健康，也不是遥测告警。

## 启动命令

以下在已有依赖环境运行；两个 PowerShell 窗口分别保持运行。

Backend（仓库根目录）：

```powershell
Set-Location D:\DevicePilot
.\.venv\Scripts\python.exe -m scripts.seed_demo
.\.venv\Scripts\python.exe -m scripts.seed_demo
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend：

```powershell
Set-Location D:\DevicePilot\frontend
pnpm dev --host 127.0.0.1 --port 5173 --strictPort
```

本次实际用等价命令 `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort` 启动前端。Backend `/health/ready` 与前端 HTTP 均为 200。浏览器打开前端，Vite 将 `/api` 代理到 8000。已运行时不要重复启动或任意杀掉占用端口的进程；终端正常运行可用 Ctrl+C 停止。

已有索引的真实评估：

```powershell
Set-Location D:\DevicePilot
.\.venv\Scripts\python.exe -m scripts.evaluate_rag --real
```

缺索引时，先确认当前知识目录仅含授权 Demo 内容，再运行 `python -m scripts.index_knowledge`。不要为求命中修改阈值或语料，不需要 `--rebuild`。已有缓存可用 `$env:HF_HUB_OFFLINE='1'` 离线加载；缓存不存在则先在演示前准备。

本轮 Docker daemon 未运行，因此使用本地 Python/Vite。若以后选择现有本地 Docker Demo，运行 `docker compose up -d --build`，必须重新构建 frontend，再检查 8080 页面；不要使用 `compose.production.yml`。本轮未验证 Docker 启动。

## 约 7 分钟讲解与点击顺序

| 时间 | 点击位置 / 操作 | 应看到什么与推荐讲解 |
| --- | --- | --- |
| 0:00–0:40 | 打开首页 | “这是一个设备管理与辅助故障诊断的 Portfolio 项目，数据是明确标识的模拟设备，展示从业务记录到诊断建议的完整链路。” |
| 0:40–1:35 | 设备总览 → 故障趋势 → 最近故障 | KPI 当前为设备 4、运行中 2、停用/维护 2、待处理故障 3；状态分布 2/1/1。趋势按最近七个本地自然日聚合记录创建时间，当前三条在 seed 当日，不是持续采集的遥测。指出泵“轴承温度升高 / 高 / 调查中”。 |
| 1:35–2:20 | 点击该 Fault 标题或设备列表“循环水离心泵” | 核对 DEMO-PUMP-001、Centrifugal Pump、A 厂房泵房与运行中。“登记状态与未解决故障并存，因此要结合记录判断。” |
| 2:20–2:55 | 向下滚动“故障记录” | 查看温升、摩擦异响和调查中。“系统读取的是已有记录；当前报告的振动还需要现场核实。” |
| 2:55–3:40 | 右侧“故障现象”输入下方原句，点击“开始诊断”一次 | 出现诊断中。“最近、又、之前、越来越触发确定性历史上下文路由；最多读取五条历史，再尝试本地知识检索，最后一次模型调用。” 等待时讲流程，不连续点击。 |
| 3:40–4:40 | 诊断结果区域 | 核对风险等级、诊断摘要、可能原因、建议检查、建议操作均存在。只朗读实际返回的摘要和一两项建议，不预设风险必为高。“这些是候选解释和检查建议，结构化校验通过不等于诊断事实正确。” |
| 4:40–5:20 | 结果下方“参考知识” | 展示真实 document 和片段号。“来源由后端根据检索结果生成，不采信模型自称的引用。” UI 片段号是 `chunk_index + 1`，例如片段 1 对应 API index 0。没有来源就明确说无命中，不能编造。 |
| 5:20–6:35 | 切换本文件末尾架构说明 | 解释 RAG、LangGraph、MCP、Skill 各自边界，强调内部 Diagnosis 不走 MCP。 |
| 6:35–7:00 | 收尾 | “这个项目重点是把模型接入真实业务数据流，明确上下文、输出校验、来源和失败边界。当前是单实例辅助诊断 Demo，还没有诊断历史、多用户权限或自动维修。” |

推荐原句：

> 设备最近又出现和之前类似的异常振动，而且温度越来越高。

首页右侧 AI 卡片也可选择“循环水离心泵”→“进入诊断”，进入同一设备详情。不要为演示新增 Fault，以免每次改变数据。Diagnosis 当前不持久化；刷新会清空输入和结果，需要重新输入并发起新调用，不能宣称刷新恢复历史诊断。默认每分钟最多五次，避免连续重跑。

## 截图计划与现状

| 文件 | 状态 / 取景 |
| --- | --- |
| `images/dashboard.png` | 本轮真实新版 Dashboard 全页截图，已替换旧版；涵盖 KPI、趋势、状态、最近故障、AI 入口和设备表 |
| `images/device-detail.png` | 本轮真实泵详情 + 一条历史 Fault；已更新 |
| `images/ai-diagnosis.png` | 仓库既有旧版截图，症状不同，没有可见 RAG 来源；本轮未确认调用来源，不能当作本轮真实成功证据 |
| `images/rag-source.png` | 待真实诊断完成；第三张若能清晰包含参考知识则无需第四张 |

最终 AI 截图应保留当前症状、五个字段和可读文字；必要时另截参考知识区域。只捕获应用内容，不带 console、secret、环境文件、内部路径；不要用 mock、DOM 改字或合成图片制造结果。既有 AI 图片暂保留，不冒充已验证 fallback。README 文本和已有引用路径保持不变。

## 出错时 fallback

- **Provider 失败或超时**：展示实际错误，不重试轰炸。“这次外部模型调用未成功，我切换到事先保存并注明日期与症状的真实结果说明输出结构。” 当前尚缺经本轮验证的 AI 截图；未补齐时只能解释输出契约，不能称旧截图为今天结果。
- **网络异常**：本地设备与 Fault 仍可展示；切换已验证的 evaluator 记录与架构说明。不要打开密钥或原始服务日志投屏排查。
- **RAG 无命中**：如实说参考知识为空，模型建议不能宣称得到知识支持。展示真实 evaluator 中相关与无关样例，解释设备类型过滤及阈值，而不是把 evaluator 结果贴成这次响应。
- **前端/API 失败**：用当前 Dashboard / Device Detail 截图说明此前已验证页面，并清楚标注为截图；现场不改生产环境。
- **限流**：等待完整窗口再手动尝试一次，或转用 fallback，不提高限制。

## 简短技术讲解

```text
React → FastAPI → 有界 LangGraph
                    → 条件读取最近 Fault
                    → 本地 RAG 检索
                    → LiteLLM → 配置的 Provider
                    → JSON / Pydantic 校验 → 结构化结果及来源

外部 Agent + Troubleshooting Skill → stdio MCP
                                     → 三个只读本地服务工具
```

**RAG：负责查找知识。** 原创 Demo Markdown/TXT 经本地 multilingual E5 embedding 与 Chroma cosine 检索，使用设备类型、Top-K 和 0.143 距离阈值。命中不保证结论正确；来源只表示进入上下文的片段。使用外部 Provider 时选中的文本会发送给它。

**LangGraph：负责有界诊断流程和历史上下文路由。** 固定无环图、确定性语义规则，最多一次历史读取、一次 retrieval service 调用、一次 Provider 调用；无开放式工具循环或自动修复。路由单测通过，不等于 UI 展示了内部 trace；当前 trace 不进入公开结果。

**MCP：向外部 Agent 暴露三个只读工具。** `get_device`、`get_recent_faults`、`search_knowledge`，本地 stdio，无远程 MCP 服务或写工具。

**Skill：规定外部 Agent 如何安全、有界地使用 MCP。** 一次单设备调查，每个工具最多一次、总共最多三次，无重试循环或写入，区分设备记录、非可信症状/知识与推断。它是外部 Host 的操作指引，Host 自动发现/安装尚未实现。

**内部生产 Diagnosis 不通过 MCP。** Backend 直接调用本地 Python 服务；MCP 是外部互操作边界，Skill 也不是 Backend runtime。

本轮推荐症状独立本地检索也已通过：centrifugal-pump.md，chunk_index=0，distance=0.11062675714492798；详见 [RAG 实测记录](DEMO_RAG_EVALUATION.md)。此证据不替代 Diagnosis 页面 Sources 验证。
