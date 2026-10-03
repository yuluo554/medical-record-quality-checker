# medical-record-quality-checker 项目计划总览

**项目**：出院病历内涵质控智能审核系统（医疗领域）
**方法论**：ai-tool-project-sprint（plan 先行 → 数据先行 → 解析/规则/LLM → 基准 → 编排交付 → 脱敏发布）
**项目系列**：construction-drawing-plan-checker（建造，已发布）→ power-operation-ticket-checker（电力，题目定稿）→ 本项目（医疗，题目定稿）

## 文档索引

| 文档 | 内容 | 状态 |
|---|---|---|
| [01-题目详细定义.md](01-题目详细定义.md) | 模拟赛题全文（介绍/任务/提交材料/评分/含金量锚点/边界） | ✅ 定稿 2026-10-03 |
| [02-需求解读.md](02-需求解读.md) | 痛点→能力转译表、FR 功能清单（带优先级）、边界与非目标 | ✅ 定稿 2026-10-03 |
| [03-架构与技术选型.md](03-架构与技术选型.md) | 分层架构、技术栈、LLM 供应商 | ✅ 定稿 2026-10-03 |
| [04-模块详设.md](04-模块详设.md) | 解析器/病历参数卡 schema/规则引擎/知识库 schema/缺陷注入对照表 | ✅ 定稿 2026-10-03 |
| [05-数据计划与里程碑.md](05-数据计划与里程碑.md) | 合成病历生成器设计、M0-M6 里程碑（每周可演示） | ✅ 定稿 2026-10-03 |
| [06-决策记录.md](06-决策记录.md) | 重大决策表（权威表）+ 待定决策表 | ✅ 建立并持续追加 |
| [HANDOFF-M1.md](HANDOFF-M1.md) | M0 收尾交接快照（M1 待办/既定口径/环境坑/DoD/命令速查） | ✅ 2026-10-03 |
| [HANDOFF-M2.md](HANDOFF-M2.md) | M1 收尾交接快照（M2 待办/既定口径/环境坑/DoD/命令速查） | ✅ 2026-10-03 |
| [HANDOFF-M3.md](HANDOFF-M3.md) | M2 收尾交接快照（M3 待办/既定口径/环境坑/DoD/命令速查） | ✅ 2026-10-03 |
| [HANDOFF-M4.md](HANDOFF-M4.md) | M3 收尾交接快照（M4 待办/既定口径/环境坑/DoD/命令速查） | ✅ 2026-10-03 |

## 决策记录

已迁移至 [06-决策记录.md](06-决策记录.md)（权威表，含待定决策 D-01~D-05），以 06 为准。

## 里程碑

- ✅ **M0 计划+骨架**（2026-10-03 完成）：plan 02–06 定稿；可运行骨架（包 `mrqc`，参数卡契约/规则引擎骨架/流水线/CLI/extras 守门测试，21 项测试全绿，CI 3.8/3.10/3.12 就位）
- ✅ **M1 数据先行**（2026-10-03 完成）：3 病种模板入库；生成器 `src/mrqc/datagen/`（固定 seed、部件 txt+truth.json、14 缺陷 ID 注入配对集）+ 对账脚本；samples 60 + paired 42+12，truth 对账与位级可复现（815 文件 sha256 零变化）通过；5 份规范官网原文入库 `data/knowledge/raw/`；台账登记齐全（[data/README.md](../data/README.md)）；33 项测试全绿
- ✅ **M2 解析层**（2026-10-03 完成）：6 部件解析器 `src/mrqc/parsers/`（规则优先、证据逐字摘录、告警不外抛、CAP 无手术记录不误报）+ parse_f1 基准（`mrqc benchmark parse` / `benchmarks/parse_f1.py`，samples 60 份 P=R=F1=1.0000 首版、paired 54 份同分；指标口径见 plan/06）+ 证据逐字子串全量校验 0 违规；65 项测试全绿
- ✅ **M3 知识与规则**（2026-10-03 完成）：知识库三层补齐（blocks 42 条文块程序化摘取自 raw 保逐字 + rules 33 条全挂 basis，14 缺陷 ID 全覆盖、7 类 check_type 全注册，only_if 门控对真实规则生效）；`mrqc/eval/detect.py` 配对集检出评测：**主缺陷检出率 100%（45/45，含 F-TIME-03 以 need_confirm 形式检出）、干净对照 12 份误报 0、非预期结论 0、依据关联率 100%**（首版报告 `benchmarks/m3_detect_report.md`）；required_field 数据源定稿（消费解析层 parse_warnings，plan/06）；105 项测试全绿
- ⬜ M4 LLM 兜底 + 内置基准：LLM 客户端（降级/防幻觉）、e2e 检出基准门槛化（检出率门槛 + 误报 0）、解析 F1 ≥0.95
- ⬜ M5 编排与交付：CLI + docx 质控报告 + Web 面板（0 外链）
- ⬜ M6 脱敏发布 GitHub + 收尾固化（tag/release/topics）
