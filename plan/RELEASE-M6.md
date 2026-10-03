# RELEASE-M6（脱敏审计留档，2026-10-03）

> M6 脱敏四步的逐项命令与结论。口径见 HANDOFF-M6 §2；DoD 见 plan/05 M6 行。
> 留档纪律：本文档用占位符指代敏感字面值（个人邮箱、本机绝对路径），不复述原文——保证"全历史 0 命中"终验可过。历史改写与发布执行记录见 [HANDOFF-FINAL.md](HANDOFF-FINAL.md)。

## 第 1 步：敏感文件名扫描 — ✅ 通过

```
$ git ls-files | grep -iE "\.env$|\.key$|secret|token"
（0 行输出）
```

`.gitignore` 核对：覆盖 `.env`、`*.key`、`*_private/`（环境与密钥段）与 `output/`、`reports/`、`*.log`（运行产物段）、`build/`、`dist/`。仓库存在 `LICENSE`（MIT，D-01 默认）与 `.github/workflows/ci.yml`。

## 第 2 步：内容级扫描全部跟踪文本文件 — ✅ 通过（误报 3 类甄别，真实发现 1 类已改）

```
$ git grep -nIE "sk-[A-Za-z0-9]{8}" -- .            # → 0 命中
$ git grep -nIE "1[3-9][0-9]{9}" -- .               # → 2 命中，均为误报
$ git grep -nIE "[0-9]{17}[0-9Xx]" -- .             # → 0 命中
$ git grep -nIE "C:.Users." -- .                    # → 1 命中，误报（见下）
$ git grep -nIE "(10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3})" -- .
                                                    # → 0 命中
$ git grep -nIE "[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+" -- .
                                                    # → 0 命中
$ git grep -nIE "<本机用户名>" -- .                  # → 0 命中
$ git grep -nIE "<本机目录关键词>|D:[/\\]" -- .       # → 初扫 12 命中 → 已改
```

命中处置：

| 模式 | 命中 | 判定 | 处置 |
|---|---|---|---|
| 手机号 `1[3-9]\d{9}` | 2（data/README.md、knowledge/raw 病案管理指标 txt） | 均为卫健委官网 PDF 直链中的文件 ID（纯数字串），非手机号 | 保留 |
| 个人路径 `C:\Users\` | 1（plan/HANDOFF-M6.md §2） | 脱敏规则文本的自引用（扫描模式本身），非真实路径 | 保留 |
| 本机绝对路径 `盘符:\本机应用目录\仓库名\…`（含 Git Bash 形式 `/盘符/本机应用目录/…`） | 12（6 份 plan/HANDOFF-M*.md，各 2 处：续接提示词行 + 命令速查 cd 行） | 机器本机应用目录路径（不含用户名，无身份信息），但按"扫出改占位符"口径不外发 | **已改**：续接提示词改为仓库相对路径 `plan\HANDOFF-MX.md`，cd 行改为 `cd <仓库根>`；复扫 0 命中；历史 blob 中的同字面值随全历史改写一并清除（见第 4 步与 HANDOFF-FINAL） |

## 第 3 步：二进制样例单独扫（docx zip 全条目）— ✅ 通过

`benchmarks/m5_report_sample.docx`（真实 `mrqc run --report` 产出，患者信息全合成）：

```
zip 条目数 17，逐条目字节流按 utf-8 容错解码后过第 2 步全部模式：
- 命中 6 处全部在 word/fontTable.xml，为字体 PANOSE 十六进制串
  （如 w:val="02020603050405020304"）匹配了 18 位数字模式 —— 误报；
- docProps/core.xml：creator = 'python-docx'，lastModifiedBy = ''（空）—— 干净；
- 其余模式（sk-/手机号/个人路径/本机盘符路径/<本机用户名>/邮箱/内网 IP）：0 命中。
```

## 第 4 步：提交元数据邮箱检查 — ⚠️→✅ 发现并处置（用户已拍板）

```
$ git log --format='%ae %ce' | sort -u
<个人QQ邮箱> <个人QQ邮箱>                    # 全部 7 个提交的 author+committer（字面值不落档）
$ git config user.name / user.email
yuluo554 / <个人QQ邮箱>
```

- 个人 QQ 邮箱已进入全部 7 个本地提交的元数据；blob 内容级扫描 0 命中（邮箱只在元数据，不在任何文件内容）；
- 远程仓库尚未建立、未 push，**重写历史此刻零风险**（push 后再改即需 force-push）；
- 处置（2026-10-03 用户在打包授权中确认）：全部提交 author/committer 经 `git filter-branch --env-filter` 改写为 GitHub noreply（`282769740+yuluo554@users.noreply.github.com`），`git config user.email` 同步；同批 tree-filter 清除 6 个提交 HANDOFF blob 中的本机路径字面值（第 2 步表格行）；执行与终验记录见 HANDOFF-FINAL；
- 提交说明（`git log --format=%B`）扫描无邮箱/路径/密钥。

## 干净环境验证 — ✅ 通过（含 1 项 README 修正）

新目录（本机 %TEMP% 下）本地 clone（HEAD=8872fb3）+ 全新 venv（Python 3.8.8，venv 自带 pip 20.2.3）：

| 步骤 | 结果 |
|---|---|
| `pip install -e ".[dev,web,report]"`（原 README 步骤） | ❌ **失败**：pip 20.2.3 不支持 pyproject-only editable 安装（需 ≥21.3，PEP 660） |
| `python -m pip install --upgrade pip` → 同上 | ✅ pip 25.0.1，安装 rc=0 |

**README 已修正**：快速开始加入 `python -m pip install --upgrade pip` 一步（Python 3.8 原装 pip 20.x 装不上 editable，这是干净环境验证抓到的唯一环境坑）。

升级后逐条照 README 跑通：

| 命令 | 结果 |
|---|---|
| `pytest --collect-only` | **173 tests collected**（与 dev 一致） |
| `pytest` | **173 passed**，rc=0 |
| `mrqc demo` | 架构自检 8 项 [ok]，rc=0 |
| `mrqc parse/check --input data/samples/appendicitis_001` | rc=0 / rc=0 |
| `mrqc run --input data/paired/defect_C-LAB-02_01 --report …docx` | rc=0；stdout 单 JSON（record_id/findings=28/summary 九键）；docx 生成 |
| `mrqc benchmark parse` | rc=0，P=R=F1=1.0 |
| `mrqc benchmark detect` | rc=0，检出率 1.0、clean_false_positives=0、basis_linkage_rate=1.0 |
| Web 冒烟（`-m mrqc.web`） | 启动 ~1s；/api/status 正常；/docs→**404**；curl multipart 真传 12 部件 → 200 JSON（干净样例 overall=通过） |

## 复扫入口（发布复核用）

```
git ls-files | grep -iE "\.env$|\.key$|secret|token"   # 应空
git grep -nIE "sk-[A-Za-z0-9]{8}|1[3-9][0-9]{9}|[0-9]{17}[0-9Xx]|C:.Users.|<本机用户名>" -- .
git grep -nIE "<本机目录关键词>|<个人邮箱字面值>" -- .    # 固定字面值不入档，见 HANDOFF-FINAL 记录
git log --format='%ae %ce' | sort -u                    # 应只剩 noreply
```

## 发布执行记录（2026-10-03）

- **全历史脱敏重写**：`git filter-branch --env-filter`（全部 8 提交 author/committer → GitHub noreply）+ `--tree-filter`（HANDOFF blob 本机路径字面值清除，与工作区占位化同法）；refs/original 删除 + reflog expire + `gc --prune=now`；预验（rev-list 逐提交 blob 扫描 4 个固定字面值）全 0；终验三扫在收尾提交后执行；
- **建仓**：`gh repo create yuluo554/medical-record-quality-checker --public --source . --remote origin`（**不带 `--push`**——规避 OAuth token 缺 `workflow` scope 且历史含 `.github/workflows/*` 时推送被拒的半失败态，方法论实录教训）→ remote 切 SSH（`ssh -T` 验证有 key）→ `git push -u origin main` 一次成功；
- **元信息**：description 按 D-02 原案建仓时写入；topics 7 个：`medical-record` `quality-control` `clinical-nlp` `llm` `rule-engine` `healthcare` `ehr`；
- **tag v0.1.0 + release**：已执行（用户已确认）——annotated tag 指向收尾回写提交（557baa0），[release 页](https://github.com/yuluo554/medical-record-quality-checker/releases/tag/v0.1.0)（notes = 基准表数值 + 演示命令摘要 + extras 说明 + 免责声明）；
- **发布后复核**：GitHub 全新 clone 历史三扫全 0 + 全量测试等效 173/173 + 双基准 rc=0 + CI main 两轮全绿 + README 远端内容核验齐——详见 [HANDOFF-FINAL.md](HANDOFF-FINAL.md)；
- **三扫口径说明**：bare `<本机用户名>` 词面曾以"扫描模式自引用"形式出现在本文档 2 个历史提交中（即 `git grep -nIE "<本机用户名>"` 规则文本本身），非用户名路径泄露——真实组合形式 `C:\Users\<本机用户名>` 全历史 0 命中；本文档前进方向全部占位化（本提交起）。
