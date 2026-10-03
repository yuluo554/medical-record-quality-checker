# HANDOFF-M6（M5 收尾 → M6 发布与收尾固化）

> 交接快照，写于 2026-10-03（M5 完成时）。新对话续接提示词：`/goal 读取 "plan\HANDOFF-M6.md" 继续完成任务`

## 1. 当前进度（M5 已完成 ✅）

- **`mrqc run` 端到端**：`src/mrqc/pipeline/stages.py` 节点库（解析 → LLM兜底 → 质控 → 汇总 → 导出，plan/03 §6 落位；CLI check/run 与 Web 共用同源节点）；stdout = 单 JSON 对象（record_id/patient/findings/summary/parse_warnings/timings），stderr = 汇总行+耗时行；输入目录缺失 exit 1；`--report` 预检 docx 依赖 exit 2 给安装提示；
- **docx 报告**：`src/mrqc/report/__init__.py` export_report（首页免责声明 → 基本信息 → 分级统计 → 非通过结论逐条带文号+条款+条文摘录+病历证据+建议 → 通过项简表 → 质控/复核双签签署栏）；0 外链由测试扫描 docx 包 rels 断言无 External 守门；`docx_available()` 供 CLI 预检；
- **Web 面板**：`src/mrqc/web/`（create_app：/docs /redoc openapi 全关闭；内联单页 `_PAGE_HTML` 0 外链静态断言；`POST /api/check` multipart→临时目录→stages 同源管线；`GET /api/status`；`py -m mrqc.web` 启动，缺依赖 exit 2）；真实上传冒烟 = pytest 内 uvicorn 子进程 + stdlib urllib 手工 multipart（CI 必跑）+ curl 实传 + 浏览器 IAB 渲染/点击/状态拉取验证；
- **extras 守门扩展**：第三方运行期 import 收敛断言（docx→report/、fastapi/uvicorn→web/，其余模块经可用性探针）；测试不用 starlette TestClient（httpx 未声明依赖）；
- **演示物**：报告样例 `benchmarks/m5_report_sample.docx`（真实 run --report 产出）+ 演示视频脚本 `docs/demo_video_script.md`（7 镜头分镜+口播+录制检查单）；demo/README 状态行 M5 全 ✅；
- **测试 173 项全绿**（M5 新增 23：stages 6 / report 3 / web 7 / cli 4 / guard 3，全离线）；基准守恒：**parse F1=1.0000（TP=7664）、检出率 100%、干净误报 0、非预期 0、依据关联率 100%**，双门槛 rc=0；plan/00、05、06 回写完成；README 同步（特性表/命令一览/路线图/目录结构）。

## 2. M6 待办（发布与收尾固化，DoD 见 plan/05 M6 行 + ai-tool-project-sprint 阶段 7/8）

1. **脱敏四步**（逐项命令+结论留档到 `plan/RELEASE-M6.md`）：
   - `git ls-files | grep -iE "\.env$|\.key$|secret|token"` 应为空；核对 .gitignore 覆盖 .env/运行产物/个人材料；
   - 内容级扫描全部跟踪文本文件：`sk-` 密钥、手机号 `1[3-9]\d{9}`、身份证 `\d{17}[\dXx]`、个人路径 `C:\Users\`、内网 IP、邮箱——个人路径最爱藏在文档叙述里（HANDOFF 的环境坑段），扫出改占位符；
   - 二进制样例单独扫（git grep 跳过二进制）：`benchmarks/m5_report_sample.docx` 用 zipfile 扫全部 zip 条目（docProps/core.xml 的 creator/lastModifiedBy 是重灾区）；合成数据无真实个人信息，确认即可；
   - 提交元数据邮箱检查：`git log --format='%ae %ce' | sort -u`，公开仓库用 noreply 邮箱（`git config user.email` 现值入仓前决定）；
2. **干净环境验证**：新目录 clone + 全新 venv，逐条照 README 快速开始跑（pytest 收集数 173 与 dev 一致、demo/parse/check/run --report/web 冒烟/双基准 rc=0）；
3. **GitHub 发布（需用户授权）**：远程仓库未建未 push；建仓 → push → `gh repo edit --description --add-topic`（topics 候选见 plan/06 D-02）；
4. **版本固化（tag/release 需用户确认，可打包一次 multiSelect 确认）**：`git tag -a v0.1.0` + push tag + `gh release create`（notes = 基准表数值 + 演示命令摘要 + extras 说明）；
5. **发布物复核**：`gh repo view` + 重跑脱敏脚本 + README 渲染核验（WebFetch 超时改 `gh api`）；全量回归复跑 + 生成器 `--verify` 位级一致（git status 零变化）；
6. plan/00、05、06 回写 + 收尾交接文档落盘。

## 3. 既定口径清单（动了会打挂基准/测试，改前先对照）

- **参数卡是唯一契约**：`src/mrqc/models/card.py` 改字段必须同步 truth 生成器、parse_f1、测试；
- **渲染↔解析共变**：render.py 是部件文本格式权威；改渲染必须重生成数据集 + verify 全过 + 解析同步；
- 注入/规则/基准三方共用 14 缺陷 ID 表（plan/04 §7）；C-LAB-02 用 also_expect 携带 C-LAB-01；F-SIGN-01 注入的记录 C-SURG-02 按缺失跳过；
- required_field 数据源 = 解析层 parse_warnings；部件整体缺失不判；need_confirm 计入非 pass；
- only_if 门控对全部 check_type 生效；门控关键词与语料互斥（"输血"/"手术"禁用）；
- severity 五值：LOW/MEDIUM/HIGH/CRITICAL/NEED_CONFIRM；多值/低置信一律 NEED_CONFIRM；
- parse_f1 口径锁定（plan/06）：知识派生路径排除、evidence 不入 F1、parse_warnings 不计分；兜底不影响 parse 基准；
- 检出口径：干净对照任何非 pass = 误报；门槛 = 干净误报 0 + 检出率 ≥0.95 默认启用；
- **LLM 纪律（M4 定稿）**：失败一律 LLMError 降级；数值结论永远来自确定性规则；兜底契约 = 白名单叶子 + quote 逐字回验 + 数值范围/时间格式校验 + confidence=0.8 不回环；接入点 = check/run 质控前；
- **M5 新增口径**：
  - **run 输出契约**（plan/06）：stdout 单 JSON 对象（与 check 的数组形状有意区分）；exit：0 成功 / 1 流水线失败 / 2 --report 缺依赖；
  - **五节点 stages 库**（plan/06）：CLI/Web 同源；summarize 口径 = eval.detect 同源（need_confirm 计非 pass、分级分布只统计非 pass、无非 pass 依据关联率记 1.0；总体 fail > need_confirm > pass）；
  - **docx 0 外链**：测试扫描 .rels 断言无 `TargetMode="External"`（python-docx 默认模板无 External，实测确认）；报告/Web/README 保留免责声明与合成数据声明；
  - **Web**：docs/redoc/openapi 全 None；单页全内联（页面文本静态断言无 http(s):// 与外链标签）；multipart 是运行期依赖（守门锁定）；
  - **测试禁用 starlette TestClient**（httpx 未声明依赖会静默少跑）：单元直调端点函数 + HTTP 层 uvicorn 子进程冒烟（web extra 缺失显式 reason 跳过，CI 装全 extras 必跑）；
  - **extras import 收敛**：docx import 只准在 report/、fastapi/uvicorn 只准在 web/；其余模块经 `docx_available()`/`web_available()` 探针；
- **基准零 API 依赖**：测试全离线（LLM 全 mock，`_http_post_json` 是 mock 点）；CI 不配 LLM 环境变量；
- 核心通路零第三方依赖；extras：report=python-docx / web=fastapi+uvicorn+python-multipart / dev=pytest；
- 指标门槛不放宽：parse F1 ≥0.95、干净集误报 0；
- DetRng 只依赖 `random.Random.random()`；数据集固定 seed（samples=20261003 / paired=20261004）重生成零 diff；
- 知识库由 `tools/build_knowledge.py` 生成，手改 blocks/rules JSON 会被重跑覆盖。

## 4. 本机环境坑（只写实测过的）

- Python 3.8.8（`py` 启动器；`python` 是商店占位符）；中文输出一律 `py -X utf8`；跑 pytest 带 `PYTHONDONTWRITEBYTECODE=1`；
- 判定成败的命令**不接管道**（`| tail` 吃退出码）；pytest `addopts="-q"` 与命令行 `-q` 叠加吞 summary 行——计数用 `--collect-only` 或分批看点数，全绿判定看真实退出码；
- **M5 新实录**：
  - pip 装包：`NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`；py3.8 实际解析到 fastapi 0.124.4 / uvicorn 0.33.0 / python-docx 1.1.2；
  - **agent-browser 本机三连挂**（CDP DOM.enable 超时 / Chrome exited before DevTools URL / 命令挂起超时强杀），已弃用；改用 ZCode IAB（browser-use 插件）：**IAB evaluate 不执行页面代码**（返回 `{}`，副作用也不生效）、文件选择器不支持——页面级验证 = domSnapshot + locator click（点击处理器/渲染路径可验）；上传冒烟走 HTTP 级（uvicorn 子进程 + stdlib urllib 手工 multipart，或 curl -F）；
  - pytest 内起 uvicorn：subprocess `sys.executable -X utf8 -m mrqc.web` + PYTHONPATH=src + 空闲端口 socket 探测 + /api/status 轮询启动 + finally terminate——实测稳定 ~1s；
  - python-docx 默认模板无 External rels（0 外链断言可行）；患者信息/汇总在表格里，验文本要连 table cells 一起读；
  - 后台 uvicorn 落下的进程：`netstat -ano | grep :PORT` 找 PID 再 taskkill（会话恢复后后台任务可能已丢，但进程还在）；
- Windows Python 不认 `/tmp` 传给 py 的场景（Git Bash /tmp 可用于 bash 侧文件交换，传 py 参数用 `cygpath -w`）；
- git 提交前三核对：`pwd` + `git log --oneline -1` + `git remote -v`（防 cwd 漂移）；**远程仓库未建、未 push**（建仓/推送需用户授权，M6）。

## 5. DoD checklist

M5（已完成 ✅）：
- [x] `mrqc run` 一条命令端到端（五节点 Pipeline；结论 JSON + 分级统计；exit 0/1/2 契约）
- [x] docx 报告导出（签署栏 + 免责声明 + 分级统计 + 依据关联；0 外链 rels 断言；缺依赖预检 exit 2）
- [x] Web 面板（内联单页 + multipart 上传 + 0 外链 + `/docs` 404 + 真实上传冒烟 uvicorn/curl/浏览器三路）
- [x] extras 守门测试覆盖 report/web 运行期 import（收敛断言 + CI 装全 extras）
- [x] 演示物：docx 报告样例（benchmarks/m5_report_sample.docx）+ 演示视频脚本（docs/demo_video_script.md）
- [x] 回归：全量测试全绿（173 = 150 + M5 新增 23）；双基准门槛 rc=0 守恒
- [x] plan/00、05、06 回写 ✅；写 HANDOFF-M6；本地提交

M6（执行时逐项打勾，未达成写偏差说明）：
- [ ] 脱敏四步全过 + plan/RELEASE-M6.md 留档（含 docx 样例 zip 全条目扫描、提交元数据邮箱检查）
- [ ] 干净环境验证：新目录 clone + 全新 venv 按 README 逐条跑通（pytest 收集数 173 与 dev 一致）
- [ ] GitHub 建仓 + push + description/topics（**需用户授权**）
- [ ] tag v0.1.0 + release notes（**需用户确认**，可与 topics 打包一次确认）
- [ ] 发布物复核（gh api 元信息 + README 渲染核验 + 脱敏重扫）+ 全量回归复跑
- [ ] plan/00、05、06 回写 ✅；收尾交接文档落盘

## 6. 关键命令速查

```bash
cd <仓库根>
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m pytest          # 全量测试（173 项；看 rc）
py -X utf8 -m mrqc demo                                  # 架构自检（6 解析器 + blocks 42 + rules 33 + report/web 可用性）
py -X utf8 -m mrqc run --input data/paired/defect_C-LAB-02_01                 # 端到端五节点
py -X utf8 -m mrqc run --input data/paired/defect_C-LAB-02_01 --report benchmarks/m5_report_sample.docx  # + docx 报告
py -X utf8 -m mrqc benchmark parse                       # parse_f1 基准（门槛 0.95 默认启用）
py -X utf8 -m mrqc benchmark detect                      # e2e 检出基准（误报 0 + 检出率 ≥0.95）
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m mrqc.web --port 8765   # Web 面板（浏览器 127.0.0.1:8765；/docs 应 404）
py -X utf8 tools/build_knowledge.py                      # 重生成 blocks+rules（重跑零 diff）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m mrqc.datagen --verify data/samples data/paired
# 脱敏扫描（M6 起步）：
git ls-files | grep -iE "\.env$|\.key$|secret|token"
git grep -nIE "sk-[A-Za-z0-9]{8}|1[3-9][0-9]{9}|[0-9]{17}[0-9Xx]|C:\\\\Users\\\\" -- .
git log --format='%ae %ce' | sort -u
git status && git log --oneline -3 && git remote -v      # 提交前三核对
```

## 7. 开放问题（不阻塞，见 plan/06 待定决策表）

D-01 License（MIT 默认）/ D-02 仓库 description+topics（M6 发布前确认）/ D-03 是否投赛 / D-04 Python 底线（3.8 默认）/ D-05 仓库名微调——均按默认执行中，用户拍板后在 06 回写。M6 发布动作全部按 ai-tool-project-sprint 授权分级：建仓 push 需用户授权；tag/release/topics 需用户确认（可一次打包）；visibility/删仓/历史重写必须明确授权。
