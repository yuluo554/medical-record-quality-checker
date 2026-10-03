# HANDOFF-M5（M4 收尾 → M5 编排与交付）

> 交接快照，写于 2026-10-03（M4 完成时）。新对话续接提示词：`/goal 读取 "plan\HANDOFF-M5.md" 继续完成任务`

## 1. 当前进度（M4 已完成 ✅）

- **LLM 客户端**：`src/mrqc/llm/client.py` 实现完毕（stdlib urllib POST、重试退避共 retries+1 次尝试、qwen 系 `enable_thinking=false`、`max_tokens` 透传）；失败纪律 = 一律抛 `LLMError`（未配置/超时/重试耗尽/4xx/JSON 不可解析），调用方降级；429/5xx/网络错误可重试、其余 4xx 不重试；`repair_truncated_json` 只回收已完整闭合的前缀元素（尾部标量不回收——可能是截断数字；字符串中段不闭合——闭合即伪造）；
- **兜底抽取管线**：`src/mrqc/llm/fallback.py`——触发 = 仅 `FieldValue.confidence < 0.8`（严格小于，既有低置信场景 = labs 文本型 item_name 0.6）；叶子白名单（知识派生/结构键不兜底）；候选行压缩（含数字或关键词，部件 80 行/总量 240 行上限）；逐条回验 = field 在请求集内 + source_part 已知部件 + **quote 逐字子串否则丢弃** + 数值范围表/时间格式校验；写回 confidence=0.8（=阈值不回环）；已接进 `mrqc check`（解析后、规则前，未配置静默）；
- **基准门槛化**：`mrqc benchmark detect` 已接进 CLI（干净误报 0 + 非预期结论 0 + 检出率 ≥0.95，未达标 exit 1）；`benchmarks/detect_paired.py` 默认门槛升为 0.95；`mrqc benchmark parse --min-f1`（默认 0.95）。**实测：parse F1=1.0000（TP=7664/FP=0/FN=0）守恒、检出率 100%（45/45）、干净误报 0、依据关联率 100%**；
- **README**：特性表/路线图 M0–M4 全 ✅；基准表格四行指标（parse F1 / 检出率 / 干净误报 / 依据关联率）+ 合成数据声明 + 免责声明保留 + 0 新增外链；
- 测试 **150 项全绿**（M4 新增 45：客户端 20（失败路径/请求契约/截断修复）/ 兜底管线 22（触发/压缩/回验/降级）/ CLI 接线 3），全部离线 mock 零 API 依赖；plan/00、05、06 回写完成；本地已提交。

## 2. M5 待办（编排与交付，DoD 见 plan/05 §5）

1. **`mrqc run` 端到端**：现在 run 只是 check 别名（--report 时 fail-fast exit 2）。改为 Pipeline 节点化编排（plan/03 §6：解析 → LLM 兜底（可选）→ 质控 → 汇总 → 导出），产出结论 JSON + 分级统计；pipeline/runner.py 骨架已就位（add_node/run/失败即停/CTX_TIMINGS）；
2. **docx 报告**：`src/mrqc/report/`（extra `report`=python-docx，惰性导入缺依赖给安装提示不崩）；内容含签署栏、免责声明、分级统计、依据关联（文号+条款+摘录）、结论清单（参考 eval/detect.render_markdown 的报告结构）；0 外链（docx 内不得引外部资源）；
3. **Web 面板**：`src/mrqc/web/`（extra `web`=fastapi+uvicorn+python-multipart）；免构建内联单页（CSS/JS 全内联，0 外链断网可演示）；multipart 上传部件 txt → 质控结论展示；`/docs`、`/redoc` 显式关闭（Swagger UI 引 CDN）；**真实上传冒烟必须做**（姊妹项目教训：multipart 缺依赖/上传路径不通都靠实跑才发现）；
4. **extras 守门**：report/web 运行期 import 必须被 `tests/test_extras_guard.py` 静态断言覆盖（防"静默少跑"；注意 pytest.importorskip 整模块跳过的坑——需要可选依赖的测试用显式 skip 原因并在 CI 装全 extras）；
5. **演示物**：报告样例（docx）+ 演示视频脚本；`mrqc demo` 路线图行更新（M5 完成后 report/web 状态行从 [--] 改 [ok]）；
6. 回归全绿 + plan/00、05、06 回写 + 写 HANDOFF-M6 + 本地提交。

## 3. 既定口径清单（动了会打挂基准/测试，改前先对照）

- **参数卡是唯一契约**：`src/mrqc/models/card.py` 改字段必须同步 truth 生成器、parse_f1、测试；
- **渲染↔解析共变**：render.py 是部件文本格式权威；改渲染必须重生成数据集 + verify 全过 + 解析同步；
- **注入/规则/基准三方共用 14 缺陷 ID 表**（plan/04 §7）：C-LAB-02 用 also_expect 携带 C-LAB-01；F-SIGN-01 注入的记录 C-SURG-02 按缺失跳过；
- **required_field 数据源**：规则消费解析层 parse_warnings，不在引擎重查部件文本；部件整体缺失不判；
- **need_confirm 计入非 pass**：待核对依据的缺陷以 need_confirm 检出算命中（F-TIME-03 现状）；评测对账 = 主缺陷必中 + also_expect 可选 + 期望外非 pass 即误报；
- **only_if 门控对全部 check_type 生效**；新增门控关键词必须与语料互斥（"输血"/"手术"有全语料污染，禁用）；
- severity 五值：LOW/MEDIUM/HIGH/CRITICAL/NEED_CONFIRM；多值/低置信度一律 NEED_CONFIRM；
- **parse_f1 指标口径已锁定**（plan/06）：知识派生路径排除（icd10、文本型检查行 item_name）、evidence 不入 F1、parse_warnings 不计分；**兜底管线不影响 parse 基准**（eval 层不调 LLM）；
- **检出指标口径**（plan/06 / eval/detect.py docstring）：need_confirm 计入非 pass；干净对照任何非 pass = 误报；缺陷记录期望外非 pass = 误报；门槛 = 干净误报 0 + 检出率 ≥0.95（`mrqc benchmark detect` 默认启用）；
- **LLM 纪律（M4 定稿，plan/06 四行）**：失败一律 LLMError 降级，数值结论永远来自确定性规则；截断修复只回收闭合前缀；兜底契约 = 白名单叶子 + quote 逐字回验 + 数值范围/时间格式校验 + 写回 confidence=0.8 不回环；接入点 = check/run 质控前，**parse 与基准保持纯规则确定性**；
- **基准零 API 依赖**：测试全离线（LLM 全 mock，`_http_post_json` 是 mock 点）；CI 不配 LLM 环境变量；
- 核心通路零第三方依赖；extras：report=python-docx / web=fastapi+uvicorn+python-multipart / dev=pytest；LLM 走 stdlib urllib；改依赖先过 `tests/test_extras_guard.py`；
- 指标门槛不放宽：parse F1 ≥0.95、干净集误报 0；
- 未实现模块 fail-fast exit 2；报告/Web/README 保留"非临床决策支持"免责声明与合成数据声明；**交付 0 外链**（docx 与 Web 页面内不得引外部资源）；
- DetRng 只依赖 `random.Random.random()`；数据集固定 seed（samples=20261003 / paired=20261004），重生成零 diff；
- 知识库由 `tools/build_knowledge.py` 生成——手改 blocks/rules JSON 会被重跑覆盖，改规则先改工具再重生成；
- 生成器 CLI：`py -X utf8 -m mrqc.datagen`；基准：`py -X utf8 benchmarks/parse_f1.py` / `benchmarks/detect_paired.py`。

## 4. 本机环境坑（只写实测过的）

- Python 3.8.8（`py` 启动器；`python` 是商店占位符）；中文输出一律 `py -X utf8`；跑 pytest 带 `PYTHONDONTWRITEBYTECODE=1`（本机 pyc 偶发损坏史）；
- **M4 新实录（崩溃阶梯有效）**：全量 pytest 连续两次在 stdlib `urllib.request` 导入期 access violation（sre_parse/sre_compile）——按 crash-loop-rescue 阶梯清 `__pycache__`（项目 + 系统 Python `lib/`）后单发重试即恢复；连续 2 崩即定性走阶梯，别刷重试；判定成败的命令**不接管道**（`| tail` 吃退出码）；
- **pytest `addopts = "-q"` 与命令行 `-q` 叠加成 `-q -q`**：summary 行（"N passed"）被吞——计数用 `pytest --collect-only -q` 汇总各文件数，或单跑文件看点数；全绿判定看真实退出码；
- **Windows Python 不认 `/tmp`**：Git Bash 的 `/tmp` 路径传给 py 读不到——落盘文件用 `cygpath -w` 转换或放仓库目录；
- **测试已 150 项**：分批纪律（每批 ≤50，按 test 文件分批跑）；最终验收跑一次全量（清缓存后实测 <5s）；
- agent-browser（浏览器自动化 CLI）：带 `--args` 的全新启动必挂起——用无参数启动；`eval --stdin`（heredoc）取逐字文本可靠；段错误(139)多为偶发，重试 1 次再定性（M5 Web 冒烟会用到）；
- webReader 类 MCP 工具返回**大模型友好摘要**（转述），不可当原文入库；本机访问 wikimedia 系与 web.archive.org 网络层不可达；
- pypdf 已装进系统 Python 3.8（dev 期工具，**不是项目依赖**，勿写进 pyproject）；
- pip 报 `127.0.0.1:7897` 代理错 → `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`（M5 装 python-docx/fastapi 时用）；
- git 提交前三核对：`pwd` + `git log --oneline -1` + `git remote -v`（防 cwd 漂移）；**远程仓库未建、未 push**（建仓/推送需用户授权，属 M6）。

## 5. DoD checklist

M4（已完成 ✅）：
- [x] LLM 客户端实现（urllib POST / 重试超时 / enable_thinking=false / JSON 截断修复），失败路径 mock 测试全绿
- [x] 兜底抽取管线（低置信触发 / 候选行压缩 / quote 逐字回验丢弃 / 数值范围丢弃）
- [x] parse F1 ≥0.95（1.0000 守恒，TP=7664/FP=0/FN=0）
- [x] e2e 检出基准达标并接进 CLI（干净误报 0 + 检出率 100%；门槛 0.95 默认启用）
- [x] 指标写入 README（基准表格 + 免责声明保留 + 0 外链）
- [x] 回归：全量测试全绿（150 项 = 105 + M4 新增 45）
- [x] plan/00、05、06 回写 ✅；写 HANDOFF-M5；本地提交

M5（执行时逐项打勾，未达成写偏差说明）：
- [ ] `mrqc run` 一条命令端到端（Pipeline 节点化：解析→兜底（可选）→质控→汇总→导出）
- [ ] docx 报告导出（签署栏 + 免责声明 + 分级统计 + 依据关联；0 外链；惰性导入缺依赖给提示）
- [ ] Web 面板（免构建内联单页 + multipart 上传 + 0 外链断网可演示 + `/docs` 关闭 + 真实上传冒烟）
- [ ] extras 守门测试覆盖 report/web 运行期 import
- [ ] 演示物：docx 报告样例 + 演示视频脚本
- [ ] 回归：全量测试全绿（150 项 + M5 新增）
- [ ] plan/00、05、06 回写 ✅；写 HANDOFF-M6；本地提交

## 6. 关键命令速查

```bash
cd <仓库根>
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m pytest          # 全量测试（150 项起步；-q -q 吞 summary，看 rc）
py -X utf8 -m mrqc demo                                  # 架构自检（6 解析器 + blocks 42 + rules 33 + LLM 状态）
py -X utf8 -m mrqc check --input data/paired/defect_C-LAB-02_01  # 质控 → 结论 JSON（含依据）
py -X utf8 -m mrqc benchmark parse                       # parse_f1 基准（门槛 0.95 默认启用）
py -X utf8 -m mrqc benchmark detect                      # e2e 检出基准（误报 0 + 检出率 ≥0.95）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 benchmarks/detect_paired.py --out benchmarks/m3_detect_report.md
py -X utf8 tools/build_knowledge.py                      # 重生成 blocks+rules（重跑零 diff）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m mrqc.datagen --verify data/samples data/paired
# LLM 兜底实测（可选，需真密钥；测试/基准永远 mock 不依赖）：
# export MRQC_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 MRQC_LLM_API_KEY=... MRQC_LLM_MODEL=qwen-plus
git status && git log --oneline -3 && git remote -v      # 提交前三核对
```

## 7. 开放问题（不阻塞，见 plan/06 待定决策表）

D-01 License / D-02 仓库 description+topics / D-03 是否投赛 / D-04 Python 底线 / D-05 仓库名微调——均按默认执行中，用户拍板后在 06 回写。M5 无阻塞设计点；LLM 供应商按 plan/06 既定（OpenAI 兼容 / DashScope qwen / enable_thinking=false / 密钥不入库），M5 报告与 Web 不新增 LLM 依赖点（兜底已就位，复核/行文属可选增强不在 DoD）。
