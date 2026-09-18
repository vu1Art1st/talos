# Talos 代码库质量审计报告

> 审计日期：2026-09-17 · 审计对象：`main`（工作区干净，HEAD = v2.17.1 之后未发布状态）
> 所有问题条目均给出 `文件:行号` 与实测证据，可逐条复核；未使用推测性结论。
> 脚本目录专项审计见 [`SCRIPTS.md`](./SCRIPTS.md)。

---

## 一、审计范围

| 范围 | 路径 | 规模（实测） |
|---|---|---|
| 后端应用 | `backend/app/` | 74 个 `.py`，13 739 行 |
| 后端脚本 | `backend/scripts/` | 11 个 `.py`，1 560 行（修复后为 10 个 / 1 336 行，见 `AUDIT_FIX_LOG.md` 批 6） |
| 后端迁移 | `backend/alembic/` | 1 437 行 |
| 后端测试 | `backend/tests/` | 5 772 行（合计 backend 120 个 `.py`，22 508 行） |
| 前端 | `frontend/src/` | 44 个 `.vue` + 48 个 `.ts`，合计 14 410 行 |
| 部署脚本 | `scripts/` | 11 个 `.sh`，908 行 |

**不在本次范围**：`docs/` 文案、`design-demos/`（本地设计稿，不入库）、依赖本身、容器运行时配置。

## 二、检查标准

审计前先固化阈值，避免「凭感觉」判定：

| 维度 | 判定标准（阈值即定义） |
|---|---|
| 无用代码·死代码 | 定义为：符号名（函数/方法）在全仓库 `.py` 中出现次数 ≤ 1（即只有定义处）；排除框架入口装饰器（`@router.*`、`@app.exception_handler`、`@pytest.fixture`、`@property` 等）、dunder、`test_*`、`visit_*` |
| 无用代码·未使用 import | AST 收集 `Import`/`ImportFrom` 绑定名，该名字在**本文件**正文中出现次数 ≤ 1 |
| 可读性·长行 | 单行 > 120 字符（PEP 8 建议 79/99；本项目既有代码普遍 100+，故取 120 作为「明确受损」阈值） |
| 可读性·超长函数 | 函数体 > 60 行 |
| 可读性·深嵌套 | 控制流嵌套 ≥ 5 层（**已排除 `elif` 链**，见 §5-D-3 校正说明） |
| 重复实现·结构克隆 | 函数体 AST 归一化（`Name`/`arg` 归一为 `N`、`Constant` 归一为类型名、内层函数名归一为 `F`）后完全相同，且函数体 ≥ 8 行 |
| 重复实现·复制粘贴 | 连续 8 行去除注释与空白后完全相同，且出现在 ≥ 2 个文件 |
| 过度防御 | `except Exception/BaseException` 且分支体仅为 `pass` / `return None` / `return` / `continue`（无日志、无注释说明） |
| 命名规范 | Python 函数名匹配 `_?[a-z][a-z0-9_]*`；前端标识符不得使用 snake_case；同一语义族的操作应使用同一命名前缀 |

**工具链现状（重要）**：项目 venv 内 `vulture` / `radon` / `ruff` / `flake8` / `pyflakes` / `pylint` / `mypy` **均未安装**（实测 `find_spec` 全部返回 `NO`）。本次数据由临时 AST/文本分析脚本采集，脚本已删除；复核可复用上表规则，或用下列等价命令：

```bash
# 长行（后端 / 前端）
rg -n '^.{121,}$' backend/app frontend/src
# 未使用 import（安装 pyflakes 后，可直接取代启发式规则）
python -m pyflakes backend/app backend/scripts backend/tests
# 指定输出行号与文件，便于与下表核对
rg -n 'except (Exception|BaseException)' backend/app
```

## 三、严重程度分级

| 级别 | 含义 | 处理要求 |
|---|---|---|
| **P0 阻断** | 功能必然失败，或存在数据错误风险 | 当次迭代必修 |
| **P1 高** | 影响正确性（口径分叉）或显著拖累可维护性（超长文件/函数、核心逻辑重复） | 近期排期 |
| **P2 中** | 可读性、可扩展性、类型安全受损，但无即时故障 | 顺手治理 |
| **P3 低** | 清理类（未使用 import、命名细节） | 随改动顺带 |

## 四、结论摘要

| 类别 | 实测结果 | 判定 |
|---|---|---|
| 死代码 | **0 处**（初判 2 处经复核为 `@app.exception_handler` 注册的处理器，误报） | 健康 |
| 未使用 import | 105 条告警 → 92 条为 `app/schemas/__init__.py` 的**按设计重导出**、1 条带 `# noqa: F401` 注释、**真实 12 条** | P3 |
| 长行 >120 字符 | 后端 22 行（`app/` 仅 4 行，迁移文件 13 行）；前端 110 行 | P2 |
| 超长函数 >60 行 | `app/` 内 **19 个**（最长 `db._migrate_lightweight` 340 行） | P1/P2 |
| 真实深嵌套 ≥5 层 | 4 个函数（最多 6 层） | P2 |
| 结构克隆组 | 4 组（2~3 个函数互为克隆） | P2 |
| 跨文件复制块 | 130 块，其中 1 处为 **约 110 行的高价值重复** | **P0** |
| 过度防御（静默吞异常） | 10 处；`except Exception` 共 27 处，其中 21 处为已注释的降级设计 | 整体健康，个别 P2 |
| 前端类型逃逸 | `any` 共 201 处 / 35 文件 | P2 |
| 命名规范 | 后端函数名 snake_case 偏离 **0 处**；问题集中在术语与前端命名族 | P1/P2 |
| 运行安全 | 1 处（`seed_dev_data.py` 缺目标库守卫） | P1 |

---

## 五、问题清单（可执行）

### A. 无用代码

**A-1（P3）12 处真实未使用 import**

| 位置 | 未使用符号 |
|---|---|
| `backend/alembic/versions/f7a8b9c0d1e2_migrate_completed_to_final.py:12` | `sqlalchemy as sa`（该文件仅使用 `op.execute`） |
| `backend/app/api/v1/imports.py:17` | `ExportJob`、`Report` |
| `backend/app/api/v1/nonpen.py:8` | `HTTPException` |
| `backend/app/api/v1/notify.py:2` | `HTTPException` |
| `backend/app/api/v1/open_api.py:13` | `parse_str_list` |
| `backend/app/api/v1/vulns.py:449` | `literal_column`（函数内局部 import，全文仅此 1 次） |
| `backend/app/services/nonpen_service.py:5` | `AsyncSession` |
| `backend/app/services/plan_service.py:10` | `Report`（该行同时导入的 `ReportSection` 在用） |
| `backend/scripts/seed_dev_data.py:36` | `now as tznow`（实测全文 `tznow` 仅出现 1 次 = 导入行） |
| `backend/scripts/seed_dev_data.py:39` | `ExportJob`、`GroupUser` |

> 复核命令：`rg -n 'literal_column|tznow' backend/app/api/v1/vulns.py backend/scripts/seed_dev_data.py`（各仅命中导入行）。
> **状态：已于 2026-09-17 批次 6 全部清理**（12 条全部移除）。

**A-2（P1）`backend/scripts/migrate_from_insight2.py` 已失效，必然抛 `ImportError`**

实测证据（2026-09-17，项目 venv）：

```
App exists: False
Asset.value: False Asset.asset_type: False Asset.is_open: False Asset.is_https: False
Vul.app_id: False
```

该脚本第 31 行 `from app.models import App, Asset, Group, Role, User, Vul, VulLog`，而 `App` 模型已按 `backend/app/models/business.py:20` 的注释「资产（系统级，合并原 App 应用与旧域名/IP 资产）」合并进 `Asset`；其第 121-127 行写入的 `Asset(value=…, asset_type=…, is_open=…, is_https=…)` 与第 150 行 `Vul(app_id=…)` 字段均已不存在。**结论：脚本语法可编译，运行时第一步 import 即失败。**
> **状态：已于 2026-09-17 批次 6 删除**，`README.md` / `README_EN.md` 的「旧数据迁移」章节已同步改写为重写指引。

**A-3（无问题）孤儿模块误报说明**

初判 `backend/app/models/dictionary.py`、`backend/app/schemas/import_.py` 无人引用，复核为误报：二者分别以全限定路径 `from app.models.dictionary import …`（`models/__init__.py:14`）与相对导入 `from . import_ import …`（`schemas/__init__.py:62`）被引用。

**A-4（P1）`backend/scripts/seed_dev_data.py` 缺目标库守卫，可能清空非开发库**

- 位置：`backend/scripts/seed_dev_data.py:26` 与 `:244-248`。
- 事实：脚本用 `os.environ.setdefault("VP_DATABASE_URL", "sqlite+aiosqlite:///./dev.db")` 注入默认 DSN —— `setdefault` **只在变量缺失时生效**；随后 `reset_and_seed()` 会对 `ALL_TABLES`（`:48-56`，共 26 张业务表）逐表执行 `DELETE FROM`。脚本全文检索无任何 `sqlite` 分支判断或库名断言（仅第 26 行的 DSN 默认值）。
- 影响：若执行环境中已导出指向测试/生产 PostgreSQL 的 `VP_DATABASE_URL`，脚本会清空该库并写入演示数据；现有的保护只有 `--reset` 参数（`:557-559`），它防的是「误跑」，防不了「跑错库」。
- 建议：在执行前断言 DSN 为 sqlite 或库名等于 `dev.db`，否则 `sys.exit(1)` 并打印当前 DSN；同时把 `DELETE` 循环改为显式打印将清空的库与表数量，需二次确认。

---

### B. 重复实现且未统一抽象

**B-1（P0）导出元数据构建逻辑双份实现，且口径已分叉**

- 位置：`backend/app/services/import_service.py:432-578`（`auto_export_report`）与 `backend/app/workers/main.py:95-210`（`export_report_task`）。
- 证据：8 行滑动窗口完全相同且跨文件命中 50+ 处（如 `import_service.py:478-491` ≡ `workers/main.py:135-150`、`import_service.py:526-530` ≡ `workers/main.py:178-182`、`import_service.py:544-547` ≡ `workers/main.py:198-202`），覆盖 `meta` 组装、`report_records` 版本记录、`sections`、`vulns`、`assets` 聚合全流程，合计约 110 行。
- **分叉已发生**：`import_service.py:499-501` 在「当前报告」分支为 `last_done.get(pr.id) or (pr.create_time … ) or export_date_str`，而 `workers/main.py:156` 只有 `last_done.get(pr.id) or export_date_str`。同一份报告在「导入自动导出」与「手动导出」两条路径下，版本变更记录的日期可能不一致。
- 建议：新建 `backend/app/services/report_meta.py`，抽出 `build_export_meta(session, report, plan, operator)`、`collect_plan_reports(session, plan)`、`build_sections(report)`、`build_vulns(session, sections)`、`build_assets(rows)`，两处调用同一实现；抽完后 `auto_export_report` 与 `export_report_task` 应各自降到 30 行内。
- 验收：`rg -n 'report_records' backend/app/services backend/app/workers` 只剩 1 处赋值实现；补充一条断言两种入口产出 meta 完全相等的测试。

**B-2（P1）复测判定口径 4 处内联，绕过既有函数**

- 既有唯一实现：`backend/app/services/plan_service.py:74` `is_retest_report_title(title)`，已在 `backend/app/api/v1/reports.py:115,130` 使用。
- 却另有 4 处内联重复（注释里还写明了「口径与 plan_service.is_retest_report_title 一致」）：
  - `backend/app/workers/main.py:106`、`workers/main.py:172`
  - `backend/app/services/import_service.py:452`、`import_service.py:516`
- 建议：统一改为调用 `is_retest_report_title`；该函数若需供 workers 使用，从 `plan_service` 导入即可（workers 已导入 `app.services`）。

**B-3（P2）删除类路由结构克隆 ×3**

- `backend/app/api/v1/imports.py:347` `delete_batch`、`backend/app/api/v1/knowledge.py:392` `delete_entry`、`backend/app/api/v1/users.py:251` `delete_group` 的函数体经 AST 归一化后完全相同（体长约 10 行）。
- 建议：在 `backend/app/core/query.py` 增加 `delete_by_id_or_404(session, Model, obj_id)`（该模块已是分页/取值的统一出口，符合 AGENTS.md 约定），三处改为调用。

**B-4（P2）权限依赖克隆 ×2**

- `backend/app/core/deps.py:84` `require_perm` 与 `:96` `require_pat_perm` 结构克隆（体长约 10 行）。
- 建议：改为工厂函数 `_perm_dep(code, *, pat: bool)`，或抽出公共 `_check_perms(user, codes)` 供两者调用。

**B-5（P2）工单 ID 派生属性克隆 ×2**

- `backend/app/models/special.py:136`（`TestingPlan.ticket_id`）与 `:203`（`NonpenPlan.ticket_id`）结构克隆。
- 该口径还与 `backend/app/services/plan_query.py` 的两处筛选表达式同源（见 MEMORY「工单ID 口径三处表达式须一致」）。
- 建议：抽 `backend/app/core/ticket_id.py::derive_ticket_id(manual, receive_time, seq)`，模型 property 与 `plan_query` 共同引用，使「同口径」由代码保证而非注释约束。

**B-6（P2）字典映射函数克隆 ×2**

- `backend/app/services/docx_parser.py:100` `_map_level` 与 `:110` `_map_type` 结构克隆。
- 建议：抽 `_map_code(text: str, mapping: dict, default: int) -> int`。

**B-7（P2）前端测试 mock 样板复制 ×4**

- `frontend/src/components/__tests__/VulnRetestPanel.spec.ts:5-7`、`frontend/src/views/__tests__/RemoteTestingList.spec.ts:5-7`、`frontend/src/views/__tests__/ReportEditor.spec.ts:28-31`、`frontend/src/views/__tests__/VulnList.spec.ts:17-20` 四份 `vi.mock('../../api/client', …)` + `getMock` 样板逐行相同。
- 建议：抽 `frontend/src/__tests__/helpers/mockClient.ts` 导出 `mockClient()`，四个 spec 改为单行调用（与 MEMORY 记载的「视图冒烟需 mock store/client」口径一致，避免下次接口调整要改 4 处）。

**B-8（P2）远程检测 / 春耕行动上传解析流程重复**

- `backend/app/api/v1/remote_testing.py:2-7` 与 `backend/app/api/v1/spring_action.py:2-7` 导入头完全相同；两者「上传 → `PK\x03\x04` 魔术字节校验 → 落盘 → `parse_any_docx` → 失败清理」流程同构（对照 `spring_action.py:78-105`）。
- 建议：抽 `backend/app/services/upload_parse.py::save_and_parse_docx(upload, subdir, filename)`，返回 `(rel_path, doc_kind, meta, records)`。

**B-9（P3）列表查询参数样板分散 ×6+**

- 同一组 `search/sort/order/page/size/…` 形参在 `backend/app/api/v1/testing_plan.py:37,85,109,138,162`、`backend/app/api/v1/open_plans.py:57`、`backend/app/services/plan_query.py:83` 重复出现（复制块命中 7 处）。
- 建议：定义 Pydantic 依赖模型 `PlanListQuery`，路由改为 `q: PlanListQuery = Depends()`；`plan_query.plan_conditions` 接收该对象。

---

### C. 过度防御代码

**C-1（P2）静默吞异常 10 处（除注明外均无日志）**

| 位置 | 处置建议 |
|---|---|
| `backend/app/services/report_builder.py:257`、`:262` | 词法分析器降级（有 docstring 说明，属合理降级）→ 补 `logger.debug` 保留线索 |
| `backend/app/api/v1/remote_testing.py:166`、`backend/app/api/v1/spring_action.py:172` | `except OSError: pass` 清理临时文件失败静默 → 补 `logger.warning` |
| `backend/app/core/security.py:42`、`:48` | JWT 解析失败返回 `None` → 合理（失败即未认证） |
| `backend/app/core/timeutil.py:45` | 时间解析失败返回 `None` → 合理 |
| `backend/app/services/docx_parser.py:38` | `KeyError` 返回 `None` → 合理 |
| `backend/scripts/migrate_from_insight2.py:38` | 随 A-2 一并处置 |
| `backend/scripts/migrate_utc_to_utc8.py:44` | JSON 列无 `python_type` 跳过 → 合理 |

**C-2（P2）前端伪造成功响应掩盖故障**

- `frontend/src/views/ReportList.vue:320`、`:333` 两处：

  ```ts
  const { data } = await client.get('/testing-plans', { params: { size: 100 } }).catch(() => ({ data: { items: [] } }))
  ```

- 影响：接口 5xx / 权限失败时页面静默显示「无工单可关联」，用户无法区分「确实没有」与「请求失败」，且绕过了 `client.ts` 的统一错误提示与错误页策略。
- 建议：改为 `try/catch` + `ElMessage` 提示并保留空态；若确需容错，至少 `console.warn` 并设置独立的 `loadFailed` 标志驱动 `el-empty` 文案。
- 同类面：前端 `.catch(` 共 48 处 / 25 个文件（`VulnFormPanel.vue` 5、`ReportList.vue` 4、`TestingPlanList.vue` 3、`PlanWorkflowDrawer.vue` 3、`main.ts` 3），建议统一「静默 vs 提示」的判定规则。

**C-3（P3）后端异常归一化丢失真实原因**

- `backend/app/api/v1/spring_action.py:91`、`backend/app/api/v1/testing_plan.py:206`、`backend/app/api/v1/assets.py:235` 用 `except Exception` 把一切异常统一转成 `HTTPException(400, "…解析失败…")`。服务端自身 bug（如 `AttributeError`）会被伪装成「用户文件有问题」，排障困难。
- 建议：收敛为 `except (zipfile.BadZipFile, ValueError)` 等可预期异常；兜底分支记 `logger.exception` 并在文案中区分「文件不可解析」与「服务器处理失败」。

**C-4（无问题）整体防御密度合理**

- `except Exception` 共 27 处，其中 21 处带明确注释（如 `backend/app/db.py:170` 「SQLite < 3.35 不支持 DROP COLUMN，忽略残留列」、`backend/app/services/audit_service.py:68` 「审计失败不阻断业务」），属刻意的降级设计，**不建议移除**。
- 未发现「整个函数体包一层 try 后静默返回默认值」这类典型过度防御。

---

### D. 可读性：长行、超长函数、深嵌套

**D-1（P2）长行分布**

- 后端 22 行 >120 字符：`alembic/versions/*` 13 行（迁移内容冻结，**建议豁免不修**）、`backend/scripts/seed_dev_data.py` 4 行、`backend/tests/test_parser.py:117` 1 行、`app/` 源码 **仅 4 行** —— `backend/app/api/v1/users.py:13`（163 字符的 schema 批量导入）、`backend/app/db.py:102`（126）、`backend/app/db.py:129`（121）、`backend/app/models/special.py:4`（121）。
- 最严重单行：`backend/scripts/seed_dev_data.py:455`（185 字符，内含 `'2025' if plan_i < 3 else '2026'` 嵌套三元），建议拆为局部变量。
- 前端 110 行 >120 字符，占比最高的是 `frontend/src/views/ErrorPage.vue`（15 行 SVG `path`/`symbol`）与 `frontend/src/router/index.ts`（16 行路由表）——二者为**可豁免的声明式长行**；真正值得处理的是 `frontend/src/views/Dashboard.vue:276-280`（ECharts 配置 5 行 143~166 字符，建议抽 `buildDeptSeries()`）与 `frontend/src/views/VulnList.vue`（9 行表格插槽单行模板，建议换行展开）。

**D-2（P1）`app/` 内 19 个函数超过 60 行，建议按优先级拆分**

> **执行后实测（2026-09-17）**：已达标 3 个（`db._migrate_lightweight` 之外 —— `workers/main.export_report_task` 168→68、`import_service.auto_export_report` 147→33、`api/v1/misc.meta` 65→6+3 个 helper）；**下表的 19 项中仍有 18 项 >60 行**，逐项现状与分档方案见 `AUDIT_FIX_LOG.md` §遗留项实施方案「遗留 3」。

| 函数 | 行数 | 拆分建议 |
|---|---|---|
| `backend/app/db.py:22-361` `_migrate_lightweight` | 340 | 按「表/域」拆成 `_migrate_imports()`、`_migrate_reports()`、`_migrate_special()` 等幂等子函数 + 顶层调度（现为单函数顺序 DDL 表） |
| `backend/app/api/v1/vulns.py:294-537` `vuln_stats` | 244 | 统计口径与 SQL 聚合分离：`_stats_filters()` + `_stats_aggregate()` + 组装 DTO |
| `backend/app/services/stats_service.py:12-190` `build_stats` | 179 | 每个图表一个 `_build_xxx()` |
| `backend/app/workers/main.py:82-249` `export_report_task` | 168 | 随 B-1 治理后自然收敛 |
| `backend/app/services/docx_parser.py:500-649` `parse_report_docx` | 150 | 按段落类型拆 `_parse_summary_table()` / `_parse_detail_sections()` / `_parse_schedule()` |
| `backend/app/services/import_service.py:432-578` `auto_export_report` | 147 | 随 B-1 治理 |
| `backend/app/services/import_service.py:596-694` `confirm_batch_internal` | 99 | 抽 `_persist_record()` / `_link_assets()` |
| `backend/app/api/v1/vulns.py:132-220` `_build_vuln_conditions` | 89 | 每种筛选维度一个 `_cond_xxx()` 追加到列表 |
| `backend/app/api/v1/imports.py:101-187` `batch_confirm_batches` | 87 | 循环体抽 `_confirm_single(batch)` |
| `backend/app/api/v1/knowledge.py:133-219` `search_entries` | 87 | 排序/相关度打分抽 `_score_row()` |
| `backend/app/services/plan_query.py:82-163` `plan_conditions` | 82 | 同 `_build_vuln_conditions` 思路 |
| `backend/app/db.py:403-481` `init_db` | 79 | 拆「建表 / 轻量迁移 / 种子」三段 |
| `backend/app/services/plan_query.py:354-430` `compute_plan_stats` | 77 | 抽取每个统计块 |
| `backend/app/services/vuln_service.py:238-314` `sync_plan_retest_state` | 77 | 判定与状态写入分离（该函数为工单级复测口径唯一实现，拆分时勿改语义） |
| `backend/app/services/plan_query.py:433-507` `compute_conclusion` | 75 | 按结论文案分块 |
| `backend/app/api/v1/reports.py:573-644` `retest_report` | 72 | 章节复制逻辑下沉 service |
| `backend/app/services/plan_io.py:107-177` `upsert_plans` | 71 | 行解析与入库分离 |
| `backend/app/api/v1/testing_plan.py:358-427` `complete_plan_no_vuln` | 70 | 校验/落库/审计分离 |
| `backend/app/services/docx_parser.py:120-187` `parse_docx` | 68 | 表格解析抽 helper |
| `backend/app/api/v1/misc.py:63-127` `meta` | 65 | 各字典域抽 `_xxx_meta()` |

**D-3（P2）真实深嵌套（≥5 层，已排除 `elif` 计入）**

| 函数 | 实测深度 |
|---|---|
| `backend/app/workers/main.py:82` `export_report_task` | 6 |
| `backend/scripts/migrate_utc_to_utc8.py:29` `migrate` | 6 |
| `backend/app/services/docx_parser.py:500` `parse_report_docx` | 5 |
| `backend/app/db.py:364` `_backfill_asset_tech_fields` | 5 |

> **口径校正说明**：初次统计把 `elif` 链按 AST 嵌套计入，导致 `backend/app/services/nonpen_service.py:67` `apply_item_action` 显示为 9 层。经排除 `elif` 重算后其真实深度为 **1**（纯扁平 `if/elif` 分派，且每个分支仅 1~3 行，可读性良好）。本节数值均为校正后结果，避免误导改造方向。

---

### E. 过度耦合

**E-1（P1）`frontend/src/components/PlanWorkflowDrawer.vue` 职责过载**

- 实测：**733 行**、15 条 `import`、**14 处直接 `client.*` 调用**（全前端最高）。
  > 数字更正（2026-09-17）：审计初稿的 679 行来自 `Measure-Object -Line`（跳过空行），实际总行数为 733。
- 单组件同时承担：工单流转操作、漏洞关联选择、报告列表与导出、复测记录、资产选择。
- 建议：按域抽 composable —— `usePlanReports`（列表/导出/复测）、`usePlanVulLinks`（关联选择/搜索）、`usePlanTransitions`（状态流转）；组件只保留渲染与编排。

**E-2（P1）`frontend/src/views/TestingPlanList.vue` 体量与依赖面最大**

- 实测：**1110 行**、25 条 `import`、11 处 `client.*`、25 处 `any`（四项均为全前端最高）。
  > 数字更正（2026-09-17）：审计初稿的 1044 行来自 `Measure-Object -Line`（跳过空行），实际总行数为 1110。
- 建议：拆为 `TestingPlanFilters.vue` + `TestingPlanForm.vue` + `TestingPlanStats.vue` + 列表壳；统计与导出逻辑下沉 composable。

**E-3（P1）后端路由层 fan-out 最大的是报告与导入域**

- 实测项目内模块 import 数：`backend/app/api/v1/reports.py` 13、`imports.py` 12、`testing_plan.py` 11（其后 `auth.py`/`vulns.py` 各 10）。
- 典型症状：`backend/app/api/v1/reports.py:135-187` `_create_retest_report` 在路由文件内直接编排章节复制、轮次推进与报告落库（该函数同时受「复测详情不得内嵌章节快照」约束，见 MEMORY 2026-09-10 条目）。
- 建议：把编排逻辑移入 `backend/app/services/report_service.py`，路由只做鉴权 + 入参 + 调用。

**E-4（无问题）模型与基础设施的「高被引用」不算耦合问题**

- `app.models` 被 48 个文件导入、`app.db` 45、`app.constants` 33、`app.core.timeutil` 31 —— 这些是全项目唯一法定出口（AGENTS.md 明确要求），属**健康收敛**，不应作为耦合问题整改。

**E-5（P2）前端类型逃逸 `any` 201 处 / 35 文件**

- 集中区：`TestingPlanList.vue` 25、`Dashboard.vue` 19、`PlanWorkflowDrawer.vue` 17、`VulnFormPanel.vue` 14、`AssetFormDialog.vue` 13、`ReportList.vue` 13。
- 建议：先为后端 DTO 建立前端 `types/` 声明（覆盖面最大的 `TestingPlan`/`Vul`/`Report`/`Asset`），再逐文件替换 `: any`；对 ECharts 配置等确实动态的结构保留 `any` 并加注释说明。

---

### F. 命名规范混乱

**F-1（P1）`vul` / `vuln` 双拼写并存，且缺乏成文规则**

实测并存情况（全部为现存符号）：

| `Vul*`（实体域） | `Vuln*`（字典/类型域） |
|---|---|
| 模型 `Vul`、表 `vulns` | 模型 `VulnType` |
| 路由 `app/api/v1/vulns.py` | schema `VulnTypeIn`、`VulnTypeOut` |
| 服务 `app/services/vuln_service.py` | 关联表 `vuln_assets` |
| schema 文件 `app/schemas/vuln.py`：`VulIn`/`VulOut`/`VulBatchIn`… | constants `VUL_TYPE`/`VUL_LEVEL`/`VUL_SOURCE`（又用 `VUL`） |
| 字段 `vuln_id`（如 `import_records.vuln_id`）、`retest_vul_snapshot` | 服务 `app/services/vuln_service.py`（服务名用 `vuln`） |

- 问题不在于「哪个对」，而在于**同仓两套拼写无规则可依**，新代码只能靠模仿，必然继续分叉。
- 建议（二选一，写入 `AGENTS.md` 固化）：
  1. **推荐**：按域区分 —— 「漏洞实体」用 `Vul`/`vul*`（模型、表、URL、字段、服务），「漏洞字典/分类」用 `Vuln*`（`VulnType`、`VulnTypeIn/Out`）。据此把 `vuln_assets` → `vul_assets`、`vuln_service.py` → `vul_service.py`，`VulnType*` 保持不变。
  2. **保守**：一律 `Vuln*`，代价是全量重命名（涉及大量路由/前端调用），不推荐在无迁移窗口时执行。
- 无论选哪种，**先加一条测试或 CI 检查**防止新分叉继续产生。

**F-2（P2）前端「打开弹窗」有 5 种命名族**

实测：`openDialog`（8 个文件：`useCrudDialog.ts` 及 `GroupList`/`KnowledgeList`/`NonpenPlanList`/`NotifyChannelList`/`RemoteTestingList`/`SpringActionList`/`TestingPlanList`）、`openCreateAsset`（`VulnFormPanel.vue`、`RemoteTestingList.vue`、`TestingPlanList.vue`）、`openWorkflow`（`NonpenPlanList.vue`、`TestingPlanList.vue`）、`onOpen`（`AssetFormDialog.vue`、`TemplatePickerDialog.vue`）、以及独立组件导出的 `open`（`PdfPreviewDialog.vue`、`CmdPalette.vue`）。
- 建议：统一为 `open<Target>`（`openDialog` → `openFormDialog`；`onOpen` → `open`；`open` 作为组件对外 API 保留但配套 `@closed` 命名对称）。

**F-3（P2）同名不同义 / 同名不同实现**

- 同名不同义：`typeName` 在 `frontend/src/components/VulnFormPanel.vue`（漏洞类型名）与 `frontend/src/views/NotifyChannelList.vue`（通知渠道类型名）语义不同。
- 同名不同实现（各 9 个文件）：`save`、`load`、`remove`；`reload` 5 个文件；`openDialog` 8 个文件。
- 建议：加域前缀（`savePlan`/`saveVul`/`saveAsset`、`loadMembers`/`loadRoles`、`removeBatch`/`removeExportJob`），与已存在的 `loadAssetLabels`、`removeExportJob` 风格对齐。

**F-4（P3）弱语义命名**

- `frontend/src/utils/colors.ts` 的 `statusSoftStyleEx(60)`：`Ex` 后缀无信息量（实测该函数专用于工单「复测完成」标注，见 MEMORY 2026-09-17 条目）→ 建议改名 `statusSoftStyleRetestDone` 或 `statusSoftStyleFor(code)`。
- `frontend/src/views/NonpenPlanList.vue:305` 的 `loadAssetLabelsRaw`（重命名自 `loadAssetLabels`，含义是「绕过缓存的原始加载」）→ 建议改名 `loadAssetLabelsUncached` 并加一行注释说明为何不用缓存。

**F-5（无问题）后端函数命名执行良好**

实测 `backend/`（app + scripts + tests）中不符合 `snake_case` 的普通函数/方法 **0 处**（`127` 条初判全部为 PascalCase 类名，属正确用法）。问题集中在术语与前端命名族，而非大小写风格。

---

## 六、修复优先级路线图（建议批次）

| 批次 | 内容 | 条目 | 预估 |
|---|---|---|---|
| 第 1 批（正确性） | 消除导出 meta 双实现与口径分叉；统一复测判定口径 | B-1、B-2 | 1~1.5 天（含回归测试） |
| 第 2 批（健壮性） | 前端伪造成功响应整改；后端异常归一化收敛；静默吞异常补日志；`seed_dev_data` 加目标库守卫 | C-2、C-3、C-1、A-4 | 0.5~1 天 |
| 第 3 批（收敛重复） | 克隆函数抽象（删除类/权限/工单ID/字典映射）、测试 mock 样板、上传解析共用 | B-3 ~ B-8 | 1~1.5 天 |
| 第 4 批（体量与解耦） | `PlanWorkflowDrawer`、`TestingPlanList` 拆分；`reports.py` 编排下沉；19 个超长函数按表拆分 | E-1 ~ E-3、D-2 | 2~3 天（可分次） |
| 第 5 批（规范化） | 固化 `vul`/`vuln` 规则到 AGENTS.md + 检查；前端命名族统一；`any` 递减 | F-1 ~ F-4、E-5 | 1~2 天 |
| 第 6 批（清理） | 12 处未使用 import；长行格式化；脚本目录合并/废弃（见 SCRIPTS.md） | A-1、A-2、D-1、SCRIPTS | 0.5 天（✅ 除 M-2/S-5 外已执行） |

> 各批次的实际执行情况、测试结果与遗留项见 [`AUDIT_FIX_LOG.md`](./AUDIT_FIX_LOG.md)（唯一执行记录）。

**工具链建议（P2）**：把 `ruff`（lint + format，可覆盖长行/E501 与未使用 import F401）与 `vulture`（死代码）加入 `backend` 开发依赖，并在 CI/本地 pre-commit 运行；本次审计中这两类问题全部靠自建脚本发现，长期看不可持续。注意：`app/schemas/__init__.py` 的重导出需在 ruff 配置中声明 `__all__` 或使用 `F401` 例外，否则会产生 92 条噪声告警。

## 七、审计方法与局限

1. **数据来源**：全部结论来自对上述文件的实际读取与静态分析（AST + 文本），未修改任何业务代码。
2. **启发式局限**：
   - 死代码判定基于「名字出现次数」，无法识别通过 `getattr(obj, "name")` / 字符串路由 / 模板反射调用的符号 —— 因此**只报告确认项**，未把疑似项写成结论。
   - 未使用 import 的初判对「按设计重导出」的 `__init__.py` 会产生系统性误报（本次 92 条），已在 §4 中扣除后给出真实数量。
   - 「结构克隆」按 AST 归一化比对，**只发现完全同构**的函数；参数/常量不同但逻辑相似的函数不会被发现，故 §B 的重复实现在数量上是**下界**而非全集。
   - 嵌套深度初版把 `elif` 计入（已在 §D-3 校正并说明）。
3. **未覆盖范围**：性能压测、并发/事务正确性、SQL 注入与越权等安全测试、前端渲染性能（Lighthouse）、依赖漏洞扫描（无 SCA 工具）。
4. **未执行项**：未运行后端 pytest 与前端 vitest（本次为纯静态审计，不对运行时行为下结论）。
