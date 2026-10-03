# HANDOFF-M3（M2 收尾 → M3 知识与规则层）

> 交接快照，写于 2026-10-03（M2 完成时）。新对话续接提示词：`/goal 读取 "plan\HANDOFF-M3.md" 继续完成任务`

## 1. 当前进度（M2 已完成 ✅）

- **6 部件解析器**入库 `src/mrqc/parsers/`：admission.py（行式键值）、course.py（节式【标题】+时间行）、surgery.py、discharge.py、orders.py（行式医嘱，护理/禁食/饮食白名单跳过）、labs.py（数值条目 + 检查所见行）；注册表 `PARSERS` + `PART_ORDER`（= 渲染装配顺序，truth 下标对齐关键）+ `load_part_texts/parse_texts/parse_record_dir`；
- **parse_f1 基准**：指标实现 `src/mrqc/eval/parse_f1.py`（口径见其 docstring，已锁定 plan/06）+ 运行器 `benchmarks/parse_f1.py` + CLI `mrqc benchmark parse`。首版出数：**samples 60 份 P=R=F1=1.0000（TP=7664/FP=0/FN=0）；paired 54 份 F1=1.0000（TP=6933）**；证据逐字子串全量校验 0 违规；
- **告警机制**：未识别/重复部件、缺必备区块、未识别行 → `parse_warnings`，全程不抛异常；条件性区块（危急值处置/用血审批/手术各节）可缺不告警，CAP 5 部件零误报（测试锁定）；
- **对账结果**：解析卡与 truth.json 在文本可导出路径上**全等**（60+54 份）；仅 2 条知识派生路径按口径排除——`diagnoses[*].icd10`、文本型检查行 `item_name`（均不落部件文本，M3 知识库可派生补齐）；
- 测试 65 项全绿（M2 新增 32：全仓对账回归/告警行为/证据校验/指标口径/CLI 基准）；plan/00、05、06 回写完成；本地已提交。

## 2. M3 待办（知识与规则，DoD 见 plan/05 §5）

1. **blocks 入库** `data/knowledge/blocks/*.json`：从 `data/knowledge/raw/` 5 份规范摘条文块（block_id/文号/条号/原文/出处），台账登记进 data/README.md；查证优先于自证，查不到的时限值标"待核对"；
2. **rules 入库** `data/knowledge/rules/*.json`：规则 ≥30 条且**全部挂 basis**（schema plan/04 §3；无 basis 加载即 RuleError——特性不是 bug）；对照 plan/04 §7 缺陷 ID 表 14 个 ID 全部有对应规则，ID 不得改名；
3. **7 类 check_type 检查函数**：`RuleEngine._dispatch` 注册 required_field / timeliness / cross_consistency / medication_logic / lab_logic / signature_format / timeline_logic（现在调未实现 type 直接 NotImplementedError）；
4. **配对集检出首版报告**：跑 data/paired 54 份（defects.json 是评测期望：expect_status/also_expect），产出"结论清单（含分级+依据）"演示物；干净对照 ctrl_* 误报应为 0（M4 门槛，M3 先看数）；
5. **依据关联**：Finding.basis 来自规则 JSON；结论证据用参数卡 Evidence（已是逐字子串）；"待核对"依据只能出 NEED_CONFIRM；
6. **首版检出指标**记录进 plan/05 §5 M3 行。

M3 开工第一个设计点：required_field 类规则（F-REQ-01 缺主诉）的判定数据源——参数卡**没有**主诉字段（区块存在性校验在解析层），解析告警 `parse_warnings` 已含"入院记录缺少区块：主诉"；建议规则引擎读 parse_warnings 或由引擎传 part_texts 做存在性检查，M3 开工时定稿并记 plan/06。

## 3. 既定口径清单（动了会打挂基准/测试，改前先对照）

- **参数卡是唯一契约**：`src/mrqc/models/card.py` 改字段必须同步 truth 生成器、parse_f1、测试（M1 扩 TimelineEvent.detail、M2 未动 schema）；
- **渲染↔解析共变**：render.py 是部件文本格式权威；解析器逐行对照渲染实现（各解析器 docstring 记了对应渲染函数）；改渲染必须重生成数据集 + verify 全过 + 解析同步；
- **注入/规则/基准三方共用 14 缺陷 ID 表**（plan/04 §7）：C-LAB-02 用 also_expect 携带 C-LAB-01；F-SIGN-01 注入的记录 C-SURG-02 按缺失跳过（inject.py docstring 与 plan/06）；
- **only_if 门控对全部 check_type 生效**（引擎已实现，any_keyword 对部件原文全文匹配）；空 only_if = 无条件启用；
- severity 五值：LOW/MEDIUM/HIGH/CRITICAL/NEED_CONFIRM；多值/低置信度一律 NEED_CONFIRM；
- **parse_f1 指标口径已锁定**（plan/06）：知识派生路径排除、evidence 不入 F1（逐字校验单独守门）、parse_warnings 不计分——M4 LLM 兜底改造解析器时不得破坏；
- **基准零 API 依赖**：LLM 未配置即基准环境；测试全离线（LLM 用 mock）；
- 核心通路零第三方依赖（M2 解析/基准纯 stdlib 已验证）；extras：report=python-docx / web=fastapi+uvicorn+python-multipart / dev=pytest；LLM 走 stdlib urllib；改依赖先过 `tests/test_extras_guard.py`；
- 指标门槛不放宽：F1 ≥0.95、干净集误报 0（M4 验收）；
- 未实现模块 fail-fast exit 2；报告/README 保留"非临床决策支持"免责声明与合成数据声明；交付 0 外链；
- DetRng 只依赖 `random.Random.random()`；数据集固定 seed（samples=20261003 / paired=20261004），重生成零 diff；
- 生成器 CLI：`py -X utf8 -m mrqc.datagen`；基准：`py -X utf8 benchmarks/parse_f1.py`（--min-f1 门槛模式 M4 用）。

## 4. 本机环境坑（只写实测过的）

- Python 3.8.8（`py` 启动器；`python` 是商店占位符）；中文输出一律 `py -X utf8`；跑 pytest 带 `PYTHONDONTWRITEBYTECODE=1`（本机 pyc 偶发损坏史）；
- **测试已 65 项**：分批纪律生效（每批 ≤50，按 test 文件分批跑）；最终验收跑一次全量（本机实测 1.7s 无压力）；
- **Windows Python 不认 `/tmp`**：Git Bash 的 `$TEMP` 传给 py 会变 `/tmp/...` 找不到文件——用 `WTEMP=$(cygpath -w "$TEMP")` 再拼进 `r'$WTEMP\\file'`；
- agent-browser（浏览器自动化 CLI）：**带 `--args` 的全新启动必挂起**——用无参数启动；`close --all` 后立即重启也可能挂，sleep 几秒再试；`eval --stdin`（heredoc）取 `document.body.innerText`/`.con` 容器逐字文本可靠；段错误(139)多为偶发，重试 1 次再定性；
- NHC 官网 WAF：curl/WebFetch 全被 412 挑战页拦；浏览器渲染可过；**附件 `files/` 路径无 WAF，curl 可直下**；
- webReader 类 MCP 工具返回**大模型友好摘要**（转述），不可当原文入库；其 -400 报错是"抓取失败"笼统提示；本机访问 wikimedia 系与 web.archive.org 网络层不可达；
- pypdf 已装进系统 Python 3.8（dev 期 PDF 文本层提取用，**不是项目依赖**，勿写进 pyproject）；
- pip 报 `127.0.0.1:7897` 代理错 → `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`；
- git 提交前三核对：`pwd` + `git log --oneline -1` + `git remote -v`（防 cwd 漂移）；**远程仓库未建、未 push**（建仓/推送需用户授权，属 M6）。

## 5. DoD checklist

M2（已完成 ✅）：
- [x] 多部件解析器对 data/samples 60 份全部产出参数卡（CAP 5 部件不误报）
- [x] parse_f1 首版指标出数并记录（plan/05 §5 M2 行：P=R=F1=1.0000，TP=7664）
- [x] 解析告警机制生效（未知部件/缺区块 → parse_warnings，异常不外抛）
- [x] 证据摘录逐字子串约束实测（114 份解析卡+truth 卡全量校验 0 违规）
- [x] 回归：全量测试全绿（65 项 = 既有 28 + M2 新增 37）
- [x] plan/00、05、06 回写 ✅；写 HANDOFF-M3；本地提交

M3（执行时逐项打勾，未达成写偏差说明）：
- [ ] blocks 条文块入库（5 份规范 → data/knowledge/blocks/，台账登记）
- [ ] rules ≥30 条全部挂 basis（14 缺陷 ID 全覆盖，文号与 raw 台账一致）
- [ ] 7 类 check_type 检查函数全部实现（dispatch 注册，不抛 NotImplementedError）
- [ ] 配对集 54 份检出首版报告（defects.json 期望对账；含分级+依据）
- [ ] 干净对照 12 份误报 = 0（首版数据，M4 门槛复核）
- [ ] 回归：全量测试全绿（65 项 + M3 新增）
- [ ] plan/00、05、06 回写 ✅；写 HANDOFF-M4；本地提交

## 6. 关键命令速查

```bash
cd <仓库根>
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m pytest          # 全量测试（65 项起步）
py -X utf8 -m mrqc demo                                  # 架构自检（6 解析器已注册）
py -X utf8 -m mrqc parse --input data/samples/cap_001/   # 解析 → 参数卡 JSON（含证据）
py -X utf8 -m mrqc benchmark parse                       # parse_f1 基准（samples 60 份）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 benchmarks/parse_f1.py --data data/paired --min-f1 0.95
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m mrqc.datagen --verify data/samples data/paired
git status && git log --oneline -3 && git remote -v      # 提交前三核对
```

## 7. 开放问题（不阻塞，见 plan/06 待定决策表）

D-01 License / D-02 仓库 description+topics / D-03 是否投赛 / D-04 Python 底线 / D-05 仓库名微调——均按默认执行中，用户拍板后在 06 回写。M3 新增：required_field 规则数据源设计点（见 §2 第 6 条）。
