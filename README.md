# AgentGuard：基于行为序列建模的 AI Agent 异常检测系统

AgentGuard 是自主命题赛道的完整参赛工程，选题属于 AI 衍生安全方向。系统把 AI Agent 的输入、工具调用、记忆和权限行为，与主机进程、网络、文件、注册表事件统一编码为行为序列；实际告警链路采用轻量 Transformer 与透明顺序规则融合，并为每条告警输出关键事件、原始日志证据和自然语言解释。

> 数据声明：本赛道没有组委会提供的训练集或测试集。`data/demo` 是固定随机种子生成的自建增强工程基准，只用于证明代码、训练、评估和演示链路可复现，不能代表生产环境效果。项目同时披露简单基线、模型单独结果、规则单独结果和混合系统结果。

新电脑或新聊天接手时，先阅读 [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md)；模型来源、校验值和精确依赖见 [`docs/09_模型权重与依赖说明.md`](docs/09_模型权重与依赖说明.md)。

## 当前可复现实验结果

测试集共 400 个行为序列，其中 100 个异常、300 个正常；划分采用实体隔离和异常场景留出，并加入包含相同高风险词元但顺序无害的困难正常样本。

| 方法 | 检出率 | 误报率 | F1 | ROC-AUC |
|---|---:|---:|---:|---:|
| 异常专属词元查表 | 0.00% | 0.00% | 0.000 | 0.500 |
| Transformer 单模型 | 65.00% | 15.33% | 0.616 | 0.834 |
| 透明顺序规则 | 84.00% | 0.00% | 0.913 | 0.920 |
| 实际混合告警链路 | **97.00%** | **15.33%** | **0.798** | **0.971** |

混合方式为 `max(Transformer 分数, 顺序规则分数)`。该结果说明当前工程基准中透明规则很强；因此项目不把 97% 误写为 Transformer 单模型成绩，也不据此声称真实部署性能。

## 证据链

- `artifacts/evaluation/metrics.json`：三组检测指标与性能指标；
- `artifacts/evaluation/baselines.json`：非学习基线；
- `artifacts/evaluation/alerts.jsonl`：混合分数、模型分数、规则分数与原始证据；
- `data/demo/metadata.json`：数据生成设置、场景留出和文件 SHA-256；
- `tests/`：窗口一致性、数据质量、安全边界、checkpoint 和无界面绘图测试。

## 环境与一键复现

支持 Windows 10/11 与 macOS（Intel、Apple Silicon），推荐 Python 3.11 或 3.12。首次安装：

Windows PowerShell：

```powershell
cd "解压后的\AgentGuard"
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_env.ps1
```

macOS 终端：

```bash
cd "解压后的/AgentGuard"
./setup_env.sh
```

完整复现：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_all.ps1
```

```bash
./run_all.sh
```

脚本依次生成数据、计算基线、训练、评估、测试、生成材料并打包；任一子步骤失败都会停止。它不会在运行中擅自安装依赖。已有模型时启动本地演示：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1
```

```bash
./run_demo.sh
```

浏览器访问 `http://127.0.0.1:8080`。服务默认只监听本机。

## 输入与数据接入

每行一个 JSON 事件，最低必填字段为 `timestamp`、`entity_id`、`event_type`、`action`：

```json
{"timestamp":"2026-06-01T09:00:00Z","entity_id":"agent-01","source":"agent","event_type":"tool","action":"read","object_type":"file","object_name":"project.md","result":"success"}
```

标签仅用于训练和评估，线上检测不依赖 `label`、`scenario` 或 `risk_hint`。CSV 转换和流式分析示例：

```powershell
.\.venv\Scripts\python.exe scripts\convert_csv.py raw.csv data\local\test.jsonl --mapping configs\csv_mapping.example.json
.\.venv\Scripts\python.exe scripts\analyze_stream.py data\local\test.jsonl --max-active-entities 10000 --output artifacts\local_alerts.jsonl
```

macOS 将上面命令中的 `.\.venv\Scripts\python.exe` 换成 `.venv/bin/python`，并将参数中的反斜杠换成 `/`。

如需实体匿名化，必须显式传入由队伍自行保管的随机盐；不要把盐或真实日志提交进压缩包。

## 核心方法

1. 按实体和时间构建长度 24、步长 8 的重叠窗口，离线和流式代码共享同一窗口定义。
2. 将来源、事件类型、动作、对象类型和结果编码为行为词元，并加入时间间隔、昼夜周期、执行结果等连续特征。
3. Tiny Transformer 同时执行窗口分类与下一事件预测，生成模型异常分数。
4. 透明规则只识别有顺序约束的典型高风险行为链；实际告警取模型和规则两者较高分。
5. 告警分别保存混合分数、模型分数和规则分数，并用注意力、惊异度与原始事件提供复核线索。

流式分析器对单实体事件窗口和活跃实体数量都设置上限；实体被 LRU 回收前会输出可用尾窗口。生产环境应按并发实体规模调整上限并监控回收率。

## 项目结构

```text
00_比赛原始材料/          原压缩包随附材料，仅作归档；其中定向赛资料不适用于本项目
configs/                  模型与训练配置
data/demo/                自建可复现增强工程基准
src/agentguard/           数据、模型、训练、推理与解释核心代码
scripts/                  生成、训练、评估、服务和材料脚本
tests/                    自动化测试
web/                      本地可视化演示台
artifacts/                模型、指标、告警和实验图
docs/                     设计、数据、文献、答辩和风险说明
submission/               最终提交物
```

## 合规与提交前检查

- 系统仅用于合法、授权、可控环境中的防御检测，不包含攻击执行模块。
- 原始数据默认不出本机；账号、路径、地址和密钥应在展示前脱敏。
- 初赛匿名材料不要出现学校、院系、教师或队员身份信息。
- 报告中的自建基准数字必须与 `metrics.json` 一致；真实环境验证需单独分表。
- 队员必须逐文件理解、运行和复核 AI 辅助形成的内容，并按当届规则如实披露。
- 提交前人工下载并核对官网最新版自主命题赛道指南、作品模板和原创性要求。
