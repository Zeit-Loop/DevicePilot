# Demo RAG 实测记录

日期：2026-09-09。命令：`.venv/Scripts/python.exe -m scripts.evaluate_rag --real`，退出码 0。
真实本地 `intfloat/multilingual-e5-small` + persistent Chroma；collection_count=4，top_k=3，max_distance=0.143。没有调用 Chat Provider。

| 用例 | 实际 source | nearest distance | 结果 |
| --- | --- | --- | --- |
| pump-high-temperature-metal-friction | centrifugal-pump.md | 0.14008313417434692 | PASS |
| pump-cavitation-abnormal-vibration | centrifugal-pump.md | 0.10059165954589844 | PASS |
| motor-bearing-abnormal-noise | industrial-motor.md | 0.1081538200378418 | PASS |
| motor-overheating-vibration | industrial-motor.md | 0.1040692925453186 | PASS |
| sensor-reading-drift | temperature-sensor.md | 0.13861173391342163 | PASS |
| sensor-reading-jump-calibration | temperature-sensor.md | 0.09201633930206299 | PASS |
| vision-camera-disconnect | vision-controller.md | 0.1099621057510376 | PASS |
| vision-intermittent-image-loss | vision-controller.md | 0.11958354711532593 | PASS |
| pump-office-printer-wifi-toner | 无（拒绝） | 0.14624953269958496 | PASS |
| motor-browser-webpage | 无（拒绝） | 0.16055971384048462 | PASS |
| sensor-windows-password | 无（拒绝） | 0.17223137617111206 | PASS |
| vision-printer-paper-jam | 无（拒绝） | 0.16984045505523682 | PASS |

实际输出 `threshold=configured passed=12/12`。只证明当前十二条 Demo 检索用例符合预期，不能宣传为通用检索准确率、真实设备诊断成功率或生产 SLA。默认不带 `--real` 的 evaluator 使用 deterministic fake embeddings，不能替代本记录。

## 推荐症状的独立本地检索

另用相同配置的 RetrievalService，以 `Centrifugal Pump` 和原句“设备最近又出现和之前类似的异常振动，而且温度越来越高。”执行一次离线查询（HF_HUB_OFFLINE=1）：

```json
{"document":"centrifugal-pump.md","chunk_index":0,"distance":0.11062675714492798}
```

真实命中，距离小于 0.143。对应页面若收到同一 source 应显示 `centrifugal-pump.md · 片段 1`。这是本地检索结果，不是已执行的 Diagnosis API 响应，也不是已验证的页面 Sources；本轮真实 LLM 与页面 Sources 仍待授权验证。
