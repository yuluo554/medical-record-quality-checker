# HANDOFF-M4（M3 收尾 → M4 LLM 兜底与基准达标）

> 交接快照，写于 2026-10-03（M3 完成时）。新对话续接提示词：`/goal 读取 "plan\HANDOFF-M4.md" 继续完成任务`

## 1. 当前进度（M3 已完成 ✅）

- **知识库三层补齐**：blocks 42 条文块（`data/knowledge/blocks/`，5 份规范各一文件）+ rules 33 条（`formal_rules.json` 12 / `integrity_rules.json` 21）。全部由 `tools/build_knowledge.py` 从 raw 原文**程序化摘取**（重跑零 diff），规则 basis 按（文号,条款）从 blocks 取同一文本；`tests/test_knowledge.py` 双向守门（引文 ⊆ raw 原文 / 规则依据 ≡ blocks 条目 / 文号与台账一致）；
- **规则库**：14 缺陷 ID 全覆盖（plan/04 §7 对账锚，未改名）；全部挂 basis（无 basis 加载即 RuleError）；7 类 check_type 全注册（`src/mrqc/rules/checks.py`，引擎 RULE_DISPATCH）；手术类规则挂 only_if ["手术记录"]、F-TIME-03 挂 ["术后首次病程记录"]，门控对真实规则生效；
- **判定纪律落地**：数据不足一律 pass 不硬判；basis.status=待核对 → 只出 need_confirm（现仅 F-TIME-03"即时"→2h 阈值一条待核对；F-TIME-01/02 的 24h/8h 已从 11 号文原文核对升级为已核对硬判）；C-SURG-02 术者签名缺失时按约定跳过（归 F-SIGN-01）；"输血"字样因"未输血"全语料出现，用血识别走参数卡 purpose 字段不走关键词；
- **配对集检出首版**：`mrqc/eval/detect.py`（实现入库）+ `benchmarks/detect_paired.py`（CLI 壳，含 --min-detection-rate 门槛模式预置）。**主缺陷检出率 100%（42/42 份全命中，45 条非 pass 结论 = 42 主缺陷 + 3 条 C-LAB-02 隐含 C-LAB-01）、干净对照 12 份误报 0、非预期结论 0、依据关联率 100%**；分级分布 CRITICAL 6 / HIGH 36 / NEED_CONFIRM 3；演示报告 `benchmarks/m3_detect_report.md`；
- **CLI**：`mrqc check` 传 part_texts（门控+部件级判定需要）并输出结论统计；`mrqc demo` 展示真实知识库计数（raw=6 / blocks=42 / rules=33）；
- 测试 **105 项全绿**（M3 新增 40：知识库不变量 10 / 七类检查行为 25 / 配对集回归 4 / 既有测试更新 1）；plan/00、04、05、06 回写完成；本地已提交。

## 2. M4 待办（LLM 兜底 + 基准达标，DoD 见 plan/05 §5）

1. **LLM 客户端**：`src/mrqc/llm/client.py` 骨架已就位（stdlib urllib、环境变量配置、`llm_available()`）——实现 `chat()`：OpenAI 兼容 chat/completions POST、重试与超时、qwen 系 `enable_thinking=false`、max_tokens 截断 JSON 修复（截断修复纪律见骨架 docstring）；
2. **兜底抽取管线**：触发条件 = 仅 `FieldValue.confidence < 阈值` 字段（解析层现在恒 1.0，注意构造低置信场景做测试：可仿 labs 文本型 item_name confidence=0.6 的既有模式）；候选行压缩（只送含数字/关键词的行）；输出契约 `{field, source_part, quote}`——**quote 不是该部件原文子串即丢弃**；数值字段超合法性范围丢弃；
3. **降级路径 mock 测试全绿**：未配置 / 超时 / 重试耗尽 / JSON 损坏（含截断）→ 全部走纯规则通路；测试全离线（LLM 用 mock，基准零 API 依赖）；
4. **e2e 检出基准门槛化**：`benchmarks/detect_paired.py --min-detection-rate` 已预置；M4 定正式门槛运行（干净误报 0 + 检出率 ≥0.95，首版已 100%），并把 e2e_detect 基准接进 `mrqc benchmark` CLI（现在 benchmark 只有 parse 子命令）；
5. **parse_f1 守恒**：LLM 兜底改造解析器时不得破坏 M2 锁定的 parse_f1 口径（plan/06 知识派生路径排除、evidence 不入 F1、parse_warnings 不计分）——跑 `mrqc benchmark parse` 确认 F1=1.0000 不回退；
6. **指标写入 README**：README 增加基准表格（parse F1 / 检出率 / 干净误报 / 依据关联率），注明合成数据与"非临床决策支持"声明；保留 0 外链。

## 3. 既定口径清单（动了会打挂基准/测试，改前先对照）

- **参数卡是唯一契约**：`src/mrqc/models/card.py` 改字段必须同步 truth 生成器、parse_f1、测试（M1 扩 TimelineEvent.detail、M2/M3 未动 schema）；
- **渲染↔解析共变**：render.py 是部件文本格式权威；改渲染必须重生成数据集 + verify 全过 + 解析同步；
- **注入/规则/基准三方共用 14 缺陷 ID 表**（plan/04 §7）：C-LAB-02 用 also_expect 携带 C-LAB-01；F-SIGN-01 注入的记录 C-SURG-02 按缺失跳过（inject.py docstring 与 plan/06）；
- **required_field 数据源定稿**（plan/06）：规则消费解析层 parse_warnings（"X缺少区块：Y"），不在引擎重查部件文本；部件整体缺失不判；
- **need_confirm 计入非 pass**（plan/06）：待核对依据的缺陷以 need_confirm 检出算命中；评测期望对账 = 主缺陷必中 + also_expect 可选 + 期望外非 pass 即误报；
- **only_if 门控对全部 check_type 生效**（引擎已实现，any_keyword 对部件原文全文匹配）；空 only_if = 无条件启用；新增门控关键词必须与语料互斥（"输血"/"手术"等词有全语料污染，禁用，见 plan/06）；
- severity 五值：LOW/MEDIUM/HIGH/CRITICAL/NEED_CONFIRM；多值/低置信度一律 NEED_CONFIRM；
- **parse_f1 指标口径已锁定**（plan/06）：知识派生路径排除、evidence 不入 F1（逐字校验单独守门）、parse_warnings 不计分；
- **检出指标口径**（plan/06 / eval/detect.py docstring）：need_confirm 计入非 pass；干净对照任何非 pass = 误报；缺陷记录期望外非 pass = 误报；M4 门槛 = 干净误报 0 + 检出率 ≥0.95；
- **基准零 API 依赖**：LLM 未配置即基准环境；测试全离线（LLM 用 mock）；
- 核心通路零第三方依赖（解析/规则/评测纯 stdlib 已验证）；extras：report=python-docx / web=fastapi+uvicorn+python-multipart / dev=pytest；LLM 走 stdlib urllib；改依赖先过 `tests/test_extras_guard.py`；
- 指标门槛不放宽：parse F1 ≥0.95、干净集误报 0（M4 验收）；
- 未实现模块 fail-fast exit 2；报告/README 保留"非临床决策支持"免责声明与合成数据声明；交付 0 外链；
- DetRng 只依赖 `random.Random.random()`；数据集固定 seed（samples=20261003 / paired=20261004），重生成零 diff；
- 知识库由 `tools/build_knowledge.py` 生成（blocks 引文程序化摘取 raw；规则 basis 从 blocks 取文）——**手改 blocks/rules JSON 会被构建脚本重跑覆盖**，改规则先改工具再重生成；
- 生成器 CLI：`py -X utf8 -m mrqc.datagen`；基准：`py -X utf8 benchmarks/parse_f1.py` / `benchmarks/detect_paired.py`。

## 4. 本机环境坑（只写实测过的）

- Python 3.8.8（`py` 启动器；`python` 是商店占位符）；中文输出一律 `py -X utf8`；跑 pytest 带 `PYTHONDONTWRITEBYTECODE=1`（本机 pyc 偶发损坏史）；
- **测试已 105 项**：分批纪律生效（每批 ≤50，按 test 文件分批跑）；最终验收跑一次全量（本机实测 <3s 无压力）；
- **Windows Python 不认 `/tmp`**：Git Bash 的 `$TEMP` 传给 py 会变 `/tmp/...` 找不到文件——用 `WTEMP=$(cygpath -w "$TEMP")` 再拼进 `r'$WTEMP\\file'`；
- agent-browser（浏览器自动化 CLI）：**带 `--args` 的全新启动必挂起**——用无参数启动；`close --all` 后立即重启也可能挂，sleep 几秒再试；`eval --stdin`（heredoc）取 `document.body.innerText`/`.con` 容器逐字文本可靠；段错误(139)多为偶发，重试 1 次再定性；
- NHC 官网 WAF：curl/WebFetch 全被 412 挑战页拦；浏览器渲染可过；**附件 `files/` 路径无 WAF，curl 可直下**；
- webReader 类 MCP 工具返回**大模型友好摘要**（转述），不可当原文入库；其 -400 报错是"抓取失败"笼统提示；本机访问 wikimedia 系与 web.archive.org 网络层不可达；
- pypdf 已装进系统 Python 3.8（dev 期 PDF 文本层提取用，**不是项目依赖**，勿写进 pyproject）；
- pip 报 `127.0.0.1:7897` 代理错 → `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`；
- git 提交前三核对：`pwd` + `git log --oneline -1` + `git remote -v`（防 cwd 漂移）；**远程仓库未建、未 push**（建仓/推送需用户授权，属 M6）。

## 5. DoD checklist

M3（已完成 ✅）：
- [x] blocks 条文块入库（5 份规范 → 42 块 data/knowledge/blocks/，台账登记 data/README §四）
- [x] rules ≥30 条全部挂 basis（33 条；14 缺陷 ID 全覆盖，文号与 raw 台账一致）
- [x] 7 类 check_type 检查函数全部实现（dispatch 注册，不抛 NotImplementedError）
- [x] 配对集 54 份检出首版报告（defects.json 期望对账；含分级+依据，`benchmarks/m3_detect_report.md`）
- [x] 干净对照 12 份误报 = 0（首版数据，M4 门槛复核）
- [x] 回归：全量测试全绿（105 项 = 既有 65 + M3 新增 40）
- [x] plan/00、04、05、06 回写 ✅；写 HANDOFF-M4；本地提交

M4（执行时逐项打勾，未达成写偏差说明）：
- [ ] LLM 客户端实现（urllib POST / 重试超时 / enable_thinking=false / JSON 截断修复），失败路径 mock 测试全绿
- [ ] 兜底抽取管线（低置信触发 / 候选行压缩 / quote 逐字回验丢弃 / 数值范围丢弃）
- [ ] parse F1 ≥0.95（当前 1.0000，改造后不回退）
- [ ] e2e 检出基准达标并接进 CLI（干净误报 0 + 检出率 ≥0.95；首版已 100%/0）
- [ ] 指标写入 README（基准表格 + 免责声明保留 + 0 外链）
- [ ] 回归：全量测试全绿（105 项 + M4 新增）
- [ ] plan/00、05、06 回写 ✅；写 HANDOFF-M5；本地提交

## 6. 关键命令速查

```bash
cd <仓库根>
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m pytest          # 全量测试（105 项起步）
py -X utf8 -m mrqc demo                                  # 架构自检（6 解析器 + blocks 42 + rules 33）
py -X utf8 -m mrqc parse --input data/samples/cap_001/   # 解析 → 参数卡 JSON（含证据）
py -X utf8 -m mrqc check --input data/paired/defect_C-LAB-02_01  # 单份质控 → 结论 JSON（含依据）
py -X utf8 -m mrqc benchmark parse                       # parse_f1 基准（samples 60 份）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 benchmarks/detect_paired.py --out benchmarks/m3_detect_report.md
PYTHONDONTWRITEBYTECODE=1 py -X utf8 benchmarks/parse_f1.py --data data/paired --min-f1 0.95
py -X utf8 tools/build_knowledge.py                      # 重生成 blocks+rules（重跑零 diff）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m mrqc.datagen --verify data/samples data/paired
git status && git log --oneline -3 && git remote -v      # 提交前三核对
```

## 7. 开放问题（不阻塞，见 plan/06 待定决策表）

D-01 License / D-02 仓库 description+topics / D-03 是否投赛 / D-04 Python 底线 / D-05 仓库名微调——均按默认执行中，用户拍板后在 06 回写。M4 新增无阻塞设计点；LLM 供应商按 plan/06 既定（OpenAI 兼容 / DashScope qwen / enable_thinking=false / 密钥不入库）。
