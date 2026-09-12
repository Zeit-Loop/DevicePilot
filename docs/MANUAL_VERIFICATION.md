# Final Manual Verification

## Preparation

1. 复制 `.env.example` 为 `.env`；需要真实 AI 时只在本机填写 `LLM_MODEL`、`LLM_API_KEY` 和可选 `LLM_API_BASE`，不要发送 Key 到聊天或提交 Git。
2. 使用本地开发命令或 `docker compose up --build` 启动应用。
3. 打开设备总览，确认四台 Demo 设备和故障统计存在。

## End-to-End

- Dashboard：统计、设备列表、中文状态和空/错误反馈
- Device Detail：设备信息、日期、故障列表
- Device Form：创建、编辑、中文必填提示、删除确认
- Fault Form：新增专用测试故障，确认故障记录立即出现
- Fault Lifecycle：开始调查 → 标记已解决；页面局部更新，历史仍保留
- Dashboard：返回总览后待处理 KPI 减少，默认最近故障不显示该记录；切换“全部”仍可找到
- Reopen：详情中重新打开，返回 Dashboard 后待处理 KPI 和默认列表恢复
- Fault Delete：对专用测试记录先取消删除确认，核对记录保留；再次确认删除后记录消失，设备及其他故障仍存在
- Operation Failure：状态更新或删除失败时展示错误，原记录保留，按钮恢复可用
- AI Diagnosis：输入“设备外壳温度异常升高，运行时出现明显异响和振动。”
- Structured Result：风险等级、诊断摘要、可能原因、建议检查、建议操作
- Stale Result：修改故障现象后旧结果立即清除，并可重新诊断
- Isolation：Diagnosis 不自动创建 Fault
- Rate Limit：连续请求超过配置次数后显示中文频率限制提示

## Responsive widths

分别在 Chrome DevTools 使用以下 viewport：

### Desktop — 1440px

- Dashboard 四列统计卡片正常
- Sidebar、设备列表、详情双栏和 AI Panel 无重叠

### Tablet — 768px

- Sidebar 收窄
- 统计卡片两列
- Device Detail 与 AI Panel 改为单列

### Mobile — 375px

- Navigation 顶置
- 统计、表单、详情信息均为单列
- 表格可横向滚动，页面主体不产生意外水平溢出
- 中文按钮可点击、文本不截断、Modal 可滚动

## Screenshots

确认没有 Secret、Codex UI 或调试信息后保存：

1. `docs/images/dashboard.png`
2. `docs/images/device-detail.png`
3. `docs/images/ai-diagnosis.png`

截图应只包含 DevicePilot 应用页面。

## Fault lifecycle 验证记录（2026-09-09）

- Backend 全量：212 passed、2 skipped；保留现有 Device/Fault/Diagnosis 回归。
- Frontend 全量：56 passed；typecheck、build、git diff --check 通过。
- 真实 Chrome headless + 本地 Vite/FastAPI：新建专用测试 Fault，依次验证调查、解决、重新打开、直接解决；未 mock API。
- 默认待处理 KPI 基线 3；测试 Fault 解决后为 3，重新打开后为 4，默认最近列表相应消失/恢复，“全部”保留 resolved。
- 删除先取消并确认记录存在，再确认删除本轮测试 Fault（id=4）；目标回读 404、设备回读 200、泵原历史与测试前深比较一致，刷新后删除仍生效。
- 375/768/1440px 详情截图和无水平溢出断言通过。
- 本次不调用真实 LLM；RAG/LangGraph/MCP/Skill 与 Deployment/CI 未修改。构建有大于 500kB 的 bundle 提示，无构建错误。
