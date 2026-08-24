# AgentGuard 新聊天交接与重新部署手册

> 这是本项目的新会话入口和事实基线。打开新聊天时，请先让 AI 完整阅读本文件、`README.md`、项目根目录的 `AGENTS.md`（如存在）、`规则文档.md`（如存在）与 `踩坑日记.md`，再检查当前文件和测试，避免凭旧描述重复返工。

## 1. 项目身份与目标

- 赛道：自主命题赛道；没有组委会提供的数据集或定向赛题资料。
- 题目：基于行为序列建模的 AI Agent 异常检测系统。
- 项目名：AgentGuard。
- 目标：把 AI Agent 的输入、规划、工具调用、记忆和权限行为，与主机进程、网络、文件和注册表事件统一为行为序列，检测跨事件异常并输出可复核证据。
- 定位：防御检测原型和可复现实验工程，不是攻击工具，也不是已经通过生产验证的安全产品。

## 2. 已确定的技术方案

1. 事件按实体与时间排序，切分为长度 24、步长 8 的重叠窗口。
2. 离散词元包含来源、事件类型、动作、对象类型和结果；连续特征包含时间间隔、昼夜周期、执行结果和对象长度等。
3. Tiny Transformer 同时执行窗口分类和下一事件预测，得到模型分数。
4. 透明顺序规则识别需要先后关系的高风险行为链，得到规则分数。
5. 最终混合分为 `max(Transformer 分数, 透明顺序规则分数)`，告警分别保存模型分、规则分、混合分、解释、关键事件与原始日志。

三项核心创新的统一表述是：

- Agent 与主机双域联合建模；
- 模型分数与透明安全规则双证据融合；
- 面向 AI Agent 安全的困难负样本与场景留出。

## 3. 当前指标

当前结果来自固定随机种子 2026 生成的自建增强工程基准。测试集 400 条序列，其中异常 100、正常 300；它只验证工程闭环，不能代表真实部署效果。

| 方法 | Recall | FPR | F1 | ROC-AUC |
|---|---:|---:|---:|---:|
| 异常专属词元查表 | 0.00% | 0.00% | 0.000 | 0.500 |
| Transformer 单模型 | 65.00% | 15.33% | 0.616 | 0.834 |
| 透明顺序规则 | 84.00% | 0.00% | 0.913 | 0.920 |
| 实际混合告警链路 | 97.00% | 15.33% | 0.798 | 0.971 |

混合链路检出 97 个异常、漏报 3 个，同时误报 46 个正常序列，Precision 为 67.83%。因此 Recall 很高但 F1 只有 0.798；当前阈值偏向降低漏报，真实部署必须按角色和处置成本重新校准。97% 不能写成 Transformer 单模型成绩。

指标事实源：`artifacts/evaluation/metrics.json`、`artifacts/evaluation/baselines.json` 和 `data/demo/metadata.json`。

## 4. 关键目录与文件

```text
configs/default.json                 模型、窗口、训练与阈值配置
data/demo/                           固定种子自建数据及数据哈希
src/agentguard/                      数据、模型、训练、推理、规则与解释核心代码
scripts/generate_demo_data.py        生成演示数据
scripts/train.py                     本地训练权重
scripts/evaluate.py                  评测、告警和实验图
scripts/generate_submission_docs.py  生成使用说明等材料
scripts/build_report_from_template.py 基于官方模板生成作品报告
scripts/verify_project.py            最终项目结构与提交物验收
scripts/package_project.py           生成完整提交压缩包与哈希
tests/                               自动化测试
web/                                 本地演示台
artifacts/agentguard.pt              本地训练权重
submission/                          最终提交材料与完整包
docs/09_模型权重与依赖说明.md        权重来源、SHA-256 与依赖版本
docs/10_前沿方案对照与补强路线.md    前沿论文、成熟 GitHub 工程和补强路线
docs/11_评委通俗讲解稿.md            给评委解释项目的 30 秒/2 分钟话术
docs/12_三类真实补充数据输入输出说明.md 本机正常、可控安全测试、公共样本输入输出
configs/*_mapping.example.json       Agent trace、osquery、Wazuh/Falco 接入映射模板
```

原始比赛材料保留在 `00_比赛原始材料/`，其中定向赛资料不适用于本自主命题项目，不应作为项目指标或数据来源。

## 5. 从零部署

支持 Windows 10/11 与 macOS（Intel、Apple Silicon），推荐 Python 3.11 或 3.12，CPU 和 8 GB 内存即可完成演示。项目路径可改变；命令不要依赖当前电脑的绝对路径。

Windows：

```powershell
cd "解压后的\AgentGuard"
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_env.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_all.ps1
```

`setup_env.ps1` 创建 `.venv` 并安装 `requirements.txt` 中的精确版本。`run_all.ps1` 依次执行数据生成、基线、训练、评测、测试、材料生成、项目验收与打包；任一环节失败即停止。

macOS：

```bash
cd "解压后的/AgentGuard"
./setup_env.sh
./run_all.sh
```

对应的 `.sh` 脚本与 Windows 流程执行相同步骤。

启动演示：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1
```

macOS 执行 `./run_demo.sh`。

浏览器访问 `http://127.0.0.1:8080`。服务默认仅监听本机。若 8080 被占用，Windows 可运行 `.\.venv\Scripts\python.exe scripts\serve.py --port 8081`，macOS 可运行 `./run_demo.sh --port 8081`。

## 6. 重新生成与验收

只重跑测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

macOS 以下各命令将 `.\.venv\Scripts\python.exe` 替换为 `.venv/bin/python`。

只验收当前项目与提交物：

```powershell
.\.venv\Scripts\python.exe scripts\verify_project.py
```

只重新生成材料与压缩包：

```powershell
.\.venv\Scripts\python.exe scripts\generate_submission_docs.py
.\.venv\Scripts\python.exe scripts\verify_project.py
.\.venv\Scripts\python.exe scripts\package_project.py
```

`submission/答辩PPT_AgentGuard_自主命题最终版.pptx` 为可选提交物；材料脚本只清除其作者元数据，不重建幻灯片内容。作品报告页脚使用 Word 的 `PAGE/NUMPAGES` 动态域，打开后如显示未刷新，请按 `Ctrl+A`、`F9` 更新全部域。

## 7. 最终材料与人工待办

最终以项目根目录 `AgentGuard_完整参赛项目.zip` 为交付入口，并用 `submission/完整包_SHA256.json` 校验。主要材料包括作品报告、答辩 PPT、带四类界面证据的系统使用说明、原创性声明、最终提交清单以及源码、模型、测试和实验产物。

提交前必须人工完成：

- 填写报告电子邮箱和日期；
- 按比赛要求签署、盖章原创性声明；
- 用 Microsoft Word 打开报告，更新目录和页码域并逐页检查换页；
- 用 PowerPoint 全屏检查字体、图片、动画或视频兼容性；
- 按官网当届最新通知复核匿名、命名、大小和提交渠道；
- 队员逐文件理解并如实披露 AI 辅助内容。

## 8. 已知限制

- 数据全部为自建模板化工程基准，规模有限，尚无授权真实环境轨迹验证。
- Transformer 单模型在场景留出下仍有明显泛化不足；混合结果很大程度受透明规则贡献。
- 当前混合系统误报率为 15.33%，不宜直接用于自动阻断。
- 注意力与下一事件惊异度是复核线索，不构成因果解释。
- JSONL 适配层仍需针对真实 EDR、审计或 Agent 框架字段定制。
- 已新增 Agent trace、osquery、Wazuh/Falco 映射模板，并补充本机正常、可控安全测试、Loghub 公共样本三类输入；这些数据用于接入证明，不替代 `data/demo` 的指标。
- 生产化还需身份认证、TLS、权限隔离、日志脱敏、审计、漂移监控和高并发压力测试。

## 9. 新聊天快速指令

可把下面这段交给新聊天中的 AI：

> 请先完整阅读 `PROJECT_HANDOFF.md`、`README.md`、`docs/10_前沿方案对照与补强路线.md`、`docs/11_评委通俗讲解稿.md`、`docs/12_三类真实补充数据输入输出说明.md`，再检查 `git status`、`IMPLEMENTATION_STATUS.md`、`artifacts/evaluation/metrics.json` 与现有测试。项目是自主命题赛道 AgentGuard，不使用组委会数据。以当前文件为事实源，只做最小必要改动；修改后运行全部测试、`scripts/verify_project.py`，重新生成并校验提交包，不要把 97% 误写成 Transformer 单模型成绩。

新聊天若要重新部署，应先执行第 5 节命令；若只继续优化，应先读取本节列出的事实源，再确认未完成事项。内部历史计划目录不进入最终提交包。
