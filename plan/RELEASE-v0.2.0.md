# RELEASE-v0.2.0（二次迭代发布留档，2026-10-21 执行 / 2026-10-22 收尾）

> 本次为 M3 二次迭代的发布留档。口径与决策见 [06-决策记录.md](06-决策记录.md) 2026-10-21 各行；
> 终态快照见 [HANDOFF-FINAL.md](HANDOFF-FINAL.md) §7；执行明细见仓库外 `update/03-执行记录.md`
> （`update/` 已入 `.gitignore`，含本机绝对路径，不入公共仓）。
>
> 留档纪律（沿用 RELEASE-M6）：本文件**不复述本机敏感字面值**；发布数值同时写入
> tag 消息、Release 说明与 `SHA256SUMS` 附件——台账在 zip 内不能自述自身 sha256。

## 1. 本次发布解决什么

**P0（唯一）：装成 wheel 后工具退化成永远说「通过」的空壳。**

| 观测点 | 改前（v0.1.0） | 改后（v0.2.0） |
|---|---|---|
| `knowledge_dir()` 装态解析 | `<venv>/Lib/data/knowledge`（**不存在**） | `<site-packages>/mrqc/knowledge/data` |
| `knowledge_status()` | `{'raw':0,'blocks':0,'rules':0}` | `{'raw':0,'blocks':42,'rules':33}` |
| `mrqc check --input <真实病历>` | `findings: []`，`[结论] 共 0 条规则参评`，**rc=0** | `findings: 33`，`[结论] 共 33 条规则参评`，rc=0 |
| `mrqc run` 汇总行 | `总体结论：通过 ｜ 参评规则 0 条`，rc=0 | `总体结论：… ｜ 参评规则 33 条`，rc=0 |
| wheel 内 `data/` 条目 | **0** | **7**（5 blocks + 2 rules） |

根因三件套：`knowledge_dir()` 用 `parents[3]`（源码态 = 仓根，wheel 态 = `Lib`）、
`pyproject` 无 `package-data`、无 `MANIFEST.in`；再叠加 `RuleEngine.load` 空目录返回空
与 `summarize` 空 findings 判 pass → 静默降级为「通过」。

**为什么测试没抓住**：`tests/test_knowledge.py` 的 `KNOWLEDGE = knowledge_dir()` 在仓库内跑
时 `parents[3]` 恰好正确；全仓没有一条测试在 site-packages 上下文里断言知识库可用。

## 2. 修复与加固（逐条可复跑）

| # | 动作 | 验证命令与结果 |
|---|---|---|
| 1 | `blocks/rules` `git mv` 进包 `src/mrqc/knowledge/data/`（9 条目，`raw/` 不动） | `knowledge_status()` → `{'raw':0,'blocks':42,'rules':33}` |
| 2 | `knowledge_dir()` 改包内相对；新增 `raw_dir()`（仓内 raw，供测试核对引文） | `test_block_quotes_are_verbatim_substrings_of_raw` 绿 |
| 3 | `pyproject` 加 `[tool.setuptools.package-data]` `"mrqc.knowledge"` | wheel `data/` 条目 0 → **7** |
| 4 | 新增 `MANIFEST.in`（sdist 自足；raw 进 sdist 不进 wheel） | sdist 条目 79 → **1070**；解包后测试 32 failed → **0** |
| 5 | `cli` 的 `check`/`run`：规则库 0 条 → 打印错误并 **rc=2** | 负控（临时改名 rules）：check rc=2 / run rc=2，stdout 0 字节 |
| 6 | 新增 `tests/test_packaging.py`（4 项） | 包内定位 / 42·33 / package-data 声明 / 5+2 文件 |
| 7 | `pyproject` 加 `pythonpath = ["src"]` | sdist 里 pytest 导入解包树自己的 src（不导入已装副本） |
| 8 | `cli._force_utf8_stdio()`（非 UTF-8 流切 UTF-8） | `PYTHONIOENCODING=cp1252 mrqc demo` → 改前 rc=1 崩、改后 **rc=0**；守门 `tests/test_cli_encoding.py` |
| 9 | 新增 `tools/ci_packaging_gate.py` + CI 步骤（构建 wheel → 全新 venv 不带 `-e` → 仓外验活） | 本地跑通：`{'raw':0,'blocks':42,'rules':33}` / findings 33 / `PACKAGING GATE OK` |
| 10 | 支持面：floor `>=3.8` → `>=3.12`、PEP 639、classifiers 只留 3.12、CI 双 OS × 3.12、actions v7 | wheel METADATA：`2.4` / `License-Expression: MIT` / `License-File: LICENSE` / `Requires-Python: >=3.12` |
| 11 | 33 条规则 basis + 42 个条文块挂复核锚（块层补 `status`） | `md5sum -c` 重跑 `tools/build_knowledge.py` **7/7 OK**（生成器不会抹掉锚） |
| 12 | README：M6 两处 ⬜→✅ + 发布状态行 + 三徽章 + sdist 说明 + 测试数（自指守门） | `grep "⬜" README.md` 零命中；`grep -c "!\["` = 3 |
| 13 | 清洁度：删空目录 `code/`、`.gitignore` 加 `update/`、订正 815 口径、版本单一来源守门 | `test_version_single_source.py` 负控（改 9.9.9 → 红） |

## 3. 验收（四处一致）

| 环境 | 命令 | 结果 |
|---|---|---|
| 仓库（dev） | `python -m pytest -o addopts=""` | **192 passed / 0 skipped** |
| 干净 clone + 全新 venv | 同上（`pip install -e ".[dev,web,report]"`） | **190 passed**（当时数，与 README 自指门一致）→ 最终 192 |
| sdist 解包 | 同上 | **192 passed / 0 failed** |
| Release 下载件 | 同上（sdist 解包后） | **192 passed / 0 skipped / 0 failed** |
| Release 下载件（wheel） | `mrqc check` | **findings 33**，`knowledge_status` 42·33，`mrqc 0.2.0` |

业务命令（干净 clone）：`--version` / `demo` / `parse` / `check` / `run --report` /
`benchmark parse` / `benchmark detect` **全 rc=0**。

基准零退化：

```
parse  {"n_records":60,"f1":1.0,"tp":7664,"fp":0,"fn":0,...}
detect {"detection_rate":1.0,"clean_false_positives":0,"unexpected_findings":0,
        "basis_linkage_rate":1.0,"n_non_pass_findings":45,
        "severity":{"CRITICAL":6,"HIGH":36,"NEED_CONFIRM":3}}
```

冻结数据零变化：`git diff --stat 3178d45..<发布提交> -- data/samples data/paired data/knowledge/raw` → **空**。

构建零弃用：`python -m build --sdist --wheel` 后 `grep -ci deprecat` → **0**。

## 4. CI

| run | 提交 | 结果 |
|---|---|---|
| 39629662669 | `f78e95d`（首轮） | ubuntu **success** / windows **failure** |
| 39631204466 | `d67d37d`（修复后） | 两腿 **success** |
| 39632221679 | `60f7f09`（README 转正后，**tag 指向此提交**） | 两腿 **success**，windows 0 条注解 / ubuntu 1 条 |

**首轮 windows 腿失败的完整原因**（本轮最有价值的发现）：

```
File "...\src\mrqc\cli.py", line 79, in _cmd_demo
  print("mrqc %s —— 出院病历内涵质控智能审核系统（骨架自检）" % __version__)
File "...\Lib\encodings\cp1252.py", line 19, in encode
UnicodeEncodeError: 'charmap' codec can't encode characters in position 14-33
```

190 项测试全过（测试期捕获输出，不写控制台），但 `mrqc demo` 崩 → rc=1。
这正是「CI 只有 ubuntu 一个 OS 维度」掩盖的真缺陷；加 windows 腿第一轮就抓到。

ubuntu 那 1 条注解是 GitHub 侧推送的
`The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19, 2026.`
（非本仓配置引起；Node20 弃用注解已归零）。
**该注解同时是对「floor 抬到 3.12」决策的旁证**：3.8.18 无 linux-26.04 构建，
钉在 3.8 会让 CI 在迁移后必然变红。

## 5. 发布物（三方 sha256 一致：本地 = GitHub digest = tag 消息）

| 附件 | 大小 | sha256 |
|---|---|---|
| `mrqc-0.2.0-py3-none-any.whl` | 116,186 B | `f90320b9469117b7c83c3f7d8af01a0e2f3dbcde34464f10fa5a7c241ee198e2` |
| `mrqc-0.2.0.tar.gz` | 1,033,299 B | `b800a1797382b7c32e86032fb2bf57b2273cad024cfb30d871a1f88fd0a2ce4c` |
| `SHA256SUMS` | 178 B | （内容即上面两行，格式 `sha256␠␠文件名`，无 `*`） |

- tag：`v0.2.0`（annotated）→ `60f7f09e6500b4ef14b47833bd6d9b51d17005c7`
- Release：https://github.com/yuluo554/medical-record-quality-checker/releases/tag/v0.2.0
- 复核方式：`gh api -H "Accept: application/octet-stream" .../releases/assets/<id>` 下载后
  `sha256sum -c SHA256SUMS` → 两行 `OK`；再装该 wheel，仓外目录复验 42·33 与 findings 33。
- 未上传 PyPI（本仓历来不发）。

## 6. 一次自我更正（如实留档）

首次把 `v0.2.0` 打在 `d67d37d` 上。随后发现**该提交的 wheel 内嵌 README 仍写
「v0.1.0 已发布」**（连带 `-X utf8` 旧建议）——典型「README 转正在 tag 之后」失效模式。

处置：因该 tag 建立仅数分钟、无任何拉取，**删除本地与远端 tag、改打在 `60f7f09`**
（README 转正后的提交，CI 两腿全绿），并重建 Release 三个附件；tag 消息内已写明更正。
校验：`git rev-parse v0.2.0^{}` = `60f7f09`；下载件 METADATA 内嵌 README 为
`✅ 状态：v0.2.0 已发布` 版。

附件字节变化来源：README 变长 → whl 116,086 → 116,186 B；tar.gz 1,033,066 → 1,033,299 B。

## 6.1 tag 之后的文档提交（如实登记，不改写 tag）

发布后 2026-10-22 做收尾回写（本文档、plan/06 决策、plan/00 里程碑与索引、plan/05 DoD 行、
HANDOFF-FINAL §7、README 状态行补本文档链接）。由此产生 **tag 之后 1 个文档提交**，
判定为可接受，理由与口径：

- 该提交**只改文档**（`plan/` 与 `README.md`），**不改任何代码/数据/构建配置**，
  故不改变发布物行为，不构成「发布物与源码不一致」；
- **不重指 tag**：v0.2.0 已发布且可能被拉取，重指会让已下载者与仓库状态分叉
  （上一节的重指是「建立数分钟、无人拉取」的特例，不可复用）；
- **副作用（如实披露）**：Release 附件内嵌的 `README.md`（wheel METADATA）是 **tag 时刻版本**，
  其状态行为「…发布留档见 `plan/RELEASE-M6.md`」，**不含**本文档链接。属文档级陈旧，
  非事实错误（RELEASE-M6 确实是有效的发布留档，只是对应 v0.1.0）。下次发版时自然消除。
- 回归口径：`git rev-list --count v0.2.0..HEAD` 在收尾提交后为 **1**；后续每次发版前
  须确认该计数只由文档提交构成。

## 7. 本轮不做 / 未做

- 33 条规则的 `type/params/only_if/severity/suggestion_template` 未改；
  `F-TIME-03` 的 `basis.status` 仍「待核对」（如实披露）。
- 两个基准的四个门槛（F1≥0.95 / 检出率≥0.95 / 干净误报 0 / 非预期结论 0）未动。
- `data/samples`(401) / `data/paired`(416) / `data/knowledge/raw`(6) 字节未动。
- `benchmarks/m3_detect_report.md`、`benchmarks/m5_report_sample.docx` 未动。
- `tools/build_knowledge.py` 的**切分逻辑**未动（只改输出路径与复核锚字段）。
- 未实现 OCR；未发 PyPI。

## 8. 需要人工确认的（机器判据覆盖不到）

- **领域语义**：33 条规则的条款号是否真对应条文。本仓有「（文号, 条款）命中 + quote
  完全相等」的硬守门，但**没有语义核对**——需临床/病案专家过一遍，尤其
  `F-TIME-03`（「术后首次病程记录未即时完成」，2h 阈值，`status=待核对`）。
- 本轮用户已决定**跳过人工目检**，故 README 首屏三处（`v0.2.0 已发布` /
  `Python ≥ 3.12` / `CI：{ubuntu, windows} × 3.12`）由程序判据背书（测试 + grep），
  未做人工视觉确认——如实记录。
