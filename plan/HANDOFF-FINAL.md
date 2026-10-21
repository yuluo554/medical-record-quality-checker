# HANDOFF-FINAL（发布收尾快照，2026-10-03；2026-10-22 二次迭代回写）

> 项目全里程碑收官（M0–M6 ✅）+ **M3 二次迭代 v0.2.0 已发布**。本文档 = 终态基线 + 发布执行记录 + 复跑手册；**既定口径清单见 HANDOFF-M6 §3（全部继续有效）**，环境坑在 HANDOFF-M6 §4 基础上增量记录（§4）。新对话续接提示词：`/goal 读取 "plan/HANDOFF-FINAL.md" 按需继续`（项目已完成，此行仅为续读指引）。
>
> ⚠️ **§1/§3/§5 保留为 v0.1.0 时期的历史记录**（不改写，便于对照）；**v0.2.0 的终态以 §7 为准**。

## 1. 发布终态（v0.1.0 时期，2026-10-03；现行终态见 §7）

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/yuluo554/medical-record-quality-checker（public，默认分支 main） |
| description | 出院病历内涵质控智能审核系统：形式+内涵双通道质控、规范依据关联、内置可复现评测基准 |
| topics | `medical-record` `quality-control` `clinical-nlp` `llm` `rule-engine` `healthcare` `ehr`（D-02 原案，用户 2026-10-03 打包确认） |
| tag / release | `v0.1.0`（annotated，指向 557baa0 收尾回写提交）+ [release](https://github.com/yuluo554/medical-record-quality-checker/releases/tag/v0.1.0)（基准表数值+快速开始+命令+依赖+免责声明） |
| 提交链 | 19466f9(题定)→b17d5d9(M0)→69a69e8(M1)→957787a(M2)→74b42c1(M3)→41aa60a(M4)→17aea67(M5)→edf7364(M6 发布准备)→557baa0(M6 收尾回写)→本提交(HANDOFF-FINAL)——全部经历史重写，author/committer 仅 noreply |
| CI | GitHub Actions 3.8/3.10/3.12；main push 两轮全绿（27s/32s，run 37162206455 / 37162462413） |
| 基准 | parse F1=1.0000（TP=7664）/ 检出率 100%（45/45）/ 干净误报 0 / 依据关联率 100%；173 项测试全绿 |

## 2. 全历史脱敏重写与终验三扫记录

用户 2026-10-03 打包授权四项：①公开仓建仓+push；②邮箱全历史改写；③v0.1.0 tag+release；④D-02 原案元信息。

- **env-filter**：全部 8 个提交 author/committer 个人 QQ 邮箱（字面值不入档，见 RELEASE-M6.md §4）→ `282769740+yuluo554@users.noreply.github.com`；`git config user.email` 同步（blob 内容级邮箱字面值 0 命中，仅元数据）；
- **tree-filter**：6 个提交 HANDOFF blob 中的本机绝对路径两种字面值（`盘符:\本机应用目录\仓库名\plan` 与 `cd /盘符/…`，同工作区占位化替换为 `plan\HANDOFF-MX.md` / `cd <仓库根>`）；
- **清理**：refs/original 全删 + `reflog expire --expire=now --all` + `gc --prune=now`（不清理则三扫面对旧对象，白验）；
- **终验三扫（全 0 才算过）**：①`git rev-list --all` 逐提交 `git grep -lF <字面值>`；②`git log --all -p | grep -cF <字面值>`；③`git log --format=%B` 扫描。固定字面值集 = 邮箱字面值、本机路径两种形式、`C:\Users\<本机用户名>` 组合形式——**全部 0 命中**；GitHub 全新 clone 侧复测同结果；
- **残留说明**：bare `<本机用户名>` 词面曾以"扫描模式自引用"形式存在于 RELEASE-M6.md 的 2 个历史提交（`git grep -nIE "<本机用户名>"` 规则文本本身），判非用户名路径泄露（真实组合形式 0 命中）；RELEASE-M6.md 自收尾提交起全部占位化，此后增长为零。

## 3. 干净环境验证与发布后复核（实测口径）

**发布前干净环境**（本地 clone + 全新 venv，详见 RELEASE-M6.md）：pytest 收集 173 与 dev 一致、demo/parse/check/run --report、双基准 rc=0、Web 冒烟 4 项全过；抓出 **py3.8 原装 pip 20.x 不支持 pyproject-only editable**（PEP 660 需 ≥21.3）→ README 快速开始补 `python -m pip install --upgrade pip` 步。

**发布后复核**（GitHub 全新 clone，2026-10-03）：

| 项 | 结果 |
|---|---|
| 历史三扫（clone 侧） | 全 0；邮箱仅 noreply |
| pytest | 172 一次过 + `test_real_uvicorn_multipart_smoke` 1 次瞬态失败（uvicorn 子进程未起，本机崩溃家族）→ 单测重试 **1 passed** → 等效 173/173 |
| demo / benchmark parse / benchmark detect | rc=0 / rc=0（F1=1.0，TP=7664，FP=FN=0）/ rc=0 |
| uvicorn 手动起 + /api/status | 200，启动日志干净 |
| README 远端 | gh api readme 8319 字节，升级 pip 步/基准数值/免责声明关键内容齐全 |
| CI | main 两轮 push 全绿（tag push 未触发 CI——本仓 ci.yml 未配 tag 触发，如实记录） |

## 4. 环境事实与禁忌（HANDOFF-M6 §4 增量，只写实测过的）

- **MSYS 路径改写陷阱**：以 `/` 开头的命令参数（如字面值 `/盘符/xxx`）会被 MSYS 静默转写成 Windows 路径再传给程序——`git grep` 字面值扫描**别用 `/` 起始模式**（改用 `'cd /盘符/xxx'` 这类非 `/` 起始的包含形式），否则假 0 命中（本次实测：`/盘符/本机目录` 扫描假 0，`cd /盘符/…` 形式才真扫）；
- **filter-branch 后置清理是三扫前提**：refs/original 不删、reflog 不清，`--all` 类扫描仍见旧对象；
- **gh 建仓 workflow scope**：gh token scopes 无 `workflow` 且历史含 `.github/workflows/*` 时，`gh repo create --push` 推送必被拒（仓库已建出=半失败态）→ 建仓走 `--source . --remote origin` 不带 `--push`，`ssh -T git@github.com` 验证有 key 后 remote 切 SSH 一次推成（本仓 SSH 可用，实录一次过）；
- **本机随机段错误期实录（crash-loop-rescue 口径）**：会话后段 venv 内 pytest 连续 3 次 rc=139（`source_to_code` access violation、失败点漂移）、`py -m venv` 的 ensurepip 子进程 2 次 exit 1。判别 = 机器崩溃非真 bug（同代码 CI 全绿、demo/bench detect 通过、单测与手动 uvicorn 重试即过）。处置 = `--without-pip` + 手动 ensurepip 绕建 venv 失败；venv 通路不稳时换 **系统 Python + `PYTHONPATH=<clone>/src`** 跑目标代码（注意本仓 pyproject 未配 pythonpath，不挂 PYTHONPATH 会静默测到系统安装的 dev 版）。判定成败的命令不接管道，原样重试 ≤3 次再换策略；
- pytest 收集数 173 的前提 = 全量 extras 可用（web/report importorskip 显式 reason；缺 extras 会少跑——对照收集数即可识别）。

## 5. 复跑命令速查（终态回归集）

```bash
cd <仓库根>
git ls-files | grep -iE "\.env$|\.key$|secret|token"      # 应空
git log --format='%ae %ce' | sort -u                       # 应只剩 noreply
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m pytest             # 173 项（看 rc）
py -X utf8 -m mrqc demo
py -X utf8 -m mrqc benchmark parse                         # F1 ≥0.95 门槛 rc=0
py -X utf8 -m mrqc benchmark detect                        # 检出/误报门槛 rc=0
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m mrqc.datagen --verify data/samples data/paired   # 位级一致
gh run list --repo yuluo554/medical-record-quality-checker --limit 5                      # CI 状态
```

## 6. 遗留与后续

- **D-03 投赛**：唯一遗留待定项（是否投研究生 AI 大赛开放赛道 / "数据要素×"），项目已发布可作参赛基础，由用户决定；
- 真实病历数据验证、打印体 OCR 为远期项（README"限制"节已如实声明）；
- 项目系列接续（plan/00 §项目系列）：下一个项目立项时沿用 ai-tool-project-sprint 流程；
- 本仓库后续改动纪律：改参数卡/渲染/口径先对照 HANDOFF-M6 §3；新增第三方运行期 import 必须进 extras 并过收敛守门测试；测试/文档中的"N 项测试"计数随守门测试增加同步更新（v0.2.0 起该条由 `tests/test_readme_consistency.py` **自动守门**，不再靠人记）。

## 7. v0.2.0 终态（2026-10-21 执行 / 2026-10-22 收尾）——**现行准据**

> 发布留档见 [RELEASE-v0.2.0.md](RELEASE-v0.2.0.md)；决策见 [06-决策记录.md](06-决策记录.md) 2026-10-21 各行。
> §1–§5 为 v0.1.0 时期记录，**不得据其判断现状**（尤其 §1 的 tag/CI/测试数三行已过时）。

### 7.1 现状终态（不得回退）

| 项 | 值 |
|---|---|
| tag / release | **`v0.2.0`**（annotated）→ `60f7f09e6500b4ef14b47833bd6d9b51d17005c7`（剥壳后）；[release](https://github.com/yuluo554/medical-record-quality-checker/releases/tag/v0.2.0) 三附件：whl 116,186 B `f90320b9…` / sdist 1,033,299 B `b800a179…` / `SHA256SUMS` 178 B |
| 版本 | `0.2.0`（`pyproject.toml:7` 与 `src/mrqc/__init__.py:9` 双处，由 `tests/test_version_single_source.py` 守门） |
| tag 滞后 | **1 个文档提交**（`git rev-list --count v0.2.0..HEAD`）——收尾回写（plan 文档 + README 链接），**只改文档、不改代码/数据/构建配置**；口径与副作用见 RELEASE-v0.2.0 §6.1（附件内嵌 README 为 tag 时刻版本，属文档级陈旧，下次发版自然消除）。**不重指 tag**（已被拉取可能）。 |
| requires-python | **`>=3.12`**（floor 由 3.8 抬升，PEP 639：`license="MIT"` + `license-files`，`setuptools>=77`） |
| CI | **{ubuntu-latest, windows-latest} × 3.12**，actions `checkout@v7` / `setup-python@v7`；含**非 editable 打包门禁**（`tools/ci_packaging_gate.py`）；job env `PYTHONIOENCODING=utf-8` |
| 测试 | **192 passed / 0 skipped**（四处一致：仓库 / 干净 clone / sdist 解包 / Release 下载件） |
| 知识库位置 | 包内 `src/mrqc/knowledge/data/{blocks,rules}`（**随 wheel 分发**）；`raw/` 留仓内 `data/knowledge/raw/`（**进 sdist、不进 wheel**） |
| 装态基线 | `knowledge_status()` = `{'raw':0,'blocks':42,'rules':33}`；`mrqc check` → **33 条 finding**，rc=0 |
| 规则库为空的纪律 | `check`/`run` 打印 `[错误]` 并 **rc=2**（绝不静默降级为「通过」） |
| 基准 | parse f1=1.0 / tp=7664 / fp=0 / fn=0；detect rate=1.0 / clean_fp=0 / unexpected=0 / n_non_pass=45（与 v0.1.0 **完全一致，零退化**） |
| 复核锚 | 33 条规则 `basis` 与 42 个条文块均带 `reviewed_at=2026-10-03` / `next_review=2027-10-03`；块层 `status="已核对"`；`F-TIME-03` 仍「待核对」 |
| 冻结数据 | `data/samples` 401 / `data/paired` 416 / `data/knowledge/raw` 6 —— **字节未动** |

### 7.2 本轮修掉的东西（一句话版）

**装成 wheel 后工具不再退化成「永远说通过的空壳」**：改前 `knowledge_dir()` 在
site-packages 下解析到 `<venv>/Lib/data/knowledge`（不存在）→ 规则库 0 条 → `check` 输出
`[]`、「总体结论：通过」、rc=0；改后知识库随 wheel 分发，装态 33 条结论，且**规则库为空
时硬失败 rc=2**。同批修掉 sdist 32 failed、CI 单 OS 单点、`>=3.8` EOL、README 状态错标。

### 7.3 v0.2.0 复跑命令速查（终态回归集）

```bash
cd <仓库根>
git rev-list --count v0.2.0..HEAD                          # 期望 0（或仅文档追加提交）
git rev-parse v0.2.0^{}                                    # 期望 60f7f09...
python -m pytest -o addopts=""                             # 192 passed（注意本仓 addopts="-q"，-q 会变 -qq 吞汇总行）
python -c "from mrqc.knowledge import knowledge_status as k; print(k()); assert k()['rules']==33 and k()['blocks']==42"
python -m build --sdist --wheel --outdir %TEMP%\v02dist    # 期望 0 条 deprecat
python tools/ci_packaging_gate.py                          # 非 editable 装态验活：PACKAGING GATE OK
mrqc benchmark parse                                       # f1=1.0 tp=7664 fp=0 fn=0
mrqc benchmark detect --data data/paired                   # rate=1.0 clean_fp=0 unexpected=0 n_non_pass=45
git diff --stat 3178d45..HEAD -- data/samples data/paired data/knowledge/raw   # 期望空
gh run list -R yuluo554/medical-record-quality-checker --limit 3               # 两腿 success
```

**从 Release 复验（最硬的一条）**：

```bash
gh api "repos/yuluo554/medical-record-quality-checker/releases/tags/v0.2.0" --jq '.assets[]|"\(.id)|\(.name)"'
# 逐个 gh api -H "Accept: application/octet-stream" .../releases/assets/<id> > <name>
sha256sum -c SHA256SUMS            # 期望两行 OK
# 再在仓外目录装 whl：knowledge_status() = {'raw':0,'blocks':42,'rules':33}，check → 33 findings
```

### 7.4 v0.2.0 新增的守门（改代码前先看这里）

| 守门 | 锁什么 |
|---|---|
| `tests/test_packaging.py`（4 项） | `knowledge_dir()` 在包内、42·33、`package-data` 已声明、5+2 json 在 |
| `tests/test_ci_workflow.py`（6 项） | ci.yml 可解析、双 OS × 3.12、无 3.8/3.10 字面量、`runs-on` 绑 matrix.os、打包门禁存在且非 editable、actions v7 |
| `tests/test_version_single_source.py`（2 项） | `pyproject.version == mrqc.__version__` |
| `tests/test_readme_consistency.py`（1 项） | README「N 项」== 真实收集数（**加测试必须同步 README**） |
| `tests/test_cli_encoding.py`（2 项） | `PYTHONIOENCODING=cp1252` 下 `mrqc demo` 仍 rc=0 |
| `tools/ci_packaging_gate.py` | 非 editable 装态知识库可用（CI 与本地都可跑） |
| `tests/test_knowledge.py` 新增 4 项 | 规则/块/文件三层复核锚齐备；逾期只警告不改退出码 |

### 7.5 v0.2.0 环境坑增量（在 §4 之上）

- **`pythonpath = ["src"]` 已在 `pyproject` 配好**（v0.1.0 时期 §4 那条「本仓 pyproject 未配
  pythonpath，不挂 PYTHONPATH 会静默测到系统安装的 dev 版」**已失效**）。但**子进程测试**
  仍需显式 `PYTHONPATH` 指向本仓 `src`——`tests/test_cli_encoding.py` 就栽过这一下（sdist
  里导入到 site-packages 的旧副本）。
- **本机 `TEMP` 两义**：Git Bash 里是 `/tmp`、Python 里是 `C:\Users\<用户>\AppData\Local\Temp`，
  **两者不是同一目录**。用 Python 写临时文件、bash 去取会错开。
- **本机代理 `127.0.0.1:7897` 当前不可达**（curl 走代理返回 000，直连 200）；pip/curl 都不要带代理。
- **`%TEMP%\dl-verify` 是别的会话遗留目录**，`rm -rf` 会因占用失败——不要去删。
- **加 windows 腿后 CI 会跑 `mrqc demo`**：Windows 默认控制台 cp1252，中文输出必崩。已用
  `cli._force_utf8_stdio()` 修在产品代码 + CI job env 双保险；新增 CLI 中文输出时别再依赖
  「用户自己加 `-X utf8`」。
- **tag 重指的合规姿势**：若 tag 尚未被任何消费方拉取，可删本地+远端 tag 重打（本轮实例见
  RELEASE-v0.2.0 §6）；**若已被拉取则不可重指**，只能追加新版本。重指后必须重建 Release
  附件（附件字节会随 README 等文件变化）并 `gh release edit`/重建说明。
