# HANDOFF-FINAL（M6 发布收尾快照，2026-10-03）

> 项目全里程碑收官（M0–M6 ✅）。本文档 = 终态基线 + 发布执行记录 + 复跑手册；**既定口径清单见 HANDOFF-M6 §3（全部继续有效）**，环境坑在 HANDOFF-M6 §4 基础上增量记录（§4）。新对话续接提示词：`/goal 读取 "plan/HANDOFF-FINAL.md" 按需继续`（项目已完成，此行仅为续读指引）。

## 1. 发布终态（不得回退）

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
- 本仓库后续改动纪律：改参数卡/渲染/口径先对照 HANDOFF-M6 §3；新增第三方运行期 import 必须进 extras 并过收敛守门测试；测试/文档中的"N 项测试"计数随守门测试增加同步更新。
