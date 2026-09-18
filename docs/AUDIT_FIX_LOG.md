# 审计问题修复批次记录

> 配套文档：[`CODE_AUDIT.md`](./CODE_AUDIT.md)（问题清单与检查标准）、[`SCRIPTS.md`](./SCRIPTS.md)（脚本清单）。
> 记录规则：每批修复完成后记录「改动内容 / 测试结果 / 环境状态 / 异常」，无异常方可进入下一批。
> 测试环境：后端 `backend/.venv`（Windows）+ 前端本地 vitest；运行环境 WSL-Kali（docker compose，前端 27012）。

## 批次总览

| 批次 | 主题 | 条目 | 状态 |
|---|---|---|---|
| 1 | 正确性：导出 meta 单一实现、复测判定口径统一 | B-1、B-2 | ✅ 完成 |
| 2 | 健壮性：前端伪造成功响应、异常归一化、静默吞异常、种子脚本守卫 | C-2、C-3、C-1、A-4 | ✅ 完成 |
| 3 | 收敛重复：克隆函数与样板抽象 | B-3 ~ B-8 | ✅ 完成 |
| 4 | 体量与解耦：前端拆分、编排下沉、超长函数 | E-1 ~ E-3、D-2 | ⚠️ 部分完成（见批 4 说明） |
| 5 | 规范化：`vul`/`vuln` 规则、前端命名族、`any` 递减 | F-1 ~ F-4、E-5 | ⚠️ 部分完成（见批 5 说明） |
| 6 | 清理：未使用 import、失效脚本、长行、脚本合并废弃 | A-1、A-2、D-1、SCRIPTS | 待执行 |

---

## 批次 1 — 正确性（B-1、B-2）

### 改动内容

1. **新增 `backend/app/services/report_meta.py`**：导出 meta / 版本变更记录 / 章节 / 漏洞与资产构建的唯一实现。
   - `build_export_meta(session, report, *, plan, generator, report_time)`：`generator=None` 表示不注入该键；`report_time=None` 表示交由 `report_builder` 取当前时间（手动导出口径）。
   - `collect_report_records()`：版本记录日期口径统一为「最近成功导出时间 > 报告自身日期 > 导出当天（当前报告）/ 空（其他报告）」。
   - `resolve_plan` / `collect_testers` / `collect_plan_urls` / `build_sections` / `collect_vulns_and_assets`。
2. **`backend/app/services/import_service.py`**：`auto_export_report` 由 147 行降至 33 行，删除重复的 meta/版本记录/章节/漏洞/资产构建（-108 行），注入 `report_time=report.create_time` 以保持导入路径原有的封面日期口径。
3. **`backend/app/workers/main.py`**：`export_report_task` 同步改为调用 `report_meta`（-112 行），不注入 `report_time`（保持手动导出取当前时间的原有口径）；连带清理仅被删除块使用的 `func` / `select` / `Vul` / `TestingPlan` 导入。
4. **B-2 复测判定口径**：两处入口的 4 处内联 `"复测" in title` 全部改为经 `report_meta` → `plan_service.is_retest_report_title`。复核结果：全仓库该内联写法仅剩 `plan_service.py:76`（唯一合法位置）。
5. **新增 `backend/tests/test_report_meta.py`**（2 例）：
   - `test_build_export_meta_flags_and_dates`：参数语义（report_time/generator 注入规则）、初测/复测标记、版本记录日期三级回退；
   - `test_export_entrypoints_share_single_implementation`：**源码级不变量** —— 两处入口不得再出现 `"复测" in (` 或 `meta["report_records"]`。

### 测试结果

| 项目 | 结果 |
|---|---|
| 后端定向（`tests/test_report_meta.py` + `tests/test_report_builder.py`） | 35 passed |
| 后端全量 pytest | **162 passed, 1 skipped**（基线 160 + 新增 2），耗时 305s |
| 前端 vitest | **21 files / 118 tests passed** |
| 镜像重建（WSL-Kali `docker compose build api worker frontend`） | 成功，6 个容器全部 Up |
| 功能验证（admin1/123456） | 登录 200；**22/22 接口返回 200** |

### 异常与处置

- 首次全量测试出现 **13 处失败**（`NameError: name 'func' is not defined` × 11、连带 `MissingGreenlet` × 2）：原因是我在删除重复块时误判 `func` 已不再使用（当时检索用了 `\bfunc\(`，而实际用法是 `func.count(...)`）。已恢复 `from sqlalchemy import func, or_, select`，重跑全量 **0 失败**。
- 附带发现并修复的**环境陈旧问题**：批次开始前的容器镜像构建于 15:03:28，早于提交 `8c16480`（15:40:45），导致 `GET /knowledge/search` 返回 **405**（旧镜像只有 `DELETE /knowledge/{entry_id}` 形成路径部分匹配）。镜像重建后该接口返回 **200**，可作后续批次的「镜像已刷新」判定信号。

### 系统状态

API 容器内 `APP_VERSION = 2.17.1`；postgres/redis healthy；`/knowledge/search` 恢复正常；无 5xx、无异常日志。

---

## 批次 2 — 健壮性（C-2、C-3、C-1、A-4）

### 改动内容

1. **C-3 异常归一化收敛**：新增 `app/core/xlsx.py::load_xlsx()`（与 `xlsx_response` 同处，符合 AGENTS.md「Excel 统一走 core/xlsx.py」），只把**可预期的文件解析异常**（`BadZipFile` / `InvalidFileException` / `ElementTree.ParseError` / `KeyError` / `ValueError`）转为 `HTTPException(400)` 并记录原始异常；其余异常上抛由全局兜底处理。
   - 改造 `app/api/v1/testing_plan.py`（工单导入）与 `app/api/v1/assets.py`（资产导入）改用该方法，各自删除 6~7 行重复的 `try/except`；连带清理仅此使用的 `BytesIO` / `load_workbook` 导入。
   - `app/api/v1/spring_action.py` 的 docx 解析兜底保留 `except Exception`（docx 解析失败模式多，收窄易把用户文件问题变成 500），但改为 `logger.exception` 保留堆栈并 `raise ... from exc`。
2. **C-1 静默吞异常补日志**：
   - `app/services/report_builder.py`：`_resolve_lexer` 两处 `except Exception: pass` → `logger.debug`（保留降级行为）；
   - `app/api/v1/remote_testing.py::_remove_appeal_file`、`app/api/v1/spring_action.py::_remove_report_file`：`except OSError: pass` → `logger.warning`（保留「尽力而为」语义）。
3. **C-2 前端不再伪造成功响应**：`frontend/src/views/ReportList.vue` 两处 `client.get('/testing-plans').catch(() => ({ data: { items: [] } }))` 改为统一的 `loadPlanOptions()`（失败时由 `client` 拦截器提示错误，`plans` 置空），顺带消除重复调用点。
4. **A-4 种子脚本目标库守卫**：`backend/scripts/seed_dev_data.py` 新增 `_assert_dev_database()`，目标 DSN 非本地 `sqlite...dev.db` 时以退出码 2 拒绝执行（原实现仅靠 `setdefault`，环境已导出 DSN 时会清空该库）。
5. **新增测试**（6 例）：`tests/test_xlsx.py`（3 例：非 ZIP 文件→400、正常 workbook 可解析、服务端异常不被吞）、`tests/test_seed_dev_data_guard.py`（3 例：拒绝 PG/非 dev.db、接受 dev.db）。

### 测试结果

| 项目 | 结果 |
|---|---|
| 后端定向（xlsx + 种子守卫 + report_meta + test_api.py） | 90 passed |
| 后端全量 pytest | **168 passed, 1 skipped**（上批 162 + 新增 6） |
| 前端 vitest | 21 files / **118 tests passed** |
| 前端生产构建 `vite build` | 成功（`dist/index.html` 刷新，59 个 assets） |
| 镜像重建 + 重启 | 成功，6 容器 Up |
| 功能验证（admin1/123456） | 登录 200；**22/22 接口 200**；API 日志无异常 |

### 异常与处置

- 新增的种子守卫用例一度导致 `test_report_meta` 报 `socket.gaierror`：原因是该用例在 `monkeypatch.setenv("VP_DATABASE_URL", "postgresql://…")` **期间**才首次导入 `app.core.config`（模块级单例），把进程级 DSN 污染成假 DSN。已改为**在模块导入期**完成 `scripts.seed_dev_data` 导入（此时环境变量仍是 conftest 注入的测试库），用例内只改环境变量后调用守卫函数。**经验：涉及 `os.environ` 的 app 模块导入必须发生在 monkeypatch 之前。**

### 系统状态

正常。`load_xlsx` 使资产/工单导入的失败文案保持 400，同时服务端缺陷不再被伪装；无 5xx。

---

## 批次 3 — 收敛重复（B-3 ~ B-8）

### 改动内容

| 条目 | 实现 | 位置 |
|---|---|---|
| B-3 删除类路由 | 新增 `core/query.py::delete_by_id_if_exists()`（**幂等**：不存在返回 False；不 commit）。三处改为 2 行调用 | `api/v1/imports.py`（批次删除）、`api/v1/knowledge.py`（模板删除）、`api/v1/users.py`（组织删除） |
| B-4 权限依赖 | `core/deps.py` 新增 `_has_perm` / `_has_any_perm`，`require_perm` / `require_pat_perm` / `require_any_perm` 三者共用（保留各自的 403 文案差异） | `core/deps.py` |
| B-5 工单ID 派生 | 新增 `core/ticket_id.py::derive_ticket_id()`；`TestingPlan.ticket_id` 与 `NonpenPlan.ticket_id` 由 8 行克隆降为 1 行调用；文件内注明与 `plan_query` 三处 SQL 表达式须同口径 | `core/ticket_id.py`、`models/special.py` |
| B-6 字典映射 | `docx_parser` 新增 `_map_code(text, mapping)`，`_map_level` / `_map_type` 变为薄封装（匹配口径唯一化） | `services/docx_parser.py` |
| B-7 前端测试 mock | 新增 `src/__tests__/helpers/clientMock.ts`（`getMock` + `clientMockFactory`），4 个 spec 的 9 行样板降为 2 行 | `VulnList/ReportEditor/RemoteTestingList/VulnRetestPanel.spec.ts` |
| B-8 上传落盘 | 新增 `services/upload_store.py::save_upload()`（扩展名/空文件/大小/魔术字节校验 → UUID 命名 → 落盘 → 返回元信息），春耕行动报告上传与远程检测申诉附件上传共用 | `services/upload_store.py`、`api/v1/spring_action.py`、`api/v1/remote_testing.py` |

### 对审计结论的修正（B-8）

审计原判定「远程检测与春耕行动的上传**解析**流程重复」**不成立**：前者是任意格式附件（无解析），后者是 docx 解析出漏洞草稿，业务差异明确。复核后确认真正的重复仅为「读取 → 校验 → UUID 命名 → 落盘 → 返回元信息」约 8 行样板，故本次只抽取该样板，**未合并解析逻辑**（强行合并会引入 ext/magic 策略参数膨胀）。`services/upload_store.py` 的模块 docstring 已记录该修正。

同样地，审计中「`metaFixture` 重复」在复核后**未合并**：`utils/__tests__/colors.spec.ts` 的 fixture 是带字典取值的 `/meta` 契约夹具，而 `VulnList.spec.ts` 的是空字典最小夹具，二者用途不同，合并会降低测试表达力。

### 测试结果

| 项目 | 结果 |
|---|---|
| 后端全量 pytest | **168 passed, 1 skipped**（与上批持平，无回归） |
| 前端 vitest | 21 files / **118 tests passed**（含 4 个改造后的 spec，验证 `vi.mock` + 外部工厂的 hoisting 用法可行） |
| 镜像重建 + 重启 | 成功 |
| 功能验证（admin1/123456） | 登录 200；**22/22 接口 200** |

### 异常与处置

无失败。前置排查：抽取上传落盘前先确认 `uuid` / `Path` 在两个路由文件中仅被上传逻辑使用（grep 全量核对），避免重演批次 1 的 `func` 误删。

### 系统状态

正常。累计新增可复用模块：`core/ticket_id.py`、`services/upload_store.py`、`src/__tests__/helpers/clientMock.ts`。

---

## 批次 4 — 体量与解耦（E-1 ~ E-3、D-2）⚠️ 部分完成

### 已完成

| 条目 | 内容 |
|---|---|
| **E-3 编排下沉** | 新增 `services/report_retest.py`，把 `api/v1/reports.py` 中的 `_create_retest_report`（52 行）、`_report_title_exists`、`_snapshot_vul_edits` 下沉为服务函数（`create_retest_report` / `report_title_exists` / `snapshot_vul_edits`，均去掉下划线前缀）。`reports.py` **净减约 115 行**（含连带清理 `re` / `strip_embedded_retest` 导入），路由层只保留鉴权与响应组装；5 处 `snapshot_vul_edits` 调用与 1 处 `create_retest_report` 调用改为引用服务。 |
| **D-2 超长函数（1/19）** | `api/v1/misc.py::meta`（65 行）拆为 `_name_dicts(session)` / `_color_dicts()` / `_nonpen_dict()` 三个纯函数，路由体降为 6 行；拆分保持响应结构逐键一致（仅对象键顺序变化，JSON 语义无影响）。 |

### 未完成（本批明确遗留，附原因与后续方案）

| 条目 | 原因 | 后续方案 |
|---|---|---|
| **E-1** `PlanWorkflowDrawer.vue`（679 行 / 14 处 `client.*`）拆分 | 属**前端交互重构**，涉及工单流转、漏洞关联、报告导出、复测四类流程的模板与状态联动；本项目无组件级交互测试（现有 4 个视图冒烟用例仅覆盖挂载），无法在无人工 UI 回归的前提下安全拆分 | 按 `usePlanReports` / `usePlanVulLinks` / `usePlanTransitions` 抽 composable（先补组件交互测试再拆） |
| **E-2** `TestingPlanList.vue`（1044 行 / 25 imports / 11 处 `client.*`）拆分 | 同上，且该页承载 7 种工单状态流转与 Excel 导入导出，拆分需配合 UI 回归 | 拆 `TestingPlanFilters` / `TestingPlanForm` / `TestingPlanStats` + 列表壳 |
| **D-2 其余 18 个超长函数** | 其中 `db._migrate_lightweight`(340) 为幂等 DDL 顺序表、`vulns.vuln_stats`(244) 与 `stats_service.build_stats`(179) 为统计聚合、`docx_parser.parse_report_docx`(150) 为解析主循环 —— 均为**核心逻辑**，拆分需逐个补单测后推进，不宜与本次多批次改动混做 | 按 `CODE_AUDIT.md` D-2 表的拆分建议逐个推进，每个函数先补覆盖用例 |

> 说明：`workers/main.py::export_report_task` 已由批次 1 从 168 行降至约 70 行（B-1 顺带完成，故 D-2 的 19 项中实际已有 2 项达标）。

### 测试结果

| 项目 | 结果 |
|---|---|
| 后端全量 pytest | **168 passed, 1 skipped** |
| 前端 vitest | 21 files / **118 tests passed** |
| 镜像重建 + 重启 | 成功 |
| 功能验证（admin1/123456） | 登录 200；**22/22 接口 200** |

### 异常与处置

无失败。改动前先核对 `_snapshot_vul_edits` 的 5 处调用与 `re` / `strip_embedded_retest` 的剩余用途，确认下沉后 `reports.py` 不会残留悬空引用。

---

## 批次 5 — 规范化（F-1 ~ F-4、E-5）⚠️ 部分完成

### 已完成

| 条目 | 内容 | 影响面 |
|---|---|---|
| **F-2 弹窗打开函数命名族** | `openDialog` → **`openFormDialog`**（`useCrudDialog` 的公开 API + 8 个视图 + 1 个 spec） | 39 处 / 11 文件，**旧名残留 0、新名 39 处**（grep 双向校验） |
| **F-3 同名不同义** | `typeName` 拆为语义明确的三个名字：`VulnFormPanel`/`VulnDetail` → `vulTypeName`（漏洞类型名）、`NotifyChannelList` → `channelTypeName`（渠道类型名） | 3 文件 / 6 处 |
| **F-4 弱语义命名** | `statusSoftStyleEx` → **`statusSoftStyleWithRetest`**；`loadAssetLabelsRaw` → **`loadAssetLabelsUncached`** 并补注释说明「绕过缓存」的意图 | 6 文件 / 15 处 + 2 文件 / 4 处 |
| **F-1 命名规则成文** | 在 `AGENTS.md`「后端编码规范」写入漏洞命名域规则：模型 `Vul`(表 `vulns`)、字典域类 `Vuln*`、**实体域新增标识符统一 `vuln_` 前缀**、常量 `VUL_*`；既有 `vul_type`/`vul_id` 等列名保持不变（重命名须双轨迁移，属独立专项）。同时在前端规范补「弹窗打开函数统一 `open<Target>`，`onXxx` 仅用于事件回调」与「测试统一复用 `clientMock`」。 | `AGENTS.md` |

> F-4 命名与审计报告建议不同：审计原建议 `statusSoftStyleRetestDone`，但复核该函数同时处理「复测未通过覆盖状态色」与「普通状态走字典色」两种语义（见 `colors.spec.ts` 用例），`RetestDone` 会误导，故改名为 `statusSoftStyleWithRetest`。

### 未完成（本批明确遗留，附原因与后续方案）

| 条目 | 原因 | 后续方案 |
|---|---|---|
| **F-1 物理重命名**（`vuln_assets` → `vul_assets`、`vuln_service.py` → `vul_service.py` 等） | 涉及 Alembic + `db.py` 双轨迁移、模型字段/关联表名、前端调用面，属**破坏性变更**，必须独立发布窗口执行（MEMORY 记载的「双轨同步铁律」即为此类改动的事故来源） | 单独立项：先加 `DEPRECATED_COLUMNS` 登记与迁移脚本，再分两次发布（先加新名兼容、后删旧名） |
| **F-2 剩余变体** | `onOpen`（`AssetFormDialog` / `TemplatePickerDialog`）语义是**组件生命周期回调**而非「打开动作」，改名为 `open` 会与 `defineExpose({ open })` 冲突且语义错误；裸 `open` 已是组件对外 API（与 `@closed` 对称） | 保留现状，规则已在 AGENTS.md 中区分「动作」与「回调」 |
| **E-5 `any` 递减**（201 处 / 35 文件） | 需要先建立后端 DTO 的前端类型声明（`types/`），再逐文件替换；盲改会引入类型错误且无法被现有测试覆盖 | 按 `CODE_AUDIT.md` E-5 的 hot spot 顺序（TestingPlanList 25 → Dashboard 19 → PlanWorkflowDrawer 17 …）分批推进，每批补 `vue-tsc` 类型检查 |

### 测试结果

| 项目 | 结果 |
|---|---|
| 前端 vitest | 21 files / **118 tests passed** |
| 前端生产构建 | 成功（`vite build`；容器内 `pnpm build` 亦通过，覆盖模板编译） |
| 后端全量 pytest | **168 passed, 1 skipped** |
| 改名完整性校验 | grep 旧名 `openDialog` / `statusSoftStyleEx` / `loadAssetLabelsRaw` / `typeName` **残留 0 处**（模板引用不会被单测捕获，故以双向计数为准） |
| 镜像重建 + 重启 | 成功 |
| 功能验证（admin1/123456） | 登录 200；**22/22 接口 200** |

### 异常与处置

- 3 处替换首次失败（`NonpenPlanList.vue` / `TestingPlanList.vue` 的缩进与预期不符）：按实际读取的行文本重做，未造成部分改名。
- 改名风险控制：`.vue` 模板中对 `openFormDialog` 等标识符的引用**不会**被 vitest 冒烟用例覆盖，故额外做了「旧名残留计数 = 0」的强制校验，避免运行期 `undefined` 调用。

### 系统状态

正常。

---

## 批次 6 — 清理（A-1、A-2、D-1、SCRIPTS）✅ 完成（M-2 / S-5 除外）

### 改动内容

| 条目 | 内容 |
|---|---|
| **A-1 未使用 import 12 处** | 全部移除：`alembic/versions/f7a8b9c0d1e2…py`（`sa`）、`api/v1/imports.py`（`ExportJob`、`Report`）、`api/v1/nonpen.py`（`HTTPException`）、`api/v1/notify.py`（`HTTPException`）、`api/v1/open_api.py`（`parse_str_list`）、`api/v1/vulns.py`（`literal_column`，保留在用的 `case`）、`services/nonpen_service.py`（`AsyncSession`）、`services/plan_service.py`（`Report`）、`scripts/seed_dev_data.py`（`now as tznow`、`ExportJob`、`GroupUser`） |
| **A-2 失效脚本** | 删除 `backend/scripts/migrate_from_insight2.py`；`README.md` / `README_EN.md` 的「旧数据迁移」章节改写为「脚本已删除 + 按当前模型重写指引」 |
| **M-1 脚本合并** | 新增 `backend/scripts/knowledge_data.py`（模板库数据唯一加载实现：`DATA_FILE` + `load_seed_data()` + `SEED_DATA`）；`seed_dev_data.py` 改为从该模块导入；**删除 `seed_knowledge.py`**（其 upsert CLI 是 `sync_knowledge_templates` 的子集）。`backend/scripts/` 由 11 个 / 1 560 行精简为 **10 个 / 1 336 行** |
| **D-1 长行（app 与脚本侧）** | 修复 6 处 >120 字符：`api/v1/users.py`（schema 批量导入换行）、`app/db.py` ×2（ALTER 语句与三字段元组）、`models/special.py`（sqlalchemy 导入换行）、`scripts/seed_dev_data.py:455`（**递进三元表达式抽出 `report_title` 局部变量，并删除其中永假的 `if False` 死分支**）、`scripts/sync_knowledge_templates.py`（argparse 参数换行）。`alembic/versions/*` 的 13 处长行按审计结论**豁免**（迁移文件内容冻结） |
| 文档同步 | `docs/SCRIPTS.md` 更新：总览表（10 个 / 1 336 行）、§3.5 改写为 `knowledge_data.py`、§3.11 标记已删除、§4.1 D-1 与 §4.2 M-1 标记已完成；`docs/CODE_AUDIT.md` 更新范围表、A-1/A-2 状态标注与路线图 |

### 未完成（本批明确遗留）

| 条目 | 原因 | 后续方案 |
|---|---|---|
| **M-2** 一次性脚本共享样板抽 `scripts/_common.py` | 6 个一次性脚本（`fix_*` / `backfill_*` / `migrate_utc_to_utc8`）**在生产上无法用自动化测试覆盖**，抽公共模块需逐个手工冒烟；本轮已连续改动多批，宜留独立窗口 | 按 `SCRIPTS.md` §4.2 M-2 执行（`bootstrap()` / `dry_run_flag()` / `dump_backup()`） |
| **S-5** `migrate.sh` / `upgrade.sh` 硬编码 `sudo docker` | 属运维脚本一致性缺陷（`backup-common.sh` 已用 `$DOCKER` 自适应）；改动会影响生产升级命令，需实机验证 | 统一为 `$DOCKER` 或提供 `--sudo/--no-sudo` 开关 |

### 测试结果

| 项目 | 结果 |
|---|---|
| 后端全量 pytest | **168 passed, 1 skipped** |
| 前端 vitest | 21 files / **118 tests passed** |
| 清理校验（逐条 grep） | 12 处未使用导入**全部无残留**；`seed_knowledge` / `migrate_from_insight2` 引用**全部无残留** |
| 脚本目录 | `backend/scripts/` 10 个 `.py`（含新增 `knowledge_data.py`） |
| 镜像重建 + 重启 | 成功 |
| 功能验证（admin1/123456） | 登录 200；**22/22 接口 200** |

### 异常与处置

无失败。

### 系统状态

正常。`docs/` 现有两份审计文档 + 一份执行记录（本文件）互为参照。

---

## 六批执行总览

| 批次 | 主题 | 状态 | 后端 pytest | 前端 vitest | 功能验证 |
|---|---|---|---|---|---|
| 1 | 正确性（导出 meta 单一实现、复测口径统一） | ✅ | 162 passed / 1 skipped | 118 passed | 22/22 接口 200 |
| 2 | 健壮性（异常归一化、伪造响应、种子守卫） | ✅ | 168 passed / 1 skipped | 118 passed | 22/22 |
| 3 | 收敛重复（克隆函数与样板） | ✅ | 168 / 1 skipped | 118 passed | 22/22 |
| 4 | 体量与解耦 | ⚠️ 部分（E-1/E-2 与 18 个超长函数待专项） | 168 / 1 skipped | 118 passed | 22/22 |
| 5 | 规范化（命名族与规则成文） | ⚠️ 部分（物理重命名与 `any` 递减待专项） | 168 / 1 skipped | 118 passed | 22/22 |
| 6 | 清理（未使用导入、失效脚本、长行、脚本合并） | ✅（M-2/S-5 除外） | 168 / 1 skipped | 118 passed | 22/22 |

各批次均完成：编辑 → 全量后端测试 → 全量前端测试 → WSL-Kali 镜像重建 → admin1/123456 登录与 22 接口探测 → 记录结果，**无一批次跳过测试即进入下一批**。

### 遗留项汇总（后续专项）

1. **E-1 / E-2**：`PlanWorkflowDrawer.vue`（679 行）与 `TestingPlanList.vue`（1044 行）拆分 —— 需先补组件交互测试。
2. **D-2 剩余 18 个超长函数**：按 `CODE_AUDIT.md` D-2 表逐个推进（每个先补覆盖用例）。
3. **F-1 物理重命名**：`vuln_*` / `vul_*` 统一需 Alembic + `db.py` 双轨迁移，属破坏性变更。
4. **E-5**：前端 `any` 201 处递减，需先建 `types/` 声明。
5. **M-2 / S-5**：一次性脚本公共样板与运维脚本 `sudo docker` 一致性。
6. **工具链**：建议引入 `ruff` + `vulture`（本次全部问题均靠人工脚本发现，`CODE_AUDIT.md` §六 P2 已记录）。

---

## 验收方法留痕（可复现）

批次验收使用的临时脚本（已按规范删除）逻辑如下，可随时重建：

1. 在 api 容器内以 **form 表单**方式登录（`/auth/login` 使用 `OAuth2PasswordRequestForm`，非 JSON）：
   `POST http://localhost:8000/api/v1/auth/login`，body `username=admin1&password=123456`；
2. 携带 `Authorization: Bearer <access_token>` 依次 GET 22 个关键接口（`/meta`、`/vulns`、`/vulns/stats`、`/reports`、`/testing-plans`、`/testing-plans/stats`、`/testing-plans/conclusion`、`/nonpen-plans`、`/nonpen-plans/stats`、`/remote-testings`、`/spring-actions`、`/knowledge`、`/knowledge/search?q=注入`、`/search?q=a`、`/assets`、`/users`、`/roles`、`/groups`、`/pats`、`/notify-channels`、`/audit/logs`、`/imports`）；
3. 全部返回 200 视为通过；同时打印容器内 `settings.APP_VERSION`。
4. 执行方式：`docker compose exec -T api python - < <本地脚本>`（WSL-Kali 仓库根）。

---

# 遗留项实施方案（Detailed Backlog）

> 度量口径：行数均为 `[IO.File]::ReadAllLines().Length`（含空行）；后端函数行数由 AST 统计（`end_lineno - lineno + 1`）。
> 通用前置纪律（6 项全部适用）：① 先补覆盖用例再重构；② 每项独立成 PR，不与其它项混提；③ 验收必跑「后端全量 pytest（当前基线 168 passed / 1 skipped）+ 前端 vitest（21 files / 118 passed）+ `vite build`」；④ 涉及运行时的改动需重建 WSL-Kali 镜像并做 admin1/123456 登录 + 22 接口探测。

## 遗留 1（E-1）拆分 `frontend/src/components/PlanWorkflowDrawer.vue`

**现状（实测）**：733 行、15 条 `import`、**14 处直接 `client.*` 调用**（全前端最高）。单组件同时承担：工单状态流转、漏洞关联选择、报告列表与导出、复测记录、资产选择。

**目标**：组件 ≤250 行、组件内 `client.*` 直呼 ≤2 处（其余下沉 composable）。

**步骤**：
1. **前置**：补交互用例 —— `PlanWorkflowDrawer.spec.ts`，复用 `src/__tests__/helpers/clientMock.ts`，覆盖 3 条主路径：① 打开抽屉拉取工单详情与报告列表；② 关联漏洞（搜索 → 选中 → 提交）；③ 导出报告并轮询状态。当前仅 `RemoteTestingList/ReportEditor/VulnList/ErrorPage/VulnRetestPanel/TemplatePickerDialog` 6 个组件/视图级用例，抽屉无覆盖。
2. 抽 `composables/usePlanReports.ts`：报告列表加载、导出提交/轮询、报告闭环标签数据（复用现有 `useExportJobs` 的提交与轮询能力，避免第二份实现）。
3. 抽 `composables/usePlanVulLinks.ts`：候选漏洞搜索/分页、已关联漏洞列表、加入/移除、`useAssetSelect` 协作。
4. 抽 `composables/usePlanTransitions.ts`：状态流转动作表、权限判定（`can_operate` / `isPlanClaimant` 对应的前端判定）、按钮禁用态。
5. 模板按分区拆为 `PlanReportPanel.vue` / `PlanVulLinkPanel.vue`（或至少 `v-if` 分段 + `<template #>`），保留抽屉壳与事件编排。

**验收**：文件 ≤250 行；新增 3 条交互用例通过；`client.*` 直呼 ≤2；工单 7 种状态流转在抽屉内仍可完整操作（人工冒烟）。

**风险/回归点**：抽屉被 `TestingPlanList.vue` 与 `NonpenPlanWorkflowDrawer.vue` 两条路径复用（`NonpenPlanList.vue` 走独立抽屉），改动需同时回归两个列表页；导出轮询与工单「复测完成」标注（`statusSoftStyleWithRetest(60)`）为跨批次的敏感点。

**预估**：1.5~2 天（其中补测试 0.5 天）。

## 遗留 2（E-2）拆分 `frontend/src/views/TestingPlanList.vue`

**现状（实测）**：1110 行、25 条 `import`、11 处 `client.*`、25 处 `any`（四项均为全前端最高）。承载 7 种工单状态流转、Excel 导入/导出、部门透视统计。

**目标**：主文件 ≤300 行；每拆出文件 ≤250 行。

**步骤**：
1. **前置**：补 `TestingPlanList.spec.ts` 交互用例（筛选提交、新增/编辑弹窗保存、批量导出、Excel 导入结果提示）。
2. 拆 `TestingPlanFilters.vue`：筛选栏 + 快捷筛选（含 `FilterBuilder` 复用；注意 MEMORY 记载的 `.el-input__wrapper` flex 拉伸坑，日期区间需 `!grow-0`）。
3. 拆 `TestingPlanForm.vue`：新增/编辑弹窗（含测试项勾选、资产选择 `usePlanAssetLink`、人天计算展示）。
4. 拆 `TestingPlanStats.vue`：统计卡 + 部门透视 ECharts（配置外置为 `buildDeptSeries()`）。
5. 抽 `composables/usePlanExcel.ts`：模板下载/导入/导出（`saveBlob` + `xlsx` 响应）。
6. 主文件只保留：列表壳、分页排序（`useListPage`）、行操作与抽屉/弹窗编排。

**验收**：主文件 ≤300 行；7 种状态流转冒烟通过；导入/导出与模板下载可用；vitest 全量通过。

**风险/回归点**：Excel 导入失败提示文案与 `failed/created/updated` 统计（`TestingPlanList.vue` 的 `ElMessageBox` 富文本提示）；`useListPage('/testing-plans')` 的 `extraParams` 与筛选态同步。

**预估**：2 天（含补测试 0.5 天）。

## 遗留 3（D-2）其余 18 个超长函数（当前实测）

| 档位 | 函数（当前行数） | 拆分方案 |
|---|---|---|
| 低风险（纯组装/映射） | `api/v1/vulns.py:132 _build_vuln_conditions`(89)、`api/v1/knowledge.py:133 search_entries`(87)、`api/v1/imports.py:101 batch_confirm_batches`(87)、`services/plan_query.py:82 plan_conditions`(82)、`services/plan_query.py:354 compute_plan_stats`(77)、`services/plan_query.py:433 compute_conclusion`(75)、`services/plan_io.py:107 upsert_plans`(71)、`api/v1/testing_plan.py:353 complete_plan_no_vuln`(70) | 每个筛选/统计维度抽 `_cond_xxx()` / `_build_xxx()`；批量循环体抽 `_confirm_single(batch)` / `_upsert_row(row)` |
| 中风险（聚合 SQL / 统计口径） | `api/v1/vulns.py:294 vuln_stats`(244)、`services/stats_service.py:12 build_stats`(179) | 拆 `_stats_scope_stmt(filters)` + `_count_by(col)` + `_assemble(rows)`；每个图表一个 `_build_xxx()` 返回 dict 片段 |
| 高风险（幂等 DDL / 解析主循环 / 状态机） | `db.py:22 _migrate_lightweight`(347)、`db.py:410 init_db`(79)、`services/docx_parser.py:502 parse_report_docx`(150)、`services/docx_parser.py:122 parse_docx`(68)、`services/vuln_service.py:238 sync_plan_retest_state`(77) | ① 迁移：抽通用「加列」helper `_ensure_columns(conn, table, specs)` + 按域分组 `_migrate_imports/_migrate_reports/_migrate_special/_migrate_assets`，先补 `tests/test_lightweight_migration.py`（旧结构 → 迁移 → 断言列存在，连跑两次验幂等）；② `init_db` 拆「建表 / 轻量迁移 / 种子」三段；③ 解析：`_parse_cover/_parse_summary_table/_parse_detail_sections/_parse_schedule`（可扩展 `test_parser.py` 现成的 `_make_docx`）；④ `sync_plan_retest_state` 拆 `_plan_closure_status()` + `_apply_transition()`，**语义不得变**（工单级口径，护栏为 `tests/test_plan_retest_sync.py` 现有 6 例） |
| 已达阈值边缘（可暂缓） | `workers/main.py:81 export_report_task`(68)、`api/v1/reports.py:495 retest_report`(72) | `export_report_task` 已在批 1 由 168 行降至 68，仅超阈 8 行；`retest_report` 的章节复制已下沉 `report_retest.py`，剩余为参数校验与响应组装，建议保留 |

**验收**：目标函数全部 ≤60 行；相关测试全绿；`pytest` 全量不低于 168 passed；`db.py` 改动额外跑一次 `alembic upgrade head`（SQLite/PG 双轨一致性由 `tests/test_schema_consistency.py` 守卫）。

**预估**：低风险 8 个 ×0.5 天 = 4 天；中风险 2 个 ≈ 2 天；高风险 5 个 ≈ 5~6 天 → 合计 **9~12 天**，建议按档位拆 3 个 PR（低 → 中 → 高）。

### E-1 启动记录（2026-09-17 续：先补护栏，再抽取）

> 位置说明：本节属「遗留 1（E-1）」的执行记录，按依赖顺序先做「前置交互测试」，再做第一处 composable 抽取。

**步骤 1：补交互测试（护栏，完成）** —— 新增 `frontend/src/components/__tests__/PlanWorkflowDrawer.spec.ts`（3 例）：
1. 打开抽屉拉取「工单详情 + 关联漏洞（含 `testing_plan_id` 过滤）+ 导入序号映射」并渲染系统名；
2. 点击「认领」触发 `POST /testing-plans/{id}/claim` 且随后重新拉取工单详情（认领 → 刷新链路）；
3. 点击「生成报告」展开表单（需求 8 的自动命名路径）。

配套改动：共享 mock 助手 `src/__tests__/helpers/clientMock.ts` 增加导出 `postMock` / `putMock` / `deleteMock`（原仅 `getMock`，写操作无法断言；此前的「认领」用例正是因此漏判 —— 第一次跑该用例失败，暴露了助手的能力缺口）。改动向后兼容，其余 4 个使用该助手的 spec 不受影响。

**步骤 2：第一处抽取 —— 报告导出簇（完成）** —— 新增 `frontend/src/composables/useReportExports.ts`：
- 迁出内容：`exportJobs` / `exporting` / `expandedExportId` 三个视图态 + `loadJobs` / `toggleExportList` / `stopPolling` / `pollJobs` / `doExport` / `download` / `removeExportJob` 七个函数 + `onBeforeUnmount(stopPolling)`（原 733 行组件里的 ~55 行）；
- 复用关系：单任务提交/下载仍复用既有 `useExportJobs`，新 composable 只负责「多报告视图态 + 轮询」；
- 系统名兜底改为传入 getter（`() => plan.value?.system_name ?? 'report'`），避免 composable 反向依赖组件状态；
- 新增 `resetExportState()` 供抽屉打开时重置（等价原两行重置 + 停止遗留轮询）。

**验证结果**：

| 项目 | 结果 |
|---|---|
| 残留引用自检 | `fetchJobs` / `submitExport` / `downloadJob` / `deleteExportJob` / `pollTimer` / `onBeforeUnmount` 在组件中**残留 0 处** |
| `PlanWorkflowDrawer.vue` 行数 | **733 → 681**（-52） |
| 前端全量 vitest | **22 files / 121 tests passed**（新增 1 文件 3 例；3 例交互测试在抽取后仍全绿 → 行为未变） |
| 前端生产构建 | 通过（`dist/index.html` 刷新） |

**E-1 完成（2026-09-17 续）：全部动作与状态下沉为 5 个 composable**

| composable | 迁出内容 |
|---|---|
| `composables/usePlanDetail.ts` | `plan`/`vulns`/`loading`/`dirty`/`statusMap`/`vulStatusMap`/`importSeq` + `refresh()`（含导出历史预取，经 `prefetchJobs` 回调注入）+ `ensureStatusDict()` + `reloadAfterChange()` + `claim()`/`quit()` |
| `composables/usePlanVulnPicker.ts` | 选择器 7 个状态 + `pickerLinkedIds` + `openVulnPicker()`/`loadPickerVulns()`/`attachPickerVulns()` |
| `composables/usePlanVulnFlow.ts` | `transitionsMap` + `loadTransitions()`/`transition()` |
| `composables/usePlanReports.ts` | 报告/无漏洞表单 9 个状态 + `toggleGenForm()`/`generateReport()`（相似性检查二次确认拆为 `confirmIfSimilar()`）/`removeReport()`/`startRetest()`/`openNoVulnDialog()`/`completeNoVuln()` |
| `composables/useReportExports.ts` | 导出一簇（前一轮已抽），本轮补 `dropReport()` 供报告删除时回收导出记录与展开态 |

**关键设计**：统一「变更后重载」原语 `reloadAfterChange()`（置脏 + 刷新），替代原先各动作函数里散落的 `dirty.value = true; await refresh()`（原 **9 处**重复样板）；composable 只通过 getter 回调读取组件状态（`getPlanId`/`getSystemName`/`getVulnIds`…），不反向依赖组件 ref。

**E-1 最终验证**：

| 项目 | 结果 |
|---|---|
| `PlanWorkflowDrawer.vue` 行数 | **733 → 514**（-219，-30%；其中 `<script setup>` 由 396 行降至 ~176 行） |
| 组件内 `client.*` 直呼 | **0 处**（目标 ≤2），`ElMessage`/`ElMessageBox`/`dayjs`/`sortPlanVulns`/`fetchMeta` 残留 **0 处** |
| 新增/改动文件 | 4 个 composable 新增 + `composables/useReportExports.ts` 补 `dropReport` + 组件瘦身 |
| 前端全量 vitest | **22 files / 121 tests passed**（3 例抽屉交互测试在每轮抽取后均全绿） |
| 前端生产构建 | 通过（`dist/assets` 完整、`index.html` 刷新） |

> **保留说明（与后端 D-2 同一口径）**：337 行 `<el-drawer>` 模板未拆分。模板内是单一直线式布局（步骤条 → 信息区 → 漏洞表 → 报告区 → 弹窗），拆分需引入插槽/子组件通信反而增加耦合，属「功能原因必须保持聚合」的情形。

**E-2 方案（已勘定目标与缝，下一步执行）**：目标文件为 **`views/TestingPlanList.vue`**（1110 行；模板块 1–433，`<script setup>` 435–1027 共 593 行，样式 1029–1110；**不是** `components/` 目录）。列表查询已复用 `useListPage('/testing-plans')`，剩余 12 处 `client.*` 直呼构成 5 个可下沉单元：

| 拟抽 composable | 行区间（现状） | 内容 |
|---|---|---|
| `useConclusionPanel` | 508–545 | `loadConclusion` / `copyConclusion` / `downloadConclusion`（结论统计与导出） |
| `usePlanFilterRules` | 546–620 | `loadFilterRules`（localStorage 持久化）/ `isRuleComplete` / `onFiltersChange` / `loadDims` |
| `usePlanStats` | 773–810 | `loadStats` / `renderMonthChart`（echarts 月度图） |
| `usePlanImportExport` | 811–866 | `reload` / `exportExcel` / `downloadTemplate` / `doImport` / `onImportExport` / `onImportFileChange` |
| `usePlanForm` | 867–1010 | 表单弹窗与保存（`openFormDialog`/`save`/`remove`）+ 字典即时新增（`addTestType`/`addDepartment`）+ 资产标签与工单流程入口 |

共用依赖 `filterParams()`（748–772，被结论/统计/导出三处复用）应随 `useListPage` 的筛选态一起下沉，避免三份重复拼装；执行顺序建议「结论 → 筛选规则 → 统计 → 导入导出 → 表单」（由独立到耦合），每步用交互测试 + vitest + 生产构建验证。

#### E-2 执行记录（2026-09-17 续）

**步骤 1：补交互测试（护栏，完成）** —— 新增 `src/views/__tests__/TestingPlanList.spec.ts`（2 例）：① 挂载时并行拉取「列表 + 统计 + 结论 + 字典」并渲染工单行；② 结论文本渲染进面板、且结论接口带上 `filterParams()` 拼装的同口径参数。

> **测试环境坑（已解决，后续页面级测试请照此处理）**：该页用 echarts 画月度图，而 jsdom 无 canvas 上下文 → `setOption` 抛 `Cannot set properties of null (setting 'dpr')`、卸载时 `dispose` 抛 `Cannot read properties of null (reading 'clearRect')`（表现为 2 例失败 + 2 个 unhandled rejection，**并非产品缺陷**）。解法：spec 内 `vi.mock('echarts', () => ({ init: () => ({ setOption, resize, dispose }) }))` 打桩；真实渲染由浏览器构建产物与手工验证覆盖。另外本页依赖 `stores/auth` 与 `stores/theme`，两个 store 都要 mock（否则 pinia 未激活会直接抛错）。

**步骤 2：`usePlanConclusion`（完成）** —— 迁出 `conclusionPanel`/`conclusion`/`conclusionLoading` + `loadConclusion()`/`copyConclusion()`/`downloadConclusion()`；筛选口径以 `getFilterParams` 回调注入（组件传 `filterParams`，保持与列表/统计同源）。

**步骤 3：`usePlanStats`（完成）** —— 迁出维度常量 `DIMENSIONS`（组件以 `PLAN_STAT_DIMENSIONS` 别名再导入供模板 `v-for` 使用）、`statsPanel`/`dims`/`stats`/`statsLoading`/`monthChartRef`/`cardDims`、`loadDims()`（localStorage 持久化）、两个 watcher（维度变化重绘 / 面板展开与明暗切换重建）、`loadStats()`、`renderMonthChart()`，并新增 `resizeChart()`/`disposeChart()` 两个生命周期出口（替代组件里直接 `monthChart?.resize()/dispose()`）。
**顺带清理**：组件内 `echarts` / `chartThemeName` / `useThemeStore` / `nextTick` 导入随之下沉或变为未使用，已一并移除（残留自检均为 0）。

**E-2 阶段验证**：

| 项目 | 结果 |
|---|---|
| `views/TestingPlanList.vue` 行数 | **1110 → 1004**（已完成 2/5 单元） |
| 残留引用自检 | `echarts` / `chartThemeName` / `theme.` / `loadDims` / `STATS_DIMS_KEY` 均 **0 处** |
| 前端全量 vitest | **23 files / 123 tests passed**（新增 1 文件 2 例；两轮抽取后均全绿） |
| 生产构建 | 通过 |

**步骤 4：`usePlanFilters`（完成）** —— 迁出快捷筛选（`quickFilters`/`pending`/`quickFilterCount`）、时间区间（`rangeKind`/`customRange`/`onRangeChange`）、聚合筛选（`filterVisible`/`rules`/`isRuleComplete`/`filterCount`/`onFiltersChange`/`disposeFilters`）与 **`buildParams()`（列表/统计/结论/导出四处唯一的参数口径）**。
**循环依赖解法**：`useListPage({ extraParams: filterParams })` 需要 `filterParams`，而 `filterParams` 需要筛选状态 → 用**函数声明提升**（`function filterParams()` 引用已初始化的 `usePlanFilters` 返回值）+ 把「筛选变化」以 `triggerReload()`（函数声明）回传，`usePlanFilters` 不反向依赖 `useListPage`。
> **测试抓到真实回归（护栏价值实证）**：首版把 `sort` 当 Ref 取 `sort.value`，但 `useListPage` 返回的 `search` 是 Ref、**`sort` 是响应式对象**（见 `ListPageState`）→ `filterParams()` 抛 `Cannot read properties of undefined (reading 'prop')`，列表与结论接口双双未发出（2 例失败）。修正为 `buildParams(search.value, sort)` 后全绿。**该口径已写入代码注释，后续改 `useListPage` 返回值时必须同步。**

**步骤 5：`usePlanImportExport`（完成）** —— 迁出 `importing`/`importInputRef` + `exportExcel`/`downloadTemplate`/`doImport`（失败明细弹窗）/`onImportExport`（下拉命令分发）/`onImportFileChange`；导入后的「回首页 + 刷新统计」以 `onImported` 回调注入。

**步骤 6：`usePlanCrud`（完成）** —— 迁出 `dialogVisible`/`saving` + `save`（剔除服务端派生字段 + URL 清洗 + 新建/编辑分支）/`remove`/`addTestType`/`addDepartment`；字典重载与保存后刷新分别以 `loadTestTypes`/`loadDepartments`/`onSaved` 注入。

**E-2 最终结果**：

| 项目 | 结果 |
|---|---|
| `views/TestingPlanList.vue` 行数 | **1110 → 854**（-256，-23%） |
| 组件内 `client.*` 直呼 | **0 处**（原 12 处全部下沉） |
| 新增 composable | `usePlanConclusion` / `usePlanStats` / `usePlanFilters` / `usePlanImportExport` / `usePlanCrud`（5 个） |
| 前端全量 vitest | **23 files / 123 tests passed** |
| 生产构建 | **✓ built in 13.19s** |

**按「功能原因必须聚合」保留（不拆分，理由明确）**：
1. **表单 schema 与校验**（`emptyForm` 422 行附近、`requireNonpenItems`/`requireTicketSource`/`planRules`）：与模板字段一一对应，且校验规则直接读取表单值，拆出后只能靠参数来回传，反而增加耦合；
2. **字段级 computed**（`testTypeOptions`/`departmentOptions`/`statusEditable`/`statsAuto`/`mandaysAuto`/`autoMandays` + `onCorrectMandays`/`onCancelMandays`）：纯展示派生，逻辑一行且与模板绑定；
3. **关联资产交互层**（`loadAssetLabels`/`openCreateAsset`/`onAssetCreated`/`onAssetsChange`）：其真实逻辑已在既有 `composables/usePlanAssetLink.ts`，页面内只是模板适配；
4. **流程抽屉入口**（`workflowVisible`/`workflowPlanId`/`openWorkflow`/`onWorkflowChanged`）：3 行状态 + 2 个直通函数。

### 遗留 3 修订（2026-09-17 续：逐项复评，「功能确需超长则保留」）

评审原则：**只拆「体内存在可独立命名、且拆分点不跨事务/状态边界」的部分**；若超长主要来自
①参数面/文档、②顺序 DDL 直线逻辑、③解析状态机与跨段共享状态、④事务 commit 边界，
则判定为「合理长」并**保留**，只补注释说明，不做形式化拆分。

**已拆（8 个，低风险档全部完成）**：
| 函数 | 前 → 后 | 手段 |
|---|---|---|
| `services/plan_query.py::plan_conditions` | 82 → **≤60（已移出清单）** | 抽 `_append_date_range()`（合并两处重复的「上界排除空串」逻辑）、`_append_tester_scope()`（三态并集）、模块常量 `_TESTER_ACTIVE_STATUSES`（原两处重复字面量） |
| `api/v1/vulns.py::_build_vuln_conditions` | 89 → **63** | 抽 `_append_in_or_eq()` / `_append_asset_in_or_eq()` / `_append_test_type()`；并把「文本维度用真值判断、id 维度用 `is not None`」统一为 `None` 单一口径（调用前把空串归一为 `None`，行为等价） |
| `services/plan_query.py::compute_plan_stats` | 77 → **≤60（已移出清单）** | 抽 `_stats_by_status()` / `_count_retest_rounds()` / `_sum_amount()`（三个求和共用，含可选附加条件）/ `_month_buckets()` + `_vulns_by_month()` |
| `services/plan_query.py::compute_conclusion` | 75 → **≤60（已移出清单）** | 抽 `_rectify_state()` / `_plan_vuln_count()` / `_conclusion_summary()`；计数分支改为直接用 `p.status` 判定（不再用文案字符串反推）；收尾轮再抽 `_conclusion_aggregate()`（取工单 + 关联漏洞计数 + 行构造整体下沉） |
| `api/v1/knowledge.py::search_entries` | 87 → **≤60（已移出清单）** | 抽 `_apply_search_filters()`（类型/等级/创建人/时间区间）、`_keyword_match()`（匹配条件 + 相关度打分表达式）、`_apply_search_order()`（相关度/白名单排序与回退） |
| `api/v1/imports.py::batch_confirm_batches` | 87 → **≤60（已移出清单）** | 抽 `_precheck_confirm_targets()`（统一工单/资产前置校验）、`_count_parsed_records()`、`_confirm_one_batch()`（单批次确认 + 失败仅回滚本批次 + 审计），主函数按 `item.status` 汇总计数 |
| `services/plan_io.py::upsert_plans` | 71 → **≤60（已移出清单）** | 抽 `_load_occupied_tickets()`（库内工单ID占用表）、`_apply_cells()`（一行 Excel → 计划实体的字段映射） |
| `api/v1/testing_plan.py::complete_plan_no_vuln` | 70 → **≤60（已移出清单）** | 抽 `_ensure_no_vuln_completable()`（权限/状态/无关联漏洞三重校验）、`_notify_no_vuln_done()`（站内信收件人去重与文案） |

**评估保留（不再拆分，附理由）**：
| 函数 | 现状 | 保留理由 |
|---|---|---|
| `api/v1/vulns.py::_build_vuln_conditions` | 63 | 逻辑体已拆净，剩余长度来自 **22 行参数面 + 12 行文档**；若将来要压到 40 以内，应引入 `VulFilterQuery` 数据类承载参数，而非再切函数 |
| `db.py::_migrate_lightweight` | 347 | **幂等 DDL 顺序表**（逐列「查 PRAGMA → ALTER」直线逻辑）；拆函数会导致 `conn` 与列集合反复传参、并破坏「一段一表」的可读顺序，且它是 SQLite 生产等效迁移路径，回归风险 > 收益。仅建议按域补分隔注释 |
| `db.py::init_db` | 79 | 三段直线（建表 → 轻量迁移 → 种子），无嵌套分支 |
| `services/docx_parser.py::parse_report_docx` / `parse_docx` | 150 / 68 | 解析主循环为**状态机**，分段之间共享 meta/records/样式上下文，拆分会引入大量跨函数状态传递 |
| `services/vuln_service.py::sync_plan_retest_state` | 77 | **工单级复测口径的唯一实现**，语义敏感（有 6 例回归护栏）；拆分的收益（可读性）远低于误改语义的风险 |
| `services/import_service.py::confirm_batch_internal` | 99 | 单批事务主流程，拆分点会跨越 `commit` 边界（批量场景要求按批次独立提交/回滚） |
| `workers/main.py::export_report_task` | 68 | 批 1 已由 168 行降至 68（薄编排），仅超阈 8 行 |
| `api/v1/reports.py::retest_report` | 72 | 编排已下沉 `services/report_retest.py`，剩余为参数校验 + 响应组装 |

**仍需拆（2 个，均属中风险档，排在本路线「步骤 4」执行）**：
| 函数 | 行数 | 拆分方向 |
|---|---|---|
| `api/v1/vulns.py::vuln_stats` | 244 | `_stats_scope_stmt(filters)` + `_count_by(col)` + `_assemble(rows)`；改动须与列表筛选口径保持一致 |
| `services/stats_service.py::build_stats` | 179 | 每图表一 `_build_xxx()` 返回 dict 片段 |

> **最新实测（收尾轮结束后）**：`app/` 内 >60 行函数已由审计时的 **19 个降至 11 个**，构成 =
> **8 个已完成拆分**（低风险档全清）+ **9 个经评估保留**（`_migrate_lightweight`、`init_db`、`parse_report_docx`、
> `parse_docx`、`sync_plan_retest_state`、`confirm_batch_internal`、`export_report_task`、`retest_report`、
> `_build_vuln_conditions`(63)）+ **2 个待拆（中风险）**。
> 原先列为「高风险」的 5 项中有 4 项经评估取消；D-2 剩余工作量约 **2 天**（仅中风险 2 个）。

### 收尾轮异常与处置（重要经验）

**问题**：拆分 `search_entries` / `batch_confirm_batches` 时，把新增的模块级辅助函数**插入到了 `@router.get/post` 装饰器与路由函数之间** → 装饰器被绑定到辅助函数上，`search_entries` / `batch_confirm_batches` **失去路由**，全量测试立即报 `FastAPIError`（3 failed + 88 errors）。
**处置**：把装饰器移回路由函数正上方后重跑全量 → **168 passed / 1 skipped**。
**教训（拆路由文件内的函数时必须遵守）**：辅助函数一律插在**装饰器之前**；每次拆完必须跑全量测试（`ruff` 不会发现此类语义错误，只有实际构造 app 的测试能拦住）。已记入 MEMORY。

## 遗留 4（F-1）`vul` / `vuln` 物理重命名

**现状**：AGENTS.md 已固化规则（见批 5），但符号层面仍并存。当前 alembic 迁移 **25 个**；生产/开发双轨迁移由 `app/db.py::_migrate_lightweight`（幂等加列）+ Alembic 承担，重命名守卫为 `tests/test_schema_consistency.py` 的 `DEPRECATED_COLUMNS`。

**建议方案（两阶段、可回滚，且只做爆炸半径可控的子集）**：
- **阶段 A（新增别名，不破坏）**：仅改**代码标识符**，不动列名 —— 模块 `services/vuln_service.py` → `services/vul_service.py`（保留一层 re-export 兼容旧 import 路径）、局部变量/参数名统一 `vul*`。
- **阶段 B（列名统一，需迁移窗口）**：仅统一**外键列名** `report_sections.vul_id` → `vuln_id`（与 `import_records.vuln_id` 对齐）：新增列 → 双写 → 回填 → 删旧列 → 同步 `DEPRECATED_COLUMNS`；`vul_type`（字段名）**保持不动**以控制范围。
- **不做**：`vuln_assets` 表名、`vuls`/`vulns` 表名等大范围重命名（收益仅为一致性，风险为生产数据迁移）。

**判据（何时做）**：若未来 3 个月无其它 DB 变更窗口，则**只保留 AGENTS.md 规则、不执行重命名**；若有窗口，则阶段 A 可立即做（零迁移风险），阶段 B 随窗口执行。

**验收**：阶段 A —— 全量 pytest + 22 接口探测通过、`rg 'from app.services.vuln_service'` 为 0；阶段 B —— `alembic upgrade head` 在 SQLite 与 PG 均通过、`test_schema_consistency` 通过、双写期数据一致性抽查。

**预估**：阶段 A 0.5 天；阶段 B 1~1.5 天（含迁移与回滚演练）。

## 遗留 5（E-5）前端 `any` 201 处 / 35 文件递减

**现状**：`frontend/src/types/` **不存在**；`any` 分布 Top：`TestingPlanList.vue` 25、`Dashboard.vue` 19、`PlanWorkflowDrawer.vue` 17、`VulnFormPanel.vue` 14、`ReportList.vue` 13、`AssetFormDialog.vue` 13。

**步骤**：
1. 新建 `frontend/src/types/`：`api.ts`（`Page<T>`、`ApiError`、`DictMeta`）+ `domain.ts`（`Vul`、`TestingPlan`、`Report`、`Asset`、`KnowledgeEntry`）。**类型来源**：以后端 `/api/openapi.json`（DEBUG 下开放）用 `openapi-typescript` 生成基线，再手工收敛 —— 避免两份类型定义漂移。
2. 加护栏：把 `vue-tsc --noEmit` 纳入本地检查（注意 MEMORY 记载：Windows 下不要用 `pnpm test`，同理建议直接用本地 `node .\node_modules\vue-tsc\bin\vue-tsc.js --noEmit`）。
3. 递减顺序（先易后难，与 E-1/E-2 拆分**合并进行**，拆组件时顺手定类型）：`AssetFormDialog`(13) / `ReportList`(13) / `VulnFormPanel`(14) → `Dashboard`(19) → `PlanWorkflowDrawer`(17) → `TestingPlanList`(25)。
4. 约定：`reactive<any>({...})`（如 `views/UserList.vue:126` 的 `userForm`）改为具体接口；`ECharts option` 等确实动态的结构保留 `any` 并加注释说明原因；`catch (e: any)` 改为 `unknown` + 类型守卫（配合 `client.ts` 的 `toastError`）。

**验收**：`any` 总数下降到 ≤50（目标值，可分批）；`vue-tsc --noEmit` 与 `vite build` 无错误；vitest 全量通过。

**预估**：与 E-1/E-2 合并后约 1~1.5 天（单独做约 3 天）。

## 遗留 6（M-2 / S-5）脚本样板与 docker 命令一致性

### M-2：抽 `backend/scripts/_common.py`
**涉及 6 个一次性脚本**：`fix_plan_retest_state.py`(109)、`fix_retest_section_dup.py`(112)、`repair_report_section_order.py`(87)、`backfill_retest.py`(50)、`backfill_vul_submit_time.py`(73)、`migrate_utc_to_utc8.py`(81)。

**重复项（实测）**：`sys.path.insert(...)` 6 处、`logging.getLogger("sqlalchemy.engine").setLevel(WARNING)` 5 处、`"--dry-run" in sys.argv` 5 处、`storage/backups/` JSON 备份 2 处，以及「dry-run 需先取纯数据快照再 rollback（规避 `MissingGreenlet`）」的隐式约定。

**方案**：`_common.py` 提供 `bootstrap()`（sys.path + 日志静默）、`dry_run_flag()`、`save_backup(records, prefix)`、`run(main)`；把 `MissingGreenlet` 规避写进 `run()`，使约定由代码保证而非注释。

**验收（关键难点：这些脚本无自动化测试）**：
- 每个脚本在**开发库**上以 `--dry-run` 冒烟（空库也必须正常输出「0 条」而非报错）；
- 对有数据的 dev.db 至少各跑一次真实路径（先 `pg_dump`-等价备份 / 对 SQLite 直接复制 `dev.db`）；
- 输出文案与退出码保持与改造前一致（前后 diff 一次）。

**预估**：0.5 天。

#### M-2 执行记录（2026-09-18 完成，6/6）

**迁移结果**：6 个脚本全部改走 `_common`，仅保留「为了让 `scripts` 包可导入」的两行 `sys.path.insert`：

| 脚本 | 行数 | 备注 |
|---|---|---|
| `backfill_retest.py` | 50 → **47** | 无备份 |
| `backfill_vul_submit_time.py` | 73 → **69** | 无备份 |
| `fix_plan_retest_state.py` | 109 → **100** | 备份改用 `save_backup(pending, "plan_retest_state")` |
| `fix_retest_section_dup.py` | 112 → **98** | 备份改用 `save_backup(records, "report_sections_retest", indent=None)`（保留原紧凑格式） |
| `repair_report_section_order.py` | 87 → **83** | 无备份 |
| `migrate_utc_to_utc8.py` | 81 → **76** | **特例**：原本就没有 `sys.path`/日志静默样板（靠 `python -m` 的 cwd 导入），故未凭空补；仅去掉 sync 包装与手动 argv 解析 |
| `_common.py` | 70 → **86** | 见下方「关键修正」 |

`backend/scripts/` 目录合计 **1 403 → 1 387 行**。

**关键修正（勘察阶段发现的隐患）**：`save_backup()` 原实现写死 `backend/storage/backups`，而两个脚本的真实约定是 `settings.storage_sub("backups")`（尊重 `VP_STORAGE_DIR`，容器内为 `/app/storage/backups`）—— 直接沿用会让**备份落到错误目录**。已改为后者，并新增 `indent` 参数保留两个脚本各自的 JSON 格式差异（`indent=None` 为紧凑）。
**同时约束**：`settings` 必须**函数内延迟导入** —— 顶层导入会在 `import scripts._common` 时即加载 `app.core.config`，若必填环境变量（如 `VP_SECRET_KEY`）缺失，会连带让只用 `run()` 的脚本无法启动。已实测：不设 `VP_SECRET_KEY` 时 `import scripts._common` 正常。

**关于「把 `MissingGreenlet` 规避写进 `run()`」的取舍**：实勘发现三个脚本的快照代码形态各异（工单+漏洞计数 / 章节新旧正文对 / 报告章节重排），无法抽出有意义的公共抽象，且运行期自动 rollback 包装会改变事务语义。故**不引入魔法**：快照代码保留在脚本内（注释精简并指向下方说明），约定固化在 `run()` 的 docstring 中。

**验收证据（全部实测）**：

| 项目 | 结果 |
|---|---|
| `ruff check scripts` | **All checks passed** |
| 改造前后输出/退出码 | 在 dev.db 副本上 4 脚本 × (dry-run + 真实路径) 共 **8 次运行，逐字一致（IDENTICAL）** |
| 备份分支端到端 | dev.db 中两个备份脚本均走「无数据提前返回」，基线覆盖不到 → **造数运行**（把一条工单置 60 且留 1 个未闭环漏洞；给一个章节正文尾部追加复测详情标记）后两脚本均触发备份：输出 `原值已备份：<STORAGE>/backups/plan_retest_state_<ts>.json`、`原值备份：<STORAGE>/backups/report_sections_retest_<ts>.json`，exit=0，落盘文件 **274 / 624 字节且为合法 JSON（各 1 条）**，文件名前缀与迁移前一致 |
| 安全边界 | 全部运行只在 `dev.db` **副本**上进行；存储目录用 `VP_STORAGE_DIR` 指向临时目录，仓库内无 `storage/backups` 产物；临时脚本/副本/输出留存**已全部删除** |

**遗留说明**：`backend/scripts/` 中 `_common.py` 现为 6 个一次性脚本的公共依赖，后续新增同类脚本应直接复用它（`run(main, dry_run=dry_run_flag())`），不要再复制样板。

### S-5：统一 docker 命令前缀
**现状**：`scripts/migrate.sh:10` 与 `scripts/upgrade.sh`（多处）硬编码 `sudo docker`；而 `scripts/backup-common.sh:7-11` 已实现 `DOCKER` 自适应（root → `docker`，否则 `sudo docker`）。

**方案（最小改动）**：在 `scripts/backup-common.sh` 已有的 `DOCKER` 变量基础上，把 `migrate.sh` / `upgrade.sh` 改为 `"${DOCKER:-sudo docker} compose ..."`，并支持 `TALOS_DOCKER` 环境变量显式覆盖（如 `TALOS_DOCKER=docker`）。

**验收**：`bash -n` 语法检查；WSL-Kali（root）下 `bash scripts/migrate.sh` 与 `--help`/失败路径各一次；非 root 环境验证自动降级为 `sudo docker`；**生产实机验证建议与下次发版合并**（升级脚本本身在升级流程中，需谨慎）。

**预估**：0.5 天（含实机验证）。

## 工具链落地：ruff + vulture（2026-09-17 完成）

**安装**：`backend/.venv` 内 `pip install ruff vulture`，并登记到 `backend/requirements-dev.txt`（`ruff>=0.16`、`vulture>=2.16`）。实测版本：ruff **0.16.8**、vulture **2.16**。

**配置**：`backend/ruff.toml`
- `line-length = 120`（**按显示宽度**计，CJK 记 2 列）；`target-version = "py310"`（理由见下方环境问题）；
- `select = ["F", "E501"]`（未使用导入/变量、长行）；
- 按文件例外（原因写在配置注释中）：`app/schemas/__init__.py` → `F401`（按设计重导出）、`alembic/versions/*` → `E501`（迁移内容冻结）、`scripts/seed_dev_data.py` → `E501`（中文演示数据，整改属纯格式 churn）。

**首次扫描与整改（实测）**：

| 工具 | 首次结果 | 处置 | 现状 |
|---|---|---|---|
| ruff | **128 处**：`F401` 92 + `E501` 34 + `F541` 1 + `F841` 1 | 92 条 `F401` 全在 `schemas/__init__.py`（按设计重导出，配置豁免）；`F541`（`seed_dev_data.py` 无占位符 f-string）与 `F841`（`test_api.py` 未使用变量 `r2_id`）已修；`E501` 修复 `app/`、`tests/` 共 9 处（含 4 处中文注释/长字符串换行） | **All checks passed（exit 0）** |
| vulture | `--min-confidence 80` → **0 处**；`--min-confidence 60` → 307 处（以 SQLAlchemy/Pydantic/ORM 字段误报为主） | 以实测为依据采用 **80** 为阈值，不引入白名单文件 | **0 处（exit 0）** |

命令已写入 `AGENTS.md`（常用命令 + 后端编码规范：提交前必须两项全绿）。

**顺带发现的严重环境问题（已登记为新遗留项）**：开发 venv 实测 **Python 3.10.11**（`.venv/pyvenv.cfg` → `python310`），而容器/生产为 **`python:3.12-slim`**（`backend/Dockerfile`）。影响：本地写 3.11+ 语法会直接报错，但容器可运行；存在「本地与容器行为不一致」的隐性窗口。当前处置：ruff `target-version` 取 `py310` 兜住语法面；建议尽快把本地 venv 重建为 3.12（同步 `dev.ps1` / `dev.sh` 的创建逻辑）。

## 附加建议：pytest-cov（未落地）

`requirements-dev.txt` 未加入 `pytest-cov`：本项目测试以 API 端到端为主，覆盖率数字对「重构安全性」的指导价值低于「关键口径必须有断言」。若要做，建议只对 `services/` 与 `core/` 设阈值（`api/v1` 由端到端覆盖）。

## 建议执行顺序（依赖关系）

```
低风险 D-2（4 天）  →  E-1/E-2 前端拆分 + E-5 类型收敛（合并做，3 天）
                    →  M-2 / S-5（1 天，可并行）
                    →  中风险 D-2（2 天）  →  高风险 D-2（5~6 天）
                    →  F-1 阶段 A（0.5 天，随时）  →  F-1 阶段 B（随 DB 变更窗口）
```

**执行进度（2026-09-17）**：

| 顺序 | 项 | 状态 |
|---|---|---|
| 0 | 工具链：ruff + vulture 落地 | ✅ 完成（ruff/vulture 双 0 问题，命令入 AGENTS.md） |
| 1 | 低风险 D-2 | ✅ **完成**：共拆 **8 个**（`plan_conditions`、`_build_vuln_conditions`、`compute_plan_stats`、`compute_conclusion`、`search_entries`、`batch_confirm_batches`、`upsert_plans`、`complete_plan_no_vuln`）；复评**保留 9 个**；`>60 行函数 19 → 11` |
| 2 | E-1/E-2 前端拆分 | ✅ **完成**：E-1 `PlanWorkflowDrawer.vue` **733 → 514** 行（5 个 composable，组件内 `client.*` 直呼 0 处）；E-2 `views/TestingPlanList.vue` **1110 → 854** 行（5 个 composable，`client.*` 由 12 处降至 0 处）；前端 **23 files / 123 tests** + 生产构建通过；两端均有页面级交互测试护栏（新增 5 例），并在真实浏览器完成验收（见「端到端验收记录」） |
| 3 | M-2 / S-5 | ✅ **全部完成**。S-5：新增 `scripts/docker-cmd.sh`，`migrate.sh`/`upgrade.sh` 共 12 处硬编码收敛为 `$DOCKER`（4 脚本 `bash -n` + 非 root 实测 + 预设覆盖实测通过）。M-2：6/6 脚本迁入 `backend/scripts/_common.py`，并修正 `save_backup` 落盘目录口径；`backend/scripts/` **1 403 → 1 387 行**；ruff 全绿 + 8 次运行输出与退出码逐字一致 + 造数触发备份分支验证（详见下方 M-2 记录） |
| 4 | 中风险 D-2（`vuln_stats`、`build_stats`） | ✅ **完成**：`api/v1/vulns.py::vuln_stats` 245 → ≤60 行（三处重复的「漏洞-资产多对多 JOIN」收敛为 `_count_by_asset()`，分组统计与交叉表分别下沉为 `_vuln_group_stats`/`_vuln_asset_stats`/`_pivot_raw_rows`/`_build_pivot`）；`services/stats_service.py::build_stats` 179 → ≤60 行（拆 `_vuln_scope_cond`/`_count_by`/`_top_vul_types`/`_build_trend`/`_agg_linked_vulns`/`_dept_map`/`_by_department_stats`）。`app/` 内 >60 行函数 **11 → 9**（余 9 个均为复评保留项）；ruff 全绿 + 后端全量 **168 passed / 1 skipped** |
| 5 | 高风险 D-2 | ✅ **经复评取消**（4 项判定为合理长：`_migrate_lightweight`、`init_db`、`parse_report_docx`、`parse_docx`；`sync_plan_retest_state` 因语义敏感保留） |
| 6 | F-1 阶段 A / B | ⏳ 未开始 |
| 7 | **新增**：开发 venv 与容器 Python 版本漂移（3.10 vs 3.12） | ✅ **已修复**：`backend/.venv` 实测 **Python 3.12.11**（`pyvenv.cfg` → `cpython-3.12.11`），与容器 `python:3.12-slim` 对齐（ruff `target-version` 仍为 `py310`，上调属独立变更窗口） |
| 8 | E-5 类型收敛（`src/types/` + `any` 递减） | ✅ **完成**：`vue-tsc --noEmit` **39 → 0 错误**（全程保持 0）；`any` **278 → 3**（其中 **2 处为文档化保留边界、1 处为注释误报 → 业务代码 `any` = 0**），共执行 13 批；新增领域类型 40+ 个，统一落在 `src/types/index.ts`。`pnpm typecheck` / `test` / `build` 三门禁齐备并写入 `AGENTS.md`（详见下方「E-5 收口」） |

## E-5 第 1 批执行记录（2026-09-18）

**先解决门禁缺失**：审计为 E-5 定的验收含 `vue-tsc --noEmit` 无错误，但**项目此前从未安装 `vue-tsc`**，即该验收当时不可执行。本批先补齐：`pnpm add -D vue-tsc`（实测 **3.3.11**），随后取基线。

**基线（首次类型检查，改动前）**：**39 个类型错误 / 17 个文件**，暴露出的是**真实存量缺陷**而非噪音 —— `formRef.value` 可能为 undefined（8 处，`?.` 缺失）、`ticket_id` 未在表单类型中声明（2 处，服务端派生字段被前端漏声明）、`ReportEditor` 的 `string | number` 混用（8 处）、`.at()` 需要 ES2022 lib（2 处）。

**本批改动**：
1. `tsconfig.json`：`target`/`lib` 由 `ES2020` 升到 `ES2022`（消除 `.at()` 两条错误；Vite/browserslist 负责降级，不影响产物）。
2. **新增 `src/types/index.ts`**：`QueryParams` / `Page<T>` / `IdName` / `UserBrief` / `Vuln` / `VulnTransition` / `Report` / `ExportJob` / `ExportFormat` / `TestingPlan` / `PlanStats` / `PlanConclusion(+Row)`。**字段均经代码核实**（`grep` 确认使用点），不提前虚构；并在文件头写明「标 `?` 的语义」与「`any` 只允许出现在确实无法静态描述的边界」。
3. **`ExportJob` 单一来源化**：从 `composables/useExportJobs.ts` 上提到 `types/`，原文件改为 `export type { ExportJob }` 转出（消费者 import 路径不变）。
4. **收敛 10 个 composable 的签名**：`usePlanDetail`（`TestingPlan`/`Vuln`/`Report`）、`usePlanVulnFlow`（`Vuln`/`VulnTransition`）、`usePlanVulnPicker`（`Vuln`/`QueryParams`）、`usePlanReports`（`Report`）、`useReportExports`（`Report`/`ExportJob`/`ExportFormat`）、`usePlanStats`（`PlanStats`/`QueryParams`）、`usePlanConclusion`（`PlanConclusion`）、`usePlanImportExport`（`QueryParams`/`{file: File}`）、`usePlanFilters`（`QueryParams`）、`usePlanCrud`（`Ref<TestingPlan>` + `formRef.value?.validate()` + 请求体改用 `Record<string, unknown>` 后**去掉 8 处 `as any`**）。
5. **两个视图**：`TestingPlanList.vue`（`form: Ref<TestingPlan>`、`emptyForm(): TestingPlan`、`dialogRow: TestingPlan | null`、`openFormDialog/openWorkflow` 入参、新增 `statValue()` 取代 `stats[d.key]` 的越界读取）、`PlanWorkflowDrawer.vue`（去 `as any` getter、`canCompleteNoVuln` 改为显式 `s === 10 || s === 20` 窄化）。

**验收结果（本批）**：

| 项目 | 基线 | 现在 |
|---|---|---|
| `vue-tsc --noEmit` 错误 | 39 | **34**（新增 0 —— 唯一"新增"项是同一条 `useExportJobs.ts` 的 ElMessageBox 重载问题因该文件删掉 12 行而位移；已消除 6 条） |
| `any` 命中行数（同一正则） | 278 | **231**（-47） |
| 前端全量测试 | 123 passed | **123 passed** |
| 生产构建 | 通过 | 通过 |

**类型门禁抓到的真实问题（说明该门禁确有价值）**：首轮改动后错误一度升到 43，全部源于**我声明的类型过窄** —— `Report.status` 实为字符串（`reportStatusName/SoftStyle` 入参是 `string`）、`Report` 缺 `all_closed`/`vul_closed`/`vul_total`/`create_time`、`ExportJob` 缺 `error`。按真实用法校准后回到 34。若没有这道门禁，这类"看起来对、实际错"的类型声明会被无声固化。

**命令已入 `AGENTS.md` 与 `package.json`**：`pnpm typecheck`（新增 script）与 `pnpm test`、`pnpm build` 三者构成前端提交前门禁。

### E-5 第 2 批：类型门禁清零（2026-09-18）

**目标**：把 34 条存量错误清到 0（审计对 E-5 的硬性验收就是「`vue-tsc` 无错误」）。

| 错误类别 | 处数 | 修复方式 |
|---|---|---|
| `formRef.value` 可能为 undefined | **11** | 统一补 `?.`（`MainLayout` / `UserList` / `RoleList` / `NonpenPlanList` / `Login` / `KnowledgeList` / `GroupList`×2 / `VulnRetestPanel` / `VulnFormPanel` / `AssetFormDialog`） |
| `ReportEditor` 的索引类型退化 | **10** | 根因是 `report = ref<any>(null)` 使 `v-for` 的索引推断为 `string \| number`；新增 `sections` computed（`ReportSection[]`）并在模板改用，`report.sections` 5 处统一替换；`testRange` 的 getter 加元组断言、setter 显式标注；`onDrop(i)` → `onDrop()`（其定义本就无参，调用多传参属笔误） |
| `SpringActionList` 的 `unknown[]` | **3** | `uniqVulValues` 改为显式入参类型 + 类型守卫过滤（顺带在 `Vuln` 类型补 `layer` 字段，经代码核实） |
| `NonpenPlanList` 的 `ticket_id` | **2** | 该字段是服务端派生、不属表单模型 → 新增 `autoTicketId` computed 只读回显，不再从 `form` 上直接取 |
| `VulnFormPanel` 的 `data` on `AxiosResponse \| null` | **1** | `.catch(() => null)` 后先取响应再解构（`resp?.data`） |
| `NotifyChannelList` 的联合类型字段 | **1** | 配置对象显式声明 `{ recipients?: string[]; url?: string }`，取用改 `config.recipients?.length` |
| `RoleList` 隐式 any 参数 | **1** | `(k: string)` |
| `urls.spec` 的 `tag` 超集 | **1** | 根因是 `UrlLike` 未声明资产 URL 条目的附加字段 → 用索引签名放行（`normalize()` 只读 `url`） |
| `useExportJobs` 的 MessageBox 重载 | **1** | Element Plus 该版本类型未声明 `width` → 断言为 `ElMessageBoxOptions` 并注明原因 |

**验收（E-5 全阶段）**：

| 项目 | 审计时 | 现在 |
|---|---|---|
| `vue-tsc --noEmit` | 39（且当时未装 vue-tsc，无可执行门禁） | **0** |
| `any` 命中行数 | 278 | **230** |
| 前端全量测试 | — | **23 files / 123 passed** |
| 生产构建 | — | 通过 |

**仍待推进**：`any` 从 230 降到审计目标 ≤50。
> **口径说明（2026-09-18 经确认）**：≤50 是**期望值而非硬指标**。逐文件收敛时按业务实际情况判断 —— 确实是「结构由第三方写入、前端不做结构访问」的边界（如 TipTap 富文本 JSON、Element Plus 未声明的选项字段）应以 `unknown`/带注释的断言承载，**不得为凑数字而伪造类型**。硬线只有一条：`vue-tsc` 保持 0 错误。

### E-5 第 3 批：按页收敛（Dashboard / VulnFormPanel，2026-09-18）

**做法**：这两页的 `any` 全部源于「接口载荷未建模」，因此**不动业务逻辑**、只在 `src/types/index.ts` 补领域类型（该文件已是唯一来源），再把内联 `(x: any) => …` 注解删掉交由推导。

| 文件 | `any` | 补的领域类型 |
|---|---|---|
| `views/Dashboard.vue` | **23 → 0** | `DashboardStats` / `DashboardDepartment` / `DashboardTrendPoint` / `NameCount` / `LevelCount` / `TypeCount`（字段取自 `stats_service._by_department_stats` 等真实输出） |
| `components/VulnFormPanel.vue` | **19 → 0** | `VulnForm`（依 `emptyVul()` 逐字段建模，含 `status?`/`id?` 编辑态字段）、`Asset`（含 `public_urls`/`internal_urls`/`owners`）、`KnowledgeTemplate`、`Items<T>`（仅返回 items 的端点）；`Vuln` 补 `asset_ids?` |

**关键手法（可复用）**：
- **axios 泛型钉住响应类型**：`client.get<DashboardStats>('/dashboard/stats')` —— 这是本批最有效的一招。原先 `const { data } = await client.get(...)` 让 `data` 为 `any`，其下所有 `data.trend.map((t: any) => …)` 的注解都在掩盖问题；给出泛型后回调参数自动推导，注解可整片删除。
- **`unknown` 取代 `any`**：TipTap 的 `update:json` 载荷（`RichEditor` 发的是 `editor.getJSON()`）以 `unknown` 承载 —— 比 `any` 更严（必须显式断言才能取属性），又不虚构结构。
- **以类型判定替代宽类型绕过**：Dashboard 原有的 `sourceFilter.value !== ('' as any)` 改为 `typeof sourceFilter.value === 'number'`，运行时行为完全一致（el-select 清空即 `''`），但不再需要断言。
- **参数注解改为 `unknown`**：模板里的 `(el: any) => setVulFormRef(...)` → `(el: unknown)`（该函数本就按 `unknown` 收参）。

**验收**：

| 项目 | 结果 |
|---|---|
| `vue-tsc --noEmit` | **0 错误**（过程中一度出现 3 处隐式 any + 2 处「我声明的类型过窄」，均已按真实用法校准） |
| `any` 命中行数 | **230 → 189**（-41，-18%） |
| 前端全量测试 | **24 files / 138 tests passed** |
| 生产构建 | **✓ built in 12.46s**，`dist/assets` 61 文件 |

**本轮再次印证的同一条规律**：报错里「看起来像业务 bug」的，多数是**我声明的类型不准** —— `Asset.owners` 用 `name` 而非 `UserBrief.realname`、`VulnForm` 缺编辑态的 `status`。**先怀疑类型声明，再动业务代码。**

**下一批候选**：`GroupList` 6、`NotifyChannelList` 6、`UserList` 6、`AssetList` 5、`NonpenPlanList` 5、`TestingPlanList` 5。

### E-5 第 12+13 批：组织用户域 / 其余业务页（一次性完成，2026-09-18）

| 文件 | `any` | 做法 |
|---|---|---|
| `views/GroupList.vue` | **6 → 0** | `Group[]`（`Group` 补 `remark`/`member_count`）、`GroupMember[]`（补 `remark`）；`Map` 计数对 `group_id` 缺省行**跳过**（原先写入 `undefined` 键、永不命中） |
| `views/UserList.vue` | **6 → 0** | 新增 `Role` / `RoleForm` / `User` / `UserForm`；`userHasPerm(user: User \| null, …)`（模板传入的 `permUser` 可空，函数体本就按可空写） |
| `views/RoleList.vue` | **4 → 0** | `Role[]` / `RoleForm`；el-checkbox 的 `change` 载荷按**联合类型** `string \| number \| boolean` 声明（本处未设 `true-label`，运行时恒为 boolean） |
| `views/TokenList.vue` | **1 → 0** | `ApiToken`；`new Date(row.expires_at ?? 0)` —— 与原先 `null` 入参的强制转换结果一致 |
| `views/AuditLog.vue` | **2 → 0** | 提为 `auditActions` 计算属性（`auth.meta?.audit_actions` 直接可取，**原 `as any` 是多余的**），两处共用、零断言 |
| `utils/__tests__/colors.spec.ts` | **2 → 0** | 不完整 meta 的构造改为 `Partial` 化类型；`statusLabel` 第 3 参本就可直接传对象（**去掉多余的 `as any`**） |
| `composables/__tests__/useExportJobs.spec.ts` | **1 → 0** | 夹具补齐为完整 `ExportJob` |
| `views/NotifyChannelList.vue` | **6 → 0** | `NotifyChannel`（`config` 显式声明消费到的 `url`/`recipients` + 索引签名放行其余键）；`auth.meta?.notify_channel_types` 去断言；el-switch 载荷按联合类型声明 + `!!value` 归一 |
| `views/AssetList.vue` | **5 → 0** | `useListPage<Asset>`、`editing: Asset \| null`、`UploadRequestOptions`；**删除未被消费的 `meta` ref**（保留 `await auth.fetchMeta()` 的注册表刷新副作用，模板用的是 `urlTagMeta`/`assetStatusMeta`） |
| `views/NonpenPlanList.vue` | **5 → 0** | 新增 `NonpenPlan` / `NonpenPlanForm`；`form` 显式声明为该类型（编辑回显是「空表单 + 行数据」合并，需允许可空字段）；提交体用 `Partial<NonpenPlanForm>` 以支持剔除服务端字段 |
| `views/TestingPlanList.vue` | **5 → 0** | `isTester/canOperate(row: TestingPlan)`、`assetPrefill: Partial<Asset> \| null`、`onAssetCreated(asset: Asset)`；模板回调用结构化标注 |
| `components/NonpenPlanWorkflowDrawer.vue` | **1 → 0** | `plan: NonpenPlan \| null`；`items` 条目补 `first_times`/`retest_times`（步骤条展示所需） |

**本轮 9 处报错处置（两类新发现）**：
1. **`el-table` 的插槽 `row` 恒为 `any`** —— 与 `:data` 的类型无关（Element Plus 的 slot 类型如此声明）。因此「给列表泛型」并不能让插槽内推导出具体类型，模板回调一律用**结构化标注**（`(o: { name: string })`）解决。
2. **`{...空表单, ...行数据}` 再次因「来源可空覆盖目标必填」失败**（`NonpenPlanList`），处置同第 11 批：把表单 ref 显式声明为共享类型，让目标类型容纳可空字段（而非改数据流）。

### E-5 收口（2026-09-18）

| 指标 | 起始 | 现状 |
|---|---|---|
| `vue-tsc --noEmit` | 39 错误（工具未安装） | **0 错误**（13 批全程保持） |
| `any` 命中行数 | **278** | **3** —— ①`stores/auth.ts` 全局 `meta`（异构袋，保留边界）②`types/index.ts` 的 `ReportSection` 索引签名（保留边界）③`views/Dashboard.vue` 的**注释文本**（正则误报，非代码）→ **业务代码 `any` = 0** |
| 前端测试 | 118 | **24 files / 138 passed** |
| 生产构建 | — | 通过 |

**沉淀的三条硬约束（已写入 `AGENTS.md` 口径）**：
1. **新增代码不得引入 `any`**；确属边界（第三方结构、用户输入 JSON）用 `unknown`，或在原处写明理由保留。
2. **类型收敛不得改变运行时数据流** —— 典型是 `{...base, ...detail}` 场景：必须保留 spread（详情接口可能返回未建模字段），只对类型冲突字段做 `?? base.x` 归一。
3. **报错先怀疑"我声明的类型"**：13 批中类型门禁报出的问题**无一是产品缺陷**，全部是声明过窄/过泛/看错调用方传参（含 `form` 对象被当成表格行等）。

**行为等价改写清单（本路线累计，供复核）**：`meta?.dict?.[x.opt ?? 0]`（回退语义不变）×4；`const arr = obj.arr` 再判空以补足收窄；`[...(ids ?? [])]`；`new Date(x ?? 0)`；`!!value`（el-switch 无 `active-value` 时恒为 boolean）；`if (m.group_id == null) continue`（原先写 `undefined` 键永不命中）；`if (!f.raw) continue`（仅 `ready` 态入列必有 raw）；富文本空值 `?? ''` 归一；`ReportEditor` 8 处最小化空值守卫（隐式前提显式化）。

**未做/遗留（需单独决定）**：
- **浏览器端到端冒烟未执行**：本机后端未启动（`http://127.0.0.1:8000` 不可达），故本轮以「类型门禁 + 138 例单测 + 生产构建」为验收；如需对上述等价改写做浏览器复核，请启动后端后告知。
- **F-1（`vul`/`vuln` 命名规范阶段 A/B）** 仍未开始，属独立工作流。
- **已知的隐式 `any` 面（不在本次计数口径内）**：部分列表页仍用未指定泛型的 `useListPage('/xxx')`（`items` 退化为 `any[]`），其表格插槽 `row` 因此无静态约束。这是下一步可选的深化方向（逐页补 `useListPage<T>` 并处理连带模板字段）。

### E-5 第 11 批：导入 / 漏洞域页面（ImportList / VulnDetail / VulnRetest / VulnEdit / VulnList）

| 文件 | `any` | 做法 |
|---|---|---|
| `views/ImportList.vue` | **7 → 0** | `useListPage<ImportBatch>`；上传列表用 Element Plus 自带的 `UploadUserFile` / `UploadFile`（**先确认库已导出**）；`catch (e: any)` → `catch (e)` + `ApiErrorShape` |
| `views/VulnDetail.vue` | **7 → 0** | `Vuln` / `VulnLog`（新增）/ `VulnTransition`（复用）/ `UserBrief`；`Vuln` 补 `submitter_id`/`cvss_vector`/`score`/`fix_time`/`notice_time` |
| `views/VulnRetest.vue` | **2 → 0** | `Vuln` + `RetestRecord`（复用第 7 批类型） |
| `views/VulnEdit.vue` | **1 → 0** | `onSaved(vulns: VulnForm[])` —— 与 `VulnFormPanel` 的 emit 契约**天然对齐**（同一类型，跨两批复用） |
| `views/VulnList.vue` | **1 → 0** | 模板槽位 `row` 为库提供的 `any`，故对回调参数做**结构化标注** `(a: { name: string })`（不打散 el-table 契约） |

**顺带收敛重复（B-3 口径）**：新增 `ApiErrorShape`（`response.data.detail` / `message` / `status`）作为**共享错误结构**，替换了 `api/client.ts` 里上一批刚加的局部 `ToastableError`。

**本轮 6 处报错处置（含一类新问题）**：
1. **`Vuln` 的可选字段覆盖 `VulnForm` 的必填字段**（`vul_type?`/`layer?`/`source?`/`score?`/可空 `cvss_vector`）—— 这是本轮最值得记录的一类：`{...base, ...detail}` 的展开语义下，**来源类型的可空性会覆盖目标类型的必填性**。处置：**保留 spread（详情接口可能返回未建模的 `*_json` 等字段，不能改成逐字段挑拣）**，只对冲突字段做 `?? base.x` 归一 —— 既过类型门禁，又不丢运行时字段。
2. `form.append('file', f.raw)`：`UploadUserFile.raw` 可选 → 增加 `if (!f.raw) continue` 守卫（仅 `ready` 状态入列，本就有 raw）。
3. 模板三处：`meta?.vul_type?.[vul.vul_type ?? 0]`、`meta?.vul_source?.[vul.source ?? 0]`（第 4 次使用同一套路）、`:title="vul.cvss_vector ?? ''"`。
4. `ImportList` 模板槽位行：`(a: { name: string })` 结构化标注。

**验收（里程碑）**：

| 项目 | 结果 |
|---|---|
| `vue-tsc --noEmit` | **0 错误** |
| `any` 命中行数 | **65 → 47**（累计 230 → 47）—— **已低于审计期望值 ≤50**；其中 2 处为文档化保留边界、1 处为注释误报，实际业务代码 `any` ≈ 44 |
| 前端全量测试 | **24 files / 138 tests passed** |
| 生产构建 | 通过 |

### E-5 第 10 批：组件层（VulnDetailDialog / PlanWorkflowDrawer / ImportBatchConfirmDialog / TemplatePickerDialog / RichEditor）

| 文件 | `any` | 做法 |
|---|---|---|
| `components/VulnDetailDialog.vue` | **3 → 0** | `vuln: Vuln \| null`、`meta` 二级字典；`Vuln` 补详情展示所需富文本字段（`description_html`/`reproduce_html`/`solution_html`） |
| `components/PlanWorkflowDrawer.vue` | **3 → 0** | 模板内 `plan.testers` 元素（`UserBrief`）、漏洞选择器 `@selection-change` 与 `:selectable` 均按 `Vuln` 声明（选择器状态本就是 `Vuln[]`） |
| `components/ImportBatchConfirmDialog.vue` | **3 → 0** | `plans: TestingPlan[]`、`assets: Asset[]`、`mismatchItems: ImportLevelMismatch[]`（**复用第 7 批上提的共享契约类型**）+ 三处响应泛型 |
| `components/TemplatePickerDialog.vue` | **2 → 0** | emit 载荷 `entry: KnowledgeTemplate`（复用第 3 批类型）；本地 `meta` 收为二级字典 |
| `components/RichEditor.vue` | **1 → 0** | `update:json` 载荷 `any → unknown`，并注明「当前 10 处消费方均已按 `unknown` 处理」（先核实再改，改完全部消费方零改动） |

**本轮两处报错处置**：
1. `meta?.vul_type?.[vuln.vul_type]`（`vul_type` 可选）→ `[vuln.vul_type ?? 0]`，与「取值失败回退显示原值」的既有语义等价。
2. 编辑态回显改为在**边界显式归一**富文本空值：`description_html: vul.description_html ?? ''`（等 3 个字段）。原因：`Vuln` 的富文本字段可空（服务端对空内容返回 `null`），而 `VulnForm` 契约为 `string` —— 此前靠 `any` 让 `null` 直接进入表单，现于边界归一并加注释说明「空值语义一致」。

**批次范围调整（说明）**：`NonpenPlanWorkflowDrawer`（1 处）**并入后续 NonpenPlan 域批次**与 `NonpenPlanList`（5 处）一起处理 —— 二者共用同一个工单实体类型，拆两批反而要建模两次。

**验收**：

| 项目 | 结果 |
|---|---|
| `vue-tsc --noEmit` | **0 错误** |
| `any` 命中行数 | **77 → 65**（累计 230 → 65，**-72%**；其中 2 处为文档化保留边界 + 1 处注释误报） |
| 前端全量测试 | **24 files / 138 tests passed** |
| 生产构建 | 通过 |

### E-5 第 9 批：共享层收口（usePlanAssetLink / useDictOptions / usePlanFilters / client / auth / main）

| 文件 | `any` | 做法 |
|---|---|---|
| `composables/usePlanAssetLink.ts` | **3 → 0** | **泛型化**：`usePlanAssetLink<P extends PlanLinkSource, A extends AssetLinkSource>`，新增两个「联动所需最小子集」输入契约；`filteredAssets` 的返回元素类型与调用方传入的资产列表**保持一致**（否则调用点会丢失 `Asset` 的 `sub_system`/`system_type`，`assetLabel(a)` 立刻报错） |
| `composables/useDictOptions.ts` | **2 → 0** | `/dict/test_type` → `{ name: string }[]`；`/groups` → `Group[]` |
| `composables/usePlanFilters.ts` | **2 → 0** | localStorage 历史规则按**不可信来源**处理：`JSON.parse` 结果收为 `unknown` + `isStoredRule()` 类型守卫（字段名走后端白名单、操作符校验为字符串）；`value` 的形态由 `FilterBuilder` 写入、非法值由既有 `isRuleComplete` 在使用处兜底，故保留一处**带注释的断言**而非改写行为 |
| `api/client.ts` | **1 → 0** | `toastError(error: any)` → `ToastableError`（只声明实际消费的 `response.data.detail` 与 `message`，即「按需结构化」而非照抄 axios 全量类型） |
| `main.ts` | **1 → 0** | `app.component(name, comp as any)` → `comp as Component`（Vue 自带类型） |
| `stores/auth.ts` | **保留 1 处** | 全局 `meta` 是**异构袋**（「码→名称」映射 + 纯字符串列表 + 嵌套色值表），逐键建模收益极低而维护成本高 → 作为**保留的宽类型边界**，补 8 行理由注释；调用方按自身用到的键局部收窄（如各组件 `Record<string, Record<number, string>>`） |

**本轮报错处置**：`plan.asset_ids?.length` 的**可选链不足以让 TS 收窄可空数组**，`plan.asset_ids[0]` 报「possibly null」。改为先取局部变量 `const ids = plan.asset_ids` 再判 `ids?.length` —— 行为不变，仅补足收窄。

**验收**：

| 项目 | 结果 |
|---|---|
| `vue-tsc --noEmit` | **0 错误** |
| `any` 命中行数 | **86 → 77**（累计 230 → 77，**-67%**；其中 1 处为文档化的保留边界） |
| 前端全量测试 | **24 files / 138 tests passed** |
| 生产构建 | 通过 |

### E-5 第 8 批：共享模块优先 —— useAssetSelect / SpringActionList（2026-09-18）

**为什么先做 composable**：`useAssetSelect` 被 `VulnFormPanel`、`RemoteTestingList`、`TestingPlanList`、`AssetFormDialog` 等**多个页面**引用。收窄它的 `assetCache` / `assetLabel` / `cacheAsset` 签名（`any` → `Asset`），一次改动即可让所有调用方的传参自动变严。

| 文件 | `any` | 做法 |
|---|---|---|
| `composables/useAssetSelect.ts` | **7 → 0** | `assetCache: Record<number, Asset>`、`assetLabel(a: Asset)`、`cacheAsset(a: Asset)`；响应 `Items<Asset>` / `Asset` |
| `views/SpringActionList.vue` | **8 → 0** | 新增 `SpringAction` / `SpringActionForm`；上传回调用 `UploadRequestOptions`；`(body as any).new_vuls` 改为 `SpringActionForm & { new_vuls?: VulnDraft[] }`（把「运行时多出的服务端字段」写进类型，替代 `delete (body as any).vuls` 的绕过） |

**共享模块策略当场兑现收益**：收窄签名后一次性暴露出 **4 处上游问题**（分属 `TestingPlanList` 与 `useAssetSelect` 自身用例）：
1. `assetUrls(asset)`（`utils/urls.ts`）拒绝 `Asset` —— 根因是 `UrlLike` 含**索引签名**（`string | { url?: string; [key: string]: unknown }`，其存在是为了「附加字段不参与归一化」），而无索引签名的类型不能赋给它。**处置**：给 `AssetPublicUrl` 加索引签名以与既有设计对齐 —— 这不是放水，而是补上「后端可扩展额外字段」这一真实契约（已在类型注释写明理由）。
2. `SpringActionList` 两处：`downloadReport(form)` 传的是**表单对象**（同第 6 批 `RemoteTestingList` 的同类问题）；`[...form.value.vul_ids]` 在 `vul_ids` 可选时报迭代错误 → 改 `?? []`（行为等价）。
3. `useAssetSelect.spec.ts` 夹具需补齐为完整 `Asset`；`cacheAsset(null)` 这一「运行时兜底」用例保留，以带注释的断言表达（验证守卫本身是有效测试）。

**验收**：

| 项目 | 结果 |
|---|---|
| `vue-tsc --noEmit` | **0 错误** |
| `any` 命中行数 | **101 → 86**（累计 230 → 86，**-63%**） |
| 前端全量测试 | **24 files / 138 tests passed** |
| 生产构建 | 通过 |

### E-5 第 7 批：ImportPreview / VulnRetestPanel（+ 弹窗顺带收敛，2026-09-18）

| 文件 | `any` | 做法 |
|---|---|---|
| `views/ImportPreview.vue` | **9 → 0** | 新增 `ImportBatch` / `ImportRecord` / `ImportLevelMismatch`；`/imports/{id}` 的 `{batch, records}` 响应类型；资产/报告/工单下拉用 `Items<T>` |
| `components/VulnRetestPanel.vue` | **9 → 0** | 新增 `RetestRecord`（含 `username`/`create_time`）；`Vuln` 补 `retest_html?`（复测记录为空时的回退展示） |
| `components/ImportLevelMismatchDialog.vue` | **1 → 0**（顺带） | `items: any[]` → `ImportLevelMismatch[]` —— 该类型由**使用方**（导入预览）与弹窗**共享**，故上提到 `src/types` 而非各自声明 |

**本轮两处「类型写错方向」的实证**：
1. `ImportBatch.meta_json` 我第一版写成 `string`（JSON 文本），但模板是 `batch.meta_json?.system_name` —— 后端 JSON 列在响应里**已经是对象**。改为结构化声明（`{ system_name?, report_date?, is_retest? }`）后即通过。
2. `RetestRecord.title` 可选，而 `if ((r.title || '').trim()) return r.title.trim()` 的守卫无法收窄 `r.title`；改为先取 `const custom = (r.title || '').trim()` 再判断 —— **行为完全等价**。

**验收**：

| 项目 | 结果 |
|---|---|
| `vue-tsc --noEmit` | **0 错误** |
| `any` 命中行数 | **120 → 101**（累计 230 → 101，**-56%**） |
| 前端全量测试 | **24 files / 138 tests passed**（`VulnRetestPanel` 有用例覆盖） |
| 生产构建 | 通过 |

### E-5 第 6 批：KnowledgeList / RemoteTestingList（2026-09-18）

| 文件 | `any` | 做法 |
|---|---|---|
| `views/KnowledgeList.vue` | **10 → 0** | 新增 `KnowledgeEntry` / `KnowledgeForm`；`client.get<KnowledgeEntry[]>`、批量删除/导入的响应类型；导入的 JSON 用 `unknown` + `Array.isArray` 收窄（用户提供的数据无法静态保证结构） |
| `views/RemoteTestingList.vue` | **9 → 0** | 新增 `RemoteTesting` / `RemoteTestingForm` / `VulnDraft`；`useListPage<RemoteTesting>`；文件上传回调改用 Element Plus 自带的 `UploadRequestOptions`（库已导出，避免自造结构） |

**本轮 5 处报错的处置（全部为「声明贴近真实用途」）**：
1. `KnowledgeEntry.cvss_vector` 由可选改必填 —— 该字段是表单必填项、列表行也总有值（`scoreFromVector(form.cvss_vector)` 要求 `string`）。
2. `VulnDraft` 增 `id?: number` —— 草稿未落库时无 id，模板正是据此决定是否显示「查看详情」入口。
3. 模板 `meta?.vul_type?.[linkedVuln.vul_type]` → `[linkedVuln.vul_type ?? 0]`：`Vuln.vul_type` 可选，`?? 0` 后索引与「取值失败则回退显示原值」的既有语义**完全等价**。
4. `downloadAppeal` 参数由 `RemoteTesting` 改为 `RemoteTestingForm` —— 模板在第 199 行传的是**表单对象**（`form`），不是表格行。

**验收**：

| 项目 | 结果 |
|---|---|
| `vue-tsc --noEmit` | **0 错误** |
| `any` 命中行数 | **137 → 120**（累计 230 → 120，**-48%**） |
| 前端全量测试 | **24 files / 138 tests passed** |
| 生产构建 | 通过 |

### E-5 第 5 批：VulnList / ReportEditor（2026-09-18）

| 文件 | `any` | 做法 |
|---|---|---|
| `views/VulnList.vue` | **13 → 0** | 新增 `VulnStats`（含透视表 `VulnPivotRow`/`VulnPivotTotals`/`VulnPivotLevelCell`）；`Vuln` 补列表行字段（`assets`/`department`/`source`）；`useListPage<Vuln>`、`QueryParams`；透视表 `span-method` / `summary-method` 的入参按 el-table 实际传参声明 |
| `views/ReportEditor.vue` | **10 → 0** | 新增 `ReportDetail`（`Report` + 章节与基础信息）、`VulnState`；`ExportJob`/`VulnState` 泛型化；`catch (e: any)` → `catch (e)` + `(e as { response?: { status?: number } })` |

**本轮类型门禁抓到了真正的价值（不是噪音）**：把 `report` 从 `any` 收窄为 `ReportDetail | null` 后，**立刻暴露出 8 处「隐式假定 report 已加载」的写入点**（`testRange` setter、`onDrop`、`onAuthorChange`、`removeSection`、`move`、`doExport`、`download`），以及 2 处 `VulnState.status` 未声明必填。

处置原则（**不动业务语义**）：
- 前 8 处按「用户操作必然发生在页面加载后」的实际前提补**最小化前置守卫**（`if (!report.value) return`，或在既有条件里追加 `&& report.value` 以保持 `onDragEnd()` 仍会执行）—— 正常路径行为完全不变，只是把原来的隐式前提变成显式；
- `VulnState.status` 改为必填（后端对每个关联漏洞必返状态，章节导航标签正是据此着色），`level` 保持可空（章节表单在 `level != null` 时禁用下拉，说明确实可能为空）。

**验收**：

| 项目 | 结果 |
|---|---|
| `vue-tsc --noEmit` | **0 错误** |
| `any` 命中行数 | **159 → 137**（累计 230 → 137，-40%） |
| 前端全量测试 | **24 files / 138 tests passed** |
| 生产构建 | **✓ built in 15.14s**，`dist/assets` 61 文件 |

> **口径备注**：统计脚本为「含 `any` 的行数」。另有 `Record<number, any>` 这类**旧口径未覆盖**的写法（本轮顺带清理了 2 处），故实际收敛幅度略大于表内数字。

### E-5 第 4 批：AssetFormDialog / ReportList（2026-09-18）

| 文件 | `any` | 做法 |
|---|---|---|
| `components/AssetFormDialog.vue` | **15 → 0** | 新增 `AssetForm`（依 `emptyForm()` 建模）+ 嵌套条目类型 `AssetPublicUrl`/`AssetPortService`/`AssetNamedVersion`/`AssetOwner` + `Group`/`GroupMember`；`Asset` 同步复用这些条目类型（消除两处重复声明） |
| `views/ReportList.vue` | **15 → 0** | `useListPage<Report>`、`Report`/`Vuln`/`TestingPlan`/`ExportJob` 泛型化；新增 `BatchExportResult`（`POST /reports/batch-export`） |

**本轮发现的两个「类型必须贴近真实用途」的点**：
1. `AssetFormDialog` 的 `meta`（`/meta` 载荷）是**异构字典袋** —— 既有「码 → 名称」映射（`url_tag`、`asset_status`），也有纯字符串列表（`system_type`）。原先 `ref<any>` 掩盖了这一点；本轮按「本组件用到的三个键」局部声明，**不冒充整个契约**（共享的全局 meta 类型仍留给 C-2 的 store 类型收口）。
2. `AssetFormDialog` 的 `asset` prop 是**预填**语义（新建场景只传 `name`、无 `id`），故声明为 `Partial<Asset>` 而不是 `Asset` —— 我第一版写成 `Asset`，`vue-tsc` 立刻在调用方（`VulnFormPanel`）报出 `{ name: string } | null` 不可赋值。**这条又是一次「先怀疑我声明的类型，再动业务代码」的实证。**

**验收**：

| 项目 | 结果 |
|---|---|
| `vue-tsc --noEmit` | **0 错误** |
| `any` 命中行数 | **189 → 159**（累计 230 → 159，-31%） |
| 前端全量测试 | **24 files / 138 tests passed** |
| 生产构建 | 通过 |

## 端到端验收记录（2026-09-17，真实环境）

**环境**：WSL-Kali 内 `docker compose`（`talos-api-1` / `talos-worker-1` / `talos-frontend-1` / `postgres` / `redis` / `gotenberg` 全部 Up），端口 `27012`（frontend → nginx → api）；账号 `admin1/123456`。
**前置**：由用户完成 api / worker / frontend 镜像重建 —— 三个服务均为**构建镜像（源码不打卷）**，前端或后端源码改动必须重新构建才生效。

**① 接口级冒烟（临时脚本 `backend/_e2e_smoke.py`，已验证后删除）**：16 项 **15 通过**；唯一失败项是脚本把字典端点误写为 `/auth/meta`，真实端点为 `GET /meta`（`stores/auth.ts:40`）→ 补测确认 `/meta` 返回 200，**非产品缺陷**。通过项覆盖：登录、`/dict/test_type`、`/testing-plans`（默认排序 / 聚合筛选 / 时间区间三种参数形态）、`/testing-plans/stats`、`/conclusion`、`/conclusion/export`、`/export`、`/import/template`（三者均返回 `openxmlformats…spreadsheetml.sheet` 真实 xlsx，7 996 / 13 361 / 5 321 字节）、`/testing-plans/76`、`/vuln-order`、`/vulns?testing_plan_id=76`、`/vulns?size=100`、`/assets`。

**② 补测（临时脚本 `backend/_e2e_smoke2.py`，已验证后删除）**：`/meta` 200 ✓；自动挑选「有报告」的工单（planId=75）覆盖抽屉报告链路。
> 环境提示：该环境**单请求耗时约 21 秒**，故脚本改为「逐条即时落盘 + 后台运行」，任何端点卡滞都能立刻定位 —— 这也是本轮前期几次「命令看起来卡死」的真实原因（另：`sudo` 会等待密码输入，脚本类命令一律避开 `sudo`）。

**③ 浏览器级验收（Chrome DevTools MCP，真实页面 `127.0.0.1:27012/testing-plans`，已登录态）**：
- **控制台错误/警告 0 条**；
- 网络实测（全部 200，且正是本次重构的代码路径）：`/testing-plans?search=&page=1&size=20&sort=receive_time&order=desc`、`/testing-plans/stats?search=&sort=receive_time&order=desc`、`/testing-plans/conclusion?…`（三者共用 `filterParams()` 单一口径）；输入关键词「安全」后**三接口同步重发** → 筛选联动正常；`/testing-plans/9`、`/vulns?testing_plan_id=9&size=100&sort=level&order=asc`、`/testing-plans/9/vuln-order`（抽屉 `refresh`）；`/reports/1|123|124/exports`（`useReportExports` 导出历史预取）；
- DOM 断言：列表 **3 行**（筛选结果）、结论面板渲染出真实结论文本（「…共发现 2 个系统存在 27 个漏洞…」）、快捷筛选面板存在；重新点击行内「流程」按钮打开抽屉后：**6 步步骤条全部渲染**、**漏洞表 20 行**、「认领」「生成报告」「导出历史」「无漏洞」入口齐备。

**结论**：E-1/E-2 的全部重构路径在真实浏览器 + 真实数据下工作正常，无 JS 报错、无接口 4xx/5xx。

**局限（如实记录，避免过度解读该验收）**：① echarts 月度图在 vitest 中被打桩，图表渲染回归不在自动化覆盖内；本次亦未在浏览器展开统计面板做确认，仅验证了统计接口 200 与面板可展开；② **未执行任何写操作**（认领 / 生成报告 / 漏洞流转 / 导入 / 删除）以免污染共享数据，写路径由后端 168 例与前端桩测试覆盖；③ 环境单请求约 21 秒，属性能异常，建议单独排查（不在本次改动范围内）。

**理由**：低风险 D-2 无回归风险、可先建立「拆分 + 补测」的节奏；前端拆分与类型收敛同时做可避免同一文件改两遍；F-1 阶段 B 涉及数据/迁移路径，必须独占窗口并预留回滚演练。

---

## 开发环境对齐：uv + Python 3.12（2026-09-17 完成）

**问题**：本地 `backend/.venv` 为 Python **3.10.11**（`pyvenv.cfg` → `python310`），而容器/生产为 `python:3.12-slim`（`backend/Dockerfile`）——存在「本地与容器行为不一致」的隐性风险窗口，且本地无法写出/验证 3.12 语法与 API。

**处置（uv 0.11.21，环境由 uv 管理）**：

| 步骤 | 命令/结果 |
|---|---|
| 候选环境（不破坏现状） | `uv venv backend/.venv312 --python 3.12` → 复用 uv 已托管的 CPython **3.12.11**（无需下载） |
| 安装依赖 | `uv pip install --python … -r requirements-dev.txt`（全量） |
| 候选环境验收 | ruff 全绿 + 后端 **168 passed / 1 skipped**，与 3.10 环境结果一致 → 证明版本升级无回归 |
| 切换 | `Move-Item .venv .venv.old310` + `Move-Item .venv312 .venv`（**重命名而非删除**，保留回退路径） |
| 正式路径复验 | `.venv` = Python 3.12.11（fastapi 0.141.1 / sqlalchemy 2.0.54 / pydantic 2.13.5）：ruff 全绿 + **168 passed / 1 skipped** |
| 配置同步 | `ruff.toml` `target-version = "py312"`；`.gitignore` 增加 `.venv.*/`（覆盖切换备份目录）；`dev.ps1` / `dev.sh` 改为**优先用 uv 创建 3.12 venv**（无 uv 时回退 `python -m venv`，并提示版本要求），preflight 检查同步放宽为「uv 或 python/python3 二者其一」；`AGENTS.md` 常用命令与规范更新 |
| 脚本语法校验 | `dev.ps1` PowerShell AST 解析通过；`dev.sh` `bash -n` 通过 |

**遗留（需人工执行）**：旧环境备份目录 `backend/.venv.old310` 仍在磁盘（已被 `.gitignore` 覆盖，不影响 git 状态）。自动删除被**安全守卫拦截**（该目录含 7167 个文件，超过单轮批量删除阈值 500，需交互确认）。确认新环境可用后请自行清理：
```powershell
Remove-Item -Recurse -Force e:\GitRepo\Talos\backend\.venv.old310
```
**注意**：`requirements*.txt` 使用 `>=` 未锁版本，本次升级把 fastapi/sqlalchemy/pydantic 等推到较新版本且测试全绿；建议后续引入 `uv pip compile requirements.txt -o requirements.lock` 锁定可复现版本（未在本轮执行，属新增可选项）。
