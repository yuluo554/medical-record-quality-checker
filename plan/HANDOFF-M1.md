# HANDOFF-M1（M0 收尾 → M1 数据先行）

> 交接快照，写于 2026-10-03（M0 完成时）。新对话续接提示词：`/goal 读取 "plan\HANDOFF-M1.md" 继续完成任务`

## 1. 当前进度（M0 已完成 ✅）

- plan 02–06 定稿（需求解读/架构/模块详设/数据与里程碑/决策记录，含待定决策 D-01~D-05 待用户拍板，均不阻塞 M1）；
- 可运行骨架：包 `mrqc`（src 布局），参数卡契约 `models/card.py`、规则模型+引擎骨架（无依据规则拒绝加载）、流水线编排、CLI（demo/parse/check/run/benchmark，未实现项 exit 2）、惰性导入的 report/web、`__main__.py`；
- 测试 21 项全绿（含 extras 守门测试锁定 python-multipart/extras/CI 覆盖）；`py -m pip install -e .` 与 `py -m mrqc demo` 实测通过；
- CI 就位（3.8/3.10/3.12 × ubuntu，显式装 `.[dev,web,report]`）；.gitattributes 统一 LF；MIT LICENSE；README（含免责声明）；
- 本地已提交；**远程仓库未建、未 push**（建仓/推送需用户授权，属 M6）。

## 2. M1 待办（数据先行，DoD 见 plan/05 §5）

1. 病种模板 ×3（社区获得性肺炎=内科用药型、急性阑尾炎=外科手术型、胆囊结石=外科手术+用血变体）→ `data/templates/`；
2. 生成器 `src/mrqc/datagen/`：固定 seed、产出部件 txt + truth.json（参数卡形状）；注入模式产出 paired + defects.json（注入清单与 also_expect）；
3. 注入器严格对照 plan/04 §7 缺陷 ID 表（12 类），与 M3 规则、M4 基准三方共用 ID；
4. 规范原文 5 份获取入库 `data/knowledge/raw/`（WebSearch 摘要不采信，只用可直连官方页面原文；查不到登记"待核对"继续）；data/README.md 登记表逐份登记（来源+URL+日期+status）；
5. truth.json 对账脚本（生成器真值 ↔ `RecordCard.from_dict` 往返校验）+ 生成器位级可复现测试（同 seed 重跑 `git status` 零变化）。

## 3. 既定口径清单（动了会打挂基准/测试，改前先对照）

- **参数卡是唯一契约**：`src/mrqc/models/card.py` 改字段必须同步 truth.json 生成器、parse_f1 基准、`tests/test_card.py`；
- **注入/规则/基准三方共用缺陷 ID 表**（plan/04 §7），不得单方改名；注入项记主期望 + also_expect，评测按全部非 pass 集合对账；
- 规则 JSON schema（plan/04 §3）：无 basis 的规则 `RuleEngine` 加载即抛 `RuleError`——这是特性不是 bug；
- `only_if` 门控对全部 check_type 生效；空 only_if = 无条件启用；
- severity 五值：LOW/MEDIUM/HIGH/CRITICAL/NEED_CONFIRM；多值/低置信度一律 NEED_CONFIRM；
- **基准零 API 依赖**：LLM 未配置即基准环境；测试全离线（LLM 用 mock）；
- 核心通路零第三方依赖；extras：report=python-docx / web=fastapi+uvicorn+python-multipart / dev=pytest；LLM 走 stdlib urllib 无独立 extra；改动依赖先过 `tests/test_extras_guard.py`；
- 指标门槛不放宽：F1 ≥0.95、干净集误报 0；
- 未实现模块 fail-fast exit 2（CLI 惯例），不伪造成功；
- 报告/README 必须保留"非临床决策支持"免责声明与合成数据声明；
- 交付 0 外链（Web 内联、docx 无外部引用）。

## 4. 本机环境坑（只写实测过的）

- Python 3.8.8（`py` 启动器；`python` 是商店占位符）；跑中文输出一律 `py -X utf8`；
- `pip install -e .` 已实测成功（pip 25.0.1 健康）；若 pip 报 `127.0.0.1:7897` 代理错 → `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`；
- `mrqc.exe` 装在非 PATH 目录 → 用 `py -m mrqc`（`__main__.py` 已备）；
- pytest 8.3.5 已在系统 Python；跑测试带 `PYTHONDONTWRITEBYTECODE=1`（本机 pyc 偶发损坏史）；
- 测试 21 项一次跑完无压力；分批纪律（每批 ≤50）从测试数超过 50 起执行；
- git 输出中文乱码仅显示层问题，hash/status 可信。

## 5. DoD checklist

M0（已完成）：
- [x] plan 02–06 定稿，00 索引与状态回写
- [x] `pip install -e .` 通过；`pytest` 21 项全绿
- [x] `py -m mrqc demo` 输出架构状态与免责声明
- [x] extras 守门测试在位；CI yaml 就位（3.8/3.10/3.12 + 全量 extras）
- [x] .gitattributes（LF 门）/ LICENSE(MIT) / README（免责声明）就位
- [x] data 四类目录 + knowledge 三层目录落位，data/README 目录约定
- [x] 本地提交（远程未建——建仓属 M6，需用户授权）

M1（执行时逐项打勾，未达成写偏差说明）：
- [ ] 3 病种模板入库
- [ ] 生成器固定 seed 位级可复现（重跑 git status 零变化）
- [ ] samples ≥60、paired 覆盖 12 类注入各 ≥3 份 + 干净对照 ≥10 份
- [ ] truth.json ↔ RecordCard 对账脚本通过
- [ ] 规范 raw 入库 + 台账登记齐全（或登记"待核对"）
- [ ] plan/00、05、06 回写 ✅；写 HANDOFF-M2

## 6. 关键命令速查

```bash
cd <仓库根>
py -X utf8 -m pytest                        # 全量测试（21 项起步）
py -X utf8 -m mrqc demo                     # 架构自检
py -X utf8 -m mrqc parse --input data/samples/xxx/   # 解析（M2 前仅告警）
py -X utf8 -m mrqc check --input data/samples/xxx/   # 质控（规则库空→0 结论）
git status && git log --oneline -3          # 提交前三核对（pwd/git log/remote）
```

## 7. 开放问题（不阻塞，见 plan/06 待定决策表）

D-01 License 确认 / D-02 仓库 description+topics / D-03 是否投赛 / D-04 Python 底线 / D-05 仓库名微调——均按默认执行中，用户拍板后在 06 回写。
