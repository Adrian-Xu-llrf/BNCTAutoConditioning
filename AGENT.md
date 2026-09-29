# AGENT.md — 版本号维护规程（给 AI / 开发者）

本文件规定 **RFQ 自动老练系统**（`AutoConditioning/`）如何升级版本号。
任何人（包括 AI 助手）在改动代码后要发版，必须按本文件执行，不得跳过任何一步。

---

## 1. 单一事实源（Single Source of Truth）

**版本号只写在 `rfq/__init__.py` 一处：**

```python
__version__ = '2.0.0'      # ← 全项目唯一版本号，格式 MAJOR.MINOR.PATCH
```

其他任何地方（README、日志、spec、界面文案）都不允许再手写一份版本号。
已接入自动读取 `__version__` 的位置：

- `main.py` 启动横幅 + 日志首行 `RFQ自动老练系统 v2.0.0 启动`
- `RFQAutoCon.spec` 用正则从 `rfq/__init__.py` 取版本号，exe 自动命名为
  `RFQAutoCon_v2.0.0.exe`（**不 import rfq**，避免拉起 epics 依赖）

> 新增展示位点时请照此写法接入，不要硬写字符串。

### 历史遗留（已知不一致，不要模仿）

| 位置 | 值 | 问题 |
|---|---|---|
| git tag `V1.0` | 指向 `d8d9252` | 该 commit 说明写的是 "V1.1"，**tag 早打错了** |
| commit message | 出现过 "V1.1" | 只在提交信息里，无 tag，无法追溯 |
| ~~`rfq/__init__.py`~~ | ~~`3.0.0`~~ | 遗留错误值，已于 2.0.0 发布时修正（见第 8 节） |

因此判断"现在跑的是哪个版本"，**以 `rfq.__version__` + `git describe --tags` 为准，不要以旧 tag 为准**。

---

## 2. 语义化版本规则

格式：`MAJOR.MINOR.PATCH`（纯数字，不带 `v` 前缀写在代码里；tag 才带 `v`）

| 位 | 何时加 | 本项目判据 |
|---|---|---|
| **MAJOR** | 有不兼容变更 | 删除/重命名 PV；状态机状态编号或合法转移表发生破坏性改动（现场配置的老流程跑不通了）；配置文件结构不兼容 |
| **MINOR** | 有新功能，向后兼容 | 新增状态（如 `AUTO_REGULATING`）；新增 PV（如 `AutoC_SetpointStep`）；新增控制器方法；新增 config 配置项 |
| **PATCH** | 修 bug / 调参数 | 只改内部逻辑、修 bug、改阈值/超时时间、加日志，不新增对外接口 |

> 参考：`1bdaf37`「脉冲模式下禁用自动加载」属于 PATCH；
> `132fbd6`「闭环后 setpoint 调节功率」新增了状态 + 2 个 PV → MINOR。

---

## 3. 发版清单（Checklist，改代码后逐条打勾）

- [ ] **1. 改版本号** —— 编辑 `rfq/__init__.py` 的 `__version__`（唯一手改点）
- [ ] **2. 确认展示位点** —— `main.py` 横幅与日志、`RFQAutoCon.spec` 的 exe 名均自动读取
      `__version__`，**无需改动**；若新增了展示位点，按第 1 节写法接入
- [ ] **3. 打包 exe** —— 产物名自动带版本号 `dist/RFQAutoCon_v2.0.0.exe`
      ```bash
      pyinstaller RFQAutoCon.spec    # 开头会打印 [spec] RFQAutoCon version = x.y.z
      ```
- [ ] **4. 跑测试** —— `python -m pytest tests/ -v`，必须全绿
- [ ] **5. 提交** —— 代码改动与版本号改动**同一个 commit**，不要分两个 commit
- [ ] **6. 打 tag** —— `git tag -a v2.0.0 -m "闭环后 setpoint 调节功率"`（annotated tag，带说明）
- [ ] **7. 推送** —— `git push origin BNCT && git push origin v2.0.0`（tag 必须单独推！）
- [ ] **8. 归档 exe** —— 把打好的 exe 复制一份到 `../archive/AutoConditioning_v2.0.0.exe`
      （`archive/` 已被 `.gitignore` 忽略，不入库，但历史版本留在本地可回溯）

---

## 4. 命令速查

```bash
# 当前版本（以代码为准）
python -c "from rfq import __version__; print(__version__)"

# 当前代码对应哪个 tag / 距上次发版几个提交
git describe --tags
git tag -l --sort=-v:refname        # 按版本号从大到小列 tag

# 发版
git add -A && git commit -m "chore: bump version to 2.0.0"
git tag -a v2.0.0 -m "release: 闭环后 setpoint 调节功率"
git push origin BNCT
git push origin v2.0.0
```

---

## 5. 现场排查：怎么确认 BNCT 上跑的是哪个版本

按可靠度从高到低：

1. **`dist/` 里的 exe 文件时间戳与文件名**（文件名带版本号后最直观）
2. **日志开头那行版本信息**（第 3 节第 2 条加上之后就有）
3. `python -c "import rfq; print(rfq.__version__)"`

> 踩坑提醒：`logs/`、`dist/`、`build/` 都在 `.gitignore` 里，**不进版本库**。
> 如果只 push 了代码但没在 BNCT 现场重新打包，源码版本 ≠ 现场 exe 版本。
> 2026-04 的教训：源码已到 setpoint 功能版，BNCT 上跑的 exe 还停在 4-19 的快照版。

---

## 6. TODO（尚未实现，登记备查）

- [x] 横幅与日志实际打印版本号（`main.py`，随 2.0.0 完成）
- [x] `RFQAutoCon.spec` 的 `EXE(name=...)` 自动带版本号（随 2.0.0 完成）
- [ ] 新增 PV `RFQ:LLRF:Con01:AutoC_Version`（float，如 `2.0`）与 `AutoC_VersionStr`（string），
      启动时写入，便于从 EPICS 界面直接确认现场版本；
      实现时需同步改 `rfq/core/pv_keys.py`、`config.yaml` 的 `pv:` 段、`tests/sim_ioc.py`、`tests/BNCT_ioc.py`
- [ ] 修正历史 tag `V1.0` → `v1.1`（**注意：改名等于丢弃原 tag 对象**，
      `git tag -d V1.0 && git tag -a v1.1 d8d9252 -m "stable 模块"`，需团队确认后再做）
- [ ] 下一个版本号待定；2.1.0 候选：新 PV、新参数、新状态；3.0.0 候选：状态机/PV 破坏性变更

---

## 7. 目录约定

- 开发目录：`BNCT/AutoConditioning/`（git 分支 `BNCT`，远端 `BNCTAutoConditioning`）
- 归档目录：`BNCT/archive/`（不入库，存历史 exe 与冻结快照；**勿在其中开发**）
- 交付仓库 `RFQAutoControl` 是 2026-04-19 分离出去的**冻结副本**，已改名为
  `archive/20260419_RFQAutoControl`，不要再从那里取代码

---

## 8. 版本历史

| 版本 | tag | 说明 |
|---|---|---|
| 2.0.0 | `v2.0.0` | 闭环后通过 setpoint 调节功率到目标值（新增 `AUTO_REGULATING` 状态、`adjust_setpoint()`、`AutoC_SetpointStep` / `AutoC_SetpointMargin` 两个 PV）；同时修正 `__version__` 的遗留错误值 `3.0.0`，启动横幅/日志/exe 名开始带版本号 |
| V1.0 | `V1.0`（指向 `d8d9252`） | tag 早打错了一个版本，该 commit 实际是 "V1.1"（stable 模块）。**tag 名不可信**，仅作历史留档 |
| — | 无 | 更早的 "V1.1" 等版本只存在于 commit message，无 tag |
