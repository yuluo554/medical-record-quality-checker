# HANDOFF-M2（M1 收尾 → M2 解析层）

> 交接快照，写于 2026-10-03（M1 完成时）。新对话续接提示词：`/goal 读取 "plan\HANDOFF-M2.md" 继续完成任务`

## 1. 当前进度（M1 已完成 ✅）

- **3 病种模板**入库 `data/templates/`：cap.json（内科用药型）、appendicitis.json（外科手术型）、gallstone.json（外科手术+用血变体）；
- **生成器全链路** `src/mrqc/datagen/`：rng.py（DetRng 确定性随机）→ spec.py（模板→记录规格，身份池/时间槽位/药物/检验/手术/危急值/用血）→ inject.py（14 缺陷 ID 注入器，对照 plan/04 §7）→ render.py（6 部件 txt 渲染 + 参数卡真值）→ verify.py（对账）→ `__main__.py`（CLI）；
- **数据集**已生成并对账通过：`data/samples/` 60（每病种 20）+ `data/paired/` 42（14 ID ×3）+12 干净对照；同 seed 重跑 815 文件 sha256 零变化（位级可复现实测）；
- **5 份规范官网原文**入库 `data/knowledge/raw/`（4 份 txt 逐字提取 + 2021 病案指标三件套：通知 txt/官方 PDF 原件/文本层 txt）；文号差异澄清（31号确认，见 plan/06）；
- **契约扩展**：`models/card.py` TimelineEvent 增加 `detail` 字段；新增 `knowledge/drugs.py` 药物字典（datagen 真值与 M2 解析共用 is_antibiotic/antibiotic_level）；`knowledge_dir()` parents[3] bug 修复；
- 测试 33 项全绿（M1 新增 12 项：位级复现/对账/注入 ID 表锁定/药物字典交叉验证/时间轴词汇等）；data/README.md 台账登记齐全；plan/00、05、06 回写完成。

## 2. M2 待办（解析层，DoD 见 plan/05 §5）

1. **多部件解析器** `src/mrqc/parsers/`：部件识别（base.py `detect_part` 已有标题关键词版，可增强）→ 各部件行式/节式抽取 → RecordCard（含 Evidence 逐字摘录）；
2. **渲染格式权威 = `datagen/render.py`**：解析正则/抽取逻辑必须对照渲染实现逐行适配（入院记录行式键值、病程记录【时间】节式、手术记录键值、出院记录键值、医嘱单行式、检验条目行"指标 数值 单位 ↑↓（参考范围 …）"，危急值标"（危急值，…）"）；改渲染必须同步解析；
3. **parse_f1 基准**：解析卡 ↔ truth.json 逐字段对比出数（plan/04 §2 指标口径），对 data/samples 60 份出首版指标并记录；
4. **告警机制**：未识别部件、缺关键区块 → `parse_warnings`，不抛异常；CAP 无手术记录部件属正常（5 部件），不得误报；
5. **药物派生**：is_antibiotic/antibiotic_level 从 drugs.py 派生（与生成器同源，不许另写第二套字典）；
6. 注意：`paired/` 的 truth.json 是**注入后文档**的真值（抽取自实写内容），解析层对账用它；defects.json 是评测期望，与解析无关（M4 用）。

## 3. 既定口径清单（动了会打挂基准/测试，改前先对照）

- **参数卡是唯一契约**：`src/mrqc/models/card.py` 改字段必须同步 truth.json 生成器、parse_f1 基准、`tests/test_card.py`（M1 已扩展 TimelineEvent.detail，先例照做）；
- **渲染↔解析共变**：render.py 是部件文本格式的权威定义，改渲染必须同步解析与位级复现测试（重生成数据集 + verify 全过）；
- **注入/规则/基准三方共用缺陷 ID 表**（plan/04 §7，14 个 ID），不得单方改名；C-LAB-02 用 also_expect 携带 C-LAB-01；F-SIGN-01 注入的记录 C-SURG-02 按缺失跳过（约定见 inject.py docstring 与 plan/06）；
- 规则 JSON schema（plan/04 §3）：无 basis 的规则 `RuleEngine` 加载即抛 `RuleError`——特性不是 bug；
- `only_if` 门控对全部 check_type 生效；空 only_if = 无条件启用；
- severity 五值：LOW/MEDIUM/HIGH/CRITICAL/NEED_CONFIRM；多值/低置信度一律 NEED_CONFIRM；
- **基准零 API 依赖**：LLM 未配置即基准环境；测试全离线（LLM 用 mock）；
- 核心通路零第三方依赖；extras：report=python-docx / web=fastapi+uvicorn+python-multipart / dev=pytest；LLM 走 stdlib urllib 无独立 extra；改动依赖先过 `tests/test_extras_guard.py`（M2 解析器禁止引入第三方库）；
- 指标门槛不放宽：F1 ≥0.95、干净集误报 0（M4 验收，M2 先出首版数）；
- 未实现模块 fail-fast exit 2（CLI 惯例），不伪造成功；
- 报告/README 必须保留"非临床决策支持"免责声明与合成数据声明；交付 0 外链；
- DetRng 只依赖 `random.Random.random()`；数据集固定 seed（samples=20261003 / paired=20261004），重生成必须零 diff；
- 生成器 CLI：`py -X utf8 -m mrqc.datagen`（模块入口；正式 `mrqc` 命令留给主流程）。

## 4. 本机环境坑（只写实测过的）

- Python 3.8.8（`py` 启动器；`python` 是商店占位符）；中文输出一律 `py -X utf8`；跑 pytest 带 `PYTHONDONTWRITEBYTECODE=1`（本机 pyc 偶发损坏史）；
- **Windows Python 不认 `/tmp`**：Git Bash 的 `$TEMP` 传给 py 会变 `/tmp/...` 找不到文件——用 `WTEMP=$(cygpath -w "$TEMP")` 再拼进 `r'$WTEMP\\file'`；
- agent-browser（浏览器自动化 CLI）：**带 `--args` 的全新启动必挂起**——用无参数启动（真实 Chrome 通过 NHC WAF 的实测配置）；`close --all` 后立即重启也可能挂，sleep 几秒再试；`eval --stdin`（heredoc）取 `document.body.innerText`/`.con` 容器逐字文本可靠；段错误(139)多为偶发，重试 1 次再定性；
- NHC 官网 WAF：curl/WebFetch 全被 412 挑战页拦；浏览器渲染可过；**附件 `files/` 路径无 WAF，curl 可直下**；
- webReader 类 MCP 工具返回的是**大模型友好摘要**（转述），不可当原文入库；其 -400 报错是"抓取失败"的笼统提示，不是 URL 格式问题；本机访问 wikimedia 系（wikipedia/wikisource）与 web.archive.org 网络层不可达；
- pypdf 已装进系统 Python 3.8（dev 期 PDF 文本层提取用，**不是项目依赖**，勿写进 pyproject）；
- pip 报 `127.0.0.1:7897` 代理错 → `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`；
- 测试 33 项一次跑完无压力；分批纪律（每批 ≤50）从测试数超过 50 起执行；
- git 提交前三核对：`pwd` + `git log --oneline -1` + `git remote -v`（防 cwd 漂移）；**远程仓库未建、未 push**（建仓/推送需用户授权，属 M6）。

## 5. DoD checklist

M1（已完成）：
- [x] 3 病种模板入库（cap/appendicitis/gallstone）
- [x] 生成器固定 seed 位级可复现（815 文件 sha256 零变化实测；测试守门）
- [x] samples 60、paired 14 ID ×3 + 干净对照 12（DoD 原文"12 类注入"按 plan/04 §7 定稿口径实为 14 ID，超额）
- [x] truth.json ↔ RecordCard 对账脚本通过（--verify 全绿）
- [x] 规范 raw 入库 5 份 + 台账登记齐全（官网原文，条款连续性零缺号抽验）
- [x] plan/00、05、06 回写 ✅；写 HANDOFF-M2；本地提交

M2（执行时逐项打勾，未达成写偏差说明）：
- [ ] 多部件解析器对 data/samples 60 份全部产出参数卡（CAP 5 部件不误报）
- [ ] parse_f1 首版指标出数并记录（记录进 plan/05 §5 M2 行或 README）
- [ ] 解析告警机制生效（未知部件/缺区块 → parse_warnings，异常不外抛）
- [ ] 证据摘录逐字子串约束实测（Evidence quote 对部件原文全量校验）
- [ ] 回归：全量测试全绿（33 项 + M2 新增）
- [ ] plan/00、05、06 回写 ✅；写 HANDOFF-M3；本地提交

## 6. 关键命令速查

```bash
cd <仓库根>
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m pytest          # 全量测试（33 项起步）
py -X utf8 -m mrqc demo                                  # 架构自检
py -X utf8 -m mrqc parse --input data/samples/cap_001/  # 解析（M2 实现目标）
# 重新生成数据集（改 render/spec 后必须重跑并 verify + git diff 零变化）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m mrqc.datagen --out data/samples --count 60 --seed 20261003
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m mrqc.datagen --out data/paired --paired --per-defect 3 --clean-controls 12 --seed 20261004
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m mrqc.datagen --verify data/samples data/paired
git status && git log --oneline -3 && git remote -v      # 提交前三核对
```

## 7. 开放问题（不阻塞，见 plan/06 待定决策表）

D-01 License 确认 / D-02 仓库 description+topics / D-03 是否投赛 / D-04 Python 底线 / D-05 仓库名微调——均按默认执行中，用户拍板后在 06 回写。
