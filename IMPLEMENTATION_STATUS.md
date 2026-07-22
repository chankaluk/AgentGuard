# AgentGuard 优化实施状态

更新时间：2026-07-22

## 已完成

- 原始压缩包保持不变，优化内容全部位于本目录；旧派生成品不再强制要求保留 `archive_pre_optimization` 目录。
- 修复一键脚本退出码、PowerShell 5.1 解析、最佳模型快照、checkpoint 安全加载、ROC-AUC 内存复杂度、无界面绘图和服务输入上限。
- 离线与流式窗口统一；流式路径增加活跃实体 LRU 上限。
- 自建数据增加困难正常样本、实体隔离和横向移动场景留出；生成元信息包含文件 SHA-256。
- 查表、顺序规则、Transformer 和实际混合链路分层评测；CLI、流式分析和 Web 均使用相同混合入口。
- 自主命题赛道口径已同步到 README、设计、数据指南、报告、答辩稿、清单和 Web 页面。
- 已基于保留的 `work-report-template.docx` 生成唯一主报告；删除“填写说明”页后结构为 9 节，并用 `PAGE/NUMPAGES` 动态域替换固定“共7页”。报告明确区分 Transformer、透明顺序规则和混合系统，补强三项创新与 Recall/F1/FPR 关系说明。
- 已使用 `@oai/artifact-tool` 继承原 12 页 PPT 模板，完成 102 处文本更新和 4 处图片替换；逐页渲染、模板忠实度和内部 XML 检查通过。
- 已更新本地 Web 控制台并实跑截图，页面分别展示混合分、模型分、规则分和首要原始事件。
- 系统使用说明已补入“系统启动与主界面、日志输入示例、告警结果页面、模型分/规则分/证据链”四类图示；最终 Word/PPT 的作者、最后修改者和组织属性已清空。
- 依赖已精确锁定；新增模型权重来源说明和 `PROJECT_HANDOFF.md`，可供新聊天快速接手并从零部署。
- 完整流水线已验证：数据生成、基线、训练、评估、34 项测试、材料生成、项目验证和最终打包全部成功。

## 当前指标

数据范围：自建可复现增强工程基准，400 个测试序列，不代表真实部署效果。

| 方法 | 检出率 | 误报率 | F1 | ROC-AUC |
|---|---:|---:|---:|---:|
| 异常专属词元查表 | 0.00% | 0.00% | 0.000 | 0.500 |
| Transformer 单模型 | 65.00% | 15.33% | 0.616 | 0.834 |
| 透明顺序规则 | 84.00% | 0.00% | 0.913 | 0.920 |
| 实际混合告警链路 | 97.00% | 15.33% | 0.798 | 0.971 |

## 最终验收

1. `scripts/verify_project.py`：`pass`，35 个必需文件/提交物全部存在，0 个错误。
2. `run_all.ps1`：退出码 0；34 项测试全部通过；最终压缩包已生成。
3. PPT：12 页逐页渲染检查通过；模板忠实度检查 `pass`、0 个问题；幻灯片 XML 中 0 个空占位符。画布检测仅报告第 1 页右上装饰圆超出边界，该元素来自原模板且属于预期裁切。
4. Word：结构回读通过；主报告为 9 节、至少 2 张表和 3 幅图片，系统使用说明含 4 幅界面证据图，动态页码域和自动更新设置存在，作者元数据为空。本机无 LibreOffice；Microsoft Word 隐藏导出曾卡死，已终止对应隐藏进程且未损坏报告，因此不声称 Word 逐页视觉检查通过。

## 关键文件与哈希

- 主报告：`submission/作品报告_AgentGuard_自主命题模板版.docx`
  - SHA-256：`C8B105567E81F2194FF708742D36508CE6532AA2755D3FE6BEC357252657D0D3`
- 系统使用说明：`submission/系统使用说明_AgentGuard.docx`
  - SHA-256：`9CEB51580162AFBD16BAB0ED3BB7BB481C30BE9374180F065DC3367213535F32`
- 最终 PPT：`submission/答辩PPT_AgentGuard_自主命题最终版.pptx`
  - SHA-256：`A38984546761C7CD59E4CA6087E99682A62F9EC2415FD1AF8EF9DA5B1A236E1C`
- 模型：`artifacts/agentguard.pt`
  - SHA-256：`D131C219FB00041EA5F96DCC38967346A6EFBDFC4BE4F7BC83D5D3FE6BEC357252657D0D3`
- 指标：`artifacts/evaluation/metrics.json`
  - SHA-256：`205B01F22B57561A13AAC10E7DF437B3AF5FAECB9524330DD137CB1DCA719F0F`
- 数据元信息：`data/demo/metadata.json`
  - SHA-256：`4891B59304E386C0E3584388D66DF19E08E2C8AE99C250E590890BC1C29FA05B`
- 完整参赛包：`AgentGuard_完整参赛项目.zip`
  - 最终 SHA-256 以包外的 `submission/完整包_SHA256.json` 为准，避免压缩包内容自引用哈希。

## 复现命令

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_env.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_all.ps1
```

第二条命令会依次完成数据、训练、评估、测试、材料生成、项目验证与打包。
