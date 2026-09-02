# Talos 开放 API 访问指南（个人访问令牌调用篇）

> 面向**已创建个人访问令牌（PAT）的调用方**：本文档说明如何用令牌通过 HTTP 接口访问 Talos 系统数据
> —— 漏洞与态势（只读）、渗透测试工单与漏扫基线工单（查询 / 创建 / 更新）——
> 包含认证方式、接口清单与参数、响应字段、错误码处理，以及 curl / Python / JavaScript 完整示例。
>
> 令牌的**创建与吊销**在 Web 界面操作（右上角头像 →「访问令牌」→ `/tokens`，页面内亦可打开本文档），第 2 节仅作简要交代。

---

## 1. 适用范围与能力边界

| 项目 | 说明 |
|---|---|
| 可访问端点 | **漏洞与态势（只读）**：`GET /open/vulns`、`GET /open/stats`；**工单（读写）**：`/open/testing-plans`、`/open/nonpen-plans` |
| 认证方式 | 仅个人访问令牌（`tlp_` 前缀），JWT 会话令牌**不接受** |
| 读权限 | 令牌代表**创建者身份**，但查询接口不做 RBAC 校验、不过滤数据归属，可读取全量漏洞 / 态势 / 工单 |
| 写权限 | **仅工单接口支持写入**（创建与更新），且按令牌所属用户的角色权限校验 `special:manage`，与站内一致；**删除、漏洞与报告写入一律不支持** |
| 站内接口 | **不可用**。`GET /api/v1/vulns`、`/api/v1/testing-plans` 等站内端点只认 JWT，携带 PAT 访问返回 401 |
| 限流 | 每令牌每分钟 120 次（`PAT_RATE_LIMIT`，服务端可用 `VP_PAT_RATE_LIMIT` 调整），超限 429 |

> 结论：PAT 是**漏洞/态势只读出口 + 工单读写出口**，适合安全大屏、日报脚本、工单自动化与数据同步；
> 漏洞录入、报告编辑、工单删除等仍需在系统界面或站内接口（JWT）完成。

---

## 2. 前置：拿到一枚令牌

1. 浏览器登录 Talos → 右上角**头像下拉** → **访问令牌**（路由 `/tokens`，不在左侧菜单栏）。
2. 点击 **新建令牌**，填写「名称」（≤64 字符，建议写明用途，如 `安全大屏看板`），选择有效期：**7 / 30 / 90 / 365 天**四档（后端强校验，不支持自定义天数，也**不支持永不过期**）。
3. 创建成功后弹出一次性明文窗口：

   > 请立即复制保存：明文令牌仅此一次展示，关闭后无法再查看。

   令牌形如 `tlp_Y7xR9...`（`tlp_` + 43 字符，共 47 位）。系统只保存其 SHA-256，**明文丢失只能吊销重建**。

4. 列表页可看到每枚令牌的：`名称` / `令牌前缀`（明文前 12 位，用于辨认）/ `有效期至` / `最近使用`（从未调用时显示「从未使用」）/ `状态`（有效 / 已过期）/ `创建时间`，以及行内「吊销」按钮。

约束：每个用户最多 **20 个有效令牌**，超出需先吊销。

---

## 3. 认证方式

### 3.1 请求头格式（唯一正确姿势）

```http
GET /api/v1/open/vulns?page=1&size=20 HTTP/1.1
Host: <你的 Talos 域名或 IP>
Authorization: Bearer tlp_Y7xR9xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Accept: application/json
```

- **请求头名称**：`Authorization`
- **值格式**：`Bearer ` + 明文令牌（单词 `Bearer`、一个半角空格、令牌原文）
- 令牌**不要**放在 URL query、`Cookie` 或请求体中；也不要使用 `Basic` 认证。
- 无需 Cookie / CSRF Token / `X-API-Key`，无需先调用登录接口换取会话。

### 3.2 基础路径（Base URL）

| 环境 | Base URL |
|---|---|
| 生产（Docker Compose + nginx，80/443） | `https://<你的域名>/api/v1`（或 `http://<VPS_IP>/api/v1`） |
| 本地调试（前端 Vite 27014，已代理 `/api`） | `http://localhost:27014/api/v1` |
| 本地调试（直连后端 uvicorn 27015） | `http://localhost:27015/api/v1` |

开放接口的完整 URL 即：`{Base URL}/open/vulns`、`{Base URL}/open/stats`。

### 3.3 浏览器直连的注意点（CORS）

后端 CORS 白名单默认为 `http://localhost` 与 `http://localhost:27014`（`CORS_ORIGINS`）。
**浏览器端 JS 直接调用会被跨域拦截**，除非你的站点已加入服务端白名单。
推荐做法：**在服务端（后端脚本 / 定时任务 / 中间层）调用**，前端页面不要持有 PAT。

---

## 4. 接口一：漏洞分页查询

```
GET /api/v1/open/vulns
```

### 4.1 请求参数（全部为 query string，GET）

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `search` | string | `""` | 关键词，模糊匹配**漏洞标题 / 受影响 URL / 关联资产名称**（三个字段 OR） |
| `status` | int | — | 状态**单选**，见 4.2 状态码表 |
| `statuses` | string | `""` | 状态**多选**，英文逗号分隔，如 `10,50,55`。非空时忽略 `status` |
| `level` | int | — | 等级**单选**，见 4.2 等级码表 |
| `levels` | string | `""` | 等级**多选**，如 `10,20`。非空时忽略 `level` |
| `vul_type` | int | — | 漏洞类型**单选**，见 4.2 类型码表 |
| `vul_types` | string | `""` | 类型**多选**，如 `10,15`。非空时忽略 `vul_type` |
| `testing_plan_id` | int | — | 按关联的渗透测试工单 ID 过滤 |
| `submit_time_from` | string | `""` | 录入时间起，格式 **`YYYY-MM-DD`**（含当天 00:00） |
| `submit_time_to` | string | `""` | 录入时间止，格式 **`YYYY-MM-DD`**（**含当天 23:59:59**，闭区间） |
| `sort` | string | `""` | 排序字段，仅在白名单内生效：`id` / `title` / `level` / `vul_type` / `status` / `submit_time` |
| `order` | string | `desc` | `desc` 降序；**除 `desc` 外的任何值均按升序**处理 |
| `page` | int | `1` | 页码，从 1 开始（`< 1` 触发 422） |
| `size` | int | `20` | 每页条数，**1–100**（超出触发 422） |

> 参数要点
> - 单选与多选**互斥**：多选参数非空时，同名单选参数被忽略。
> - **时间格式必须严格为 `YYYY-MM-DD`**；格式非法时该条件被**静默忽略**（不报错、不筛选），这是最常见的"筛选没生效"原因。
> - 非法排序字段不会报错，会回退默认排序：`submit_time` 降序（并以 `id` 降序作为稳定次序）。
> - 该接口**不提供** `asset_id` / `department` / `system_type` / `mine` 等参数（这些仅站内 `/api/v1/vulns` 支持）；如需按部门/资产筛选，请拉取后在本地按响应中的 `department`、`assets` 字段过滤。

### 4.2 字典码表

**等级 `level` / `levels`**

| 码值 | 名称 |
|---|---|
| 10 | 严重 |
| 20 | 高危 |
| 30 | 中危 |
| 40 | 低危 |
| 50 | 安全 |

**状态 `status` / `statuses`**

| 码值 | 名称 |
|---|---|
| 10 | 未修复 |
| 20 | 已忽略 |
| 35 | 暂不处理 |
| 50 | 修复中 |
| 55 | 复测中 |
| 60 | 已修复 |

**漏洞类型 `vul_type` / `vul_types`**

| 码值 | 名称 | 码值 | 名称 |
|---|---|---|---|
| 10 | SQL注入漏洞 | 45 | 逻辑漏洞 |
| 15 | XSS跨站漏洞 | 50 | 存在后门 |
| 20 | 命令执行漏洞 | 55 | 信息泄露 |
| 25 | 代码执行漏洞 | 60 | 文件上传 |
| 30 | 文件包含漏洞 | 65 | 弱口令 |
| 35 | 任意文件操作 | 70 | 威胁情报 |
| 40 | 权限绕过 | 75 | 其他 |

> 以上字典以后端 `app/constants.py` 为唯一来源，站内 `/api/v1/meta` 亦可获取。

### 4.3 响应结构

```json
{
  "total": 128,
  "items": [
    {
      "id": 1024,
      "title": "某系统后台存在SQL注入",
      "vul_type": 10,
      "level": 20,
      "source": 0,
      "layer": 10,
      "affected_url": "https://example.com/admin/list",
      "description_html": "<p>...</p>",
      "description_json": null,
      "reproduce_html": "<p>...</p>",
      "reproduce_json": null,
      "solution_html": "<p>...</p>",
      "solution_json": null,
      "score": 7.5,
      "risk_score": 0,
      "left_risk_score": 0,
      "asset_level": 0,
      "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
      "asset_ids": [12, 30],
      "testing_plan_id": 88,
      "status": 50,
      "department": "信息技术部、网金部",
      "retest_html": "",
      "retest_json": null,
      "is_retest": false,
      "delay_days": 0,
      "delay_reason": "",
      "submitter_id": 3,
      "assets": [
        { "id": 12, "name": "统一身份认证系统", "sub_system": "SSO", "department": "信息技术部" },
        { "id": 30, "name": "网金门户", "sub_system": "", "department": "网金部" }
      ],
      "submit_time": "2026-08-21T10:12:33",
      "audit_time": null,
      "notice_time": null,
      "fix_time": null,
      "update_time": "2026-08-25T09:01:02"
    }
  ]
}
```

**顶层字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| `total` | int | 符合条件的**总条数**（非本页条数），用于计算总页数 |
| `items` | array | 当前页数据 |

**`items[]` 关键字段**

| 字段 | 说明 |
|---|---|
| `id` | 漏洞 ID |
| `title` | 漏洞标题 |
| `level` / `vul_type` / `status` / `layer` / `source` | 字典码（int），按 4.2 表翻译；`source=0` 表示未选择来源（关联渗透测试工单的漏洞固定为 0） |
| `affected_url` | 受影响 URL |
| `description_html` / `reproduce_html` / `solution_html` | 漏洞描述 / 复现过程 / 修复建议（**富文本 HTML**，已消毒；`*_json` 为 TipTap 文档结构，可能为 `null`） |
| `cvss_vector` | CVSS 3.1 向量串，空串表示未评分 |
| `score` / `risk_score` / `left_risk_score` / `asset_level` | 评分与风险分值 |
| `assets[]` / `asset_ids[]` | 关联资产（多对多）。`assets[]` 含 `id` / `name` / `sub_system` / `department` |
| `department` | 归属部门，由关联资产聚合，多个用「、」连接 |
| `testing_plan_id` | 关联渗透测试工单 ID，未关联为 `null` |
| `is_retest` / `retest_html` | 是否复测及复测详情富文本 |
| `delay_days` / `delay_reason` | 延期天数与原因 |
| `submitter_id` | 提交人用户 ID |
| `submit_time` / `audit_time` / `notice_time` / `fix_time` / `update_time` | 各时间节点，字符串格式 `YYYY-MM-DDTHH:MM:SS`，**均为 UTC+8（北京时间）且不带时区后缀**，可能为 `null` |

---

## 5. 接口二：安全态势聚合统计

```
GET /api/v1/open/stats
```

### 5.1 请求参数（query string，GET）

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `date_from` | string | `""` | 录入时间起，`YYYY-MM-DD`（含当天） |
| `date_to` | string | `""` | 录入时间止，`YYYY-MM-DD`（含当天） |
| `department` | string | `""` | 部门名称，**按「渗透测试工单所属部门」精确匹配**（≠ 资产部门） |
| `source` | int | — | 漏洞来源码：10 工信部远程检测 / 20 春耕行动 / 30 集团众测 / 40 集团ASM远程检测 / 50 数智事业部远程检测 |
| `level` | int | — | 等级单选，码值同 4.2 |

> 注意：本接口**不支持分页**（一次性返回全量聚合结果），且 `department` 的口径与 `/open/vulns` 响应里的 `department`（资产部门聚合）**不同**，混用时需留意。

### 5.2 响应结构

```json
{
  "total_vulns": 128,
  "total_assets": 46,
  "open_vulns": 57,
  "fix_rate": 55.5,
  "by_status":  [{ "status": 10, "name": "未修复", "count": 30 }, { "status": 60, "name": "已修复", "count": 71 }],
  "by_level":   [{ "level": 20, "name": "高危", "count": 12 }],
  "by_type":    [{ "type": 10, "name": "SQL注入漏洞", "count": 20 }],
  "by_department": [
    {
      "department": "信息技术部",
      "plans": 8,
      "vulns": 40,
      "high": 6,
      "fixed": 30,
      "open": 8,
      "fix_rate": 75.0,
      "mandays": 24.5
    }
  ],
  "trend": [{ "month": "2025-10", "submitted": 12, "fixed": 5 }]
}
```

| 字段 | 说明 |
|---|---|
| `total_vulns` | 筛选后漏洞总数 |
| `total_assets` | 资产总数（**不受筛选条件影响**，为全库资产数） |
| `open_vulns` | 未闭环数 = 总数 − 已修复 − 已忽略 |
| `fix_rate` | 修复率（百分数，`已修复 / 总数 × 100`，保留 1 位小数） |
| `by_status[]` | 状态分布：`status` 码 + `name` 名称 + `count` |
| `by_level[]` | 等级分布：`level` 码 + `name` + `count` |
| `by_type[]` | 类型 Top10（按数量降序），未知类型统一并入「其他」 |
| `by_department[]` | 部门维度：`plans` 工单数 / `vulns` 发现漏洞 / `high` 高危及以上 / `fixed` 已修复 / `open` 未闭环 / `fix_rate` 修复率（无关联漏洞时为 `null`）/ `mandays` 实际人天 |
| `trend[]` | 近 12 个月趋势：`month`（`YYYY-MM`）+ `submitted`（当月提交）+ `fixed`（当月已修复） |

---

## 6. 渗透测试工单接口（/open/testing-plans）

路径、请求体与响应模型沿用站内工单 API，仅认证方式换为 PAT。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/open/testing-plans` | PAT 登录即可 | 分页列表 |
| GET | `/api/v1/open/testing-plans/{id}` | PAT 登录即可 | 单条详情 |
| POST | `/api/v1/open/testing-plans` | PAT + `special:manage` | 创建工单 |
| PUT | `/api/v1/open/testing-plans/{id}` | PAT + `special:manage` | 全量更新工单 |

### 6.1 列表参数（GET /open/testing-plans）

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `search` | string | `""` | 模糊匹配**测试系统 / 所属部门 / 测试类型** |
| `status` | int | — | 工单状态单选，见 6.2 |
| `test_type` | string | `""` | 测试类型（包含匹配） |
| `department` | string | `""` | 所属部门（**精确匹配**） |
| `receive_from` / `receive_to` | string | `""` | 需求接收日期范围，`YYYY-MM-DD` 闭区间 |
| `first_test_from` / `first_test_to` | string | `""` | 初测完成日期范围，`YYYY-MM-DD` 闭区间 |
| `sort` | string | `""` | 排序字段白名单：`id` / `system_name` / `plan_name` / `test_type` / `department` / `status` / `est_mandays` / `actual_mandays` / `receive_time` / `ticket_seq` / `first_test_done_time` / `retest_done_time` / `create_time` |
| `order` | string | `desc` | `desc` 降序；其余值按升序 |
| `page` | int | `1` | 页码，≥1 |
| `size` | int | `20` | 每页条数，1–100 |

默认排序：`receive_time` 降序 → `ticket_seq` 降序 → `id` 降序。

### 6.2 工单状态码

| 码值 | 名称 | 码值 | 名称 |
|---|---|---|---|
| 10 | 未测试 | 40 | 复测申请 |
| 20 | 初测中 | 50 | 复测中 |
| 30 | 等待复测 | 60 | 复测完成 |
| 70 | 测试通过（无漏洞闭环终态） | | |

合法流转：

| 当前状态 | 可流转到 |
|---|---|
| 10 未测试 | 20 初测中、70 测试通过 |
| 20 初测中 | 30 等待复测、70 测试通过 |
| 30 等待复测 | 40 复测申请、50 复测中 |
| 40 复测申请 | 50 复测中 |
| 50 复测中 | 60 复测完成 |
| 60 复测完成 | 50 复测中 |
| 70 测试通过 | 20 初测中 |

### 6.3 创建工单（POST）

```bash
curl -sS -X POST "$TALOS_BASE/open/testing-plans" \
  -H "Authorization: Bearer $TALOS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "system_name": "统一身份认证系统",
        "plan_name": "2026年三季度渗透测试",
        "test_type": "渗透测试",
        "department": "信息技术部",
        "receive_time": "2026-09-03",
        "status": 10,
        "est_mandays": 5,
        "asset_ids": [12],
        "target_urls": ["https://sso.example.com"],
        "detail": "由工单系统自动创建"
      }'
```

**请求体字段**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `system_name` | string | **是** | — | 测试系统，1–128 字符 |
| `plan_name` | string | 否 | `""` | 计划名称（与测试系统区分） |
| `test_type` | string | 否 | `""` | 测试类型 |
| `department` | string | 否 | `""` | 所属部门 |
| `receive_time` | string | 否 | `""` | 需求接收日期 `YYYY-MM-DD`，**工单ID 的生成依据** |
| `ticket_time` | string | 否 | `""` | 工单提起时间 |
| `ticket_id_manual` | string | 否 | `""` | 手动指定工单ID；留空则按「接收日期 + 当日序号」自动生成 |
| `first_test_done_time` | string | 否 | `""` | 初测完成日期 |
| `status` | int | 否 | `10` | 工单状态，见 6.2 |
| `retest_notice_time` / `retest_done_time` | string | 否 | `""` | 复测通知 / 复测完成日期 |
| `stat_critical` / `stat_high` / `stat_medium` / `stat_low` | int | 否 | `0` | 手填漏洞统计（有关联漏洞时以自动重算为准） |
| `est_mandays` / `actual_mandays` | float | 否 | `0` | 预估 / 实际人天 |
| `actual_mandays_override` | bool | 否 | `false` | 实际人天手动修正标志（置 true 后不再被报告自动覆盖） |
| `asset_ids` | int[] | 否 | `[]` | 关联资产 ID |
| `target_urls` | string[] | 否 | `[]` | 被测系统 URL |
| `no_vul_conclusion` | string | 否 | `""` | 无漏洞闭环结论 |
| `detail` | string | 否 | `""` | 备注 |
| `create_nonpen` | bool | 否 | `false` | 是否联动创建漏扫基线工单（共享工单ID） |
| `nonpen_test_items` | string[] | 否 | `[]` | 联动创建时勾选的非渗透测试项：`baseline` / `host` / `web` |

**工单ID 规则**：`ticket_id_manual` 非空时以它为准；否则由 `receive_time` + 当日最大序号+1 生成，形如 `20260903-3`。
**序号序列为渗透测试工单与漏扫基线工单两表共享**，即同一接收日期内两类工单合计连续编号。

**响应（200）**

```json
{
  "id": 88,
  "ticket_id": "20260903-1",
  "ticket_seq": 1,
  "system_name": "统一身份认证系统",
  "plan_name": "2026年三季度渗透测试",
  "test_type": "渗透测试",
  "department": "信息技术部",
  "receive_time": "2026-09-03",
  "status": 10,
  "est_mandays": 5.0,
  "actual_mandays": 0,
  "asset_ids": [12],
  "target_urls": ["https://sso.example.com"],
  "detail": "由工单系统自动创建",
  "testers": [],
  "vuls": [],
  "reports": [],
  "retest_rounds": [],
  "retest_round_count": 0,
  "create_time": "2026-09-03T10:20:31",
  "update_time": "2026-09-03T10:20:31"
}
```

`testers[]` 为测试人员摘要（`id` / `username` / `realname`），`vuls[]` 为关联漏洞摘要（`id` / `title` / `level` / `status` / `layer`），`reports[]` 为关联报告摘要（`id` / `title` / `status` / `actual_mandays` / `create_time`），`retest_rounds[]` 为复测轮次（`round_no` / `start_time` / `done_time` / `source`）。

### 6.4 更新工单（PUT）

```bash
curl -sS -X PUT "$TALOS_BASE/open/testing-plans/88" \
  -H "Authorization: Bearer $TALOS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"system_name":"统一身份认证系统","plan_name":"2026年三季度渗透测试",
       "test_type":"渗透测试","department":"信息技术部","receive_time":"2026-09-03",
       "status":20,"asset_ids":[12],"target_urls":["https://sso.example.com"],"detail":"已启动初测"}'
```

> ⚠️ **PUT 是全量更新，不是增量补丁**：请求体字段与创建时完全一致，**未传字段会被重置为默认值**。
> 正确姿势：先 `GET` 详情 → 在返回的 JSON 上改字段 → 整体 `PUT` 回去
> （返回体中的 `id` / `ticket_id` / `ticket_seq` / `testers` / `vuls` / `reports` 等只读字段会被忽略）。
> `create_nonpen` / `nonpen_test_items` 仅创建时生效，更新时忽略。

更新时的服务端约束：

| 场景 | 结果 |
|---|---|
| 状态码未变化 | 任何有 `special:manage` 的账号均可更新 |
| 状态码发生变化 | 操作者须为**该工单的认领者**或权限含 `*` 的管理员，否则 403 |
| 流转不合法（如 20 → 60） | 400「不允许从当前状态流转到目标状态」 |
| 流转为 70 测试通过且工单存在关联漏洞 | 400「该计划存在关联漏洞，不能流转为「测试通过」」 |
| 工单ID 与其他工单重复（含联动的漏扫基线工单） | 400「工单ID「xxx」已存在，请更换后保存」 |
| 工单 ID 不存在 | 404「渗透测试工单不存在」 |
| 状态发生流转 | 额外写一条 `plan_transition` 审计日志 |

---

## 7. 漏扫基线工单接口（/open/nonpen-plans）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/open/nonpen-plans` | PAT 登录即可 | 分页列表 |
| GET | `/api/v1/open/nonpen-plans/{id}` | PAT 登录即可 | 单条详情 |
| POST | `/api/v1/open/nonpen-plans` | PAT + `special:manage` | 创建工单 |
| PUT | `/api/v1/open/nonpen-plans/{id}` | PAT + `special:manage` | 全量更新工单 |

### 7.1 列表参数（GET /open/nonpen-plans）

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `search` | string | `""` | 匹配计划名称 / 测试系统 / 所属部门 / 工单ID（手动值，或 `YYYYMMDD-N` 自动编号） |
| `actionable` | bool | `false` | `true` 时仅返回「可进行」工单：存在非忽略测试项处于可测试状态 |
| `sort` | string | `""` | 白名单：`id` / `plan_name` / `system_name` / `test_type` / `department` / `receive_time` / `ticket_time` / `ticket_seq` / `create_time` |
| `order` | string | `desc` | 同渗透测试工单 |
| `page` / `size` | int | `1` / `20` | 同渗透测试工单 |

### 7.2 创建 / 更新（POST、PUT）

```bash
curl -sS -X POST "$TALOS_BASE/open/nonpen-plans" \
  -H "Authorization: Bearer $TALOS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "system_name": "网金门户",
        "department": "网金部",
        "receive_time": "2026-09-03",
        "test_items": ["baseline", "web"],
        "asset_ids": [30]
      }'
```

**请求体字段**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `system_name` | string | **是** | 测试系统，1–128 字符 |
| `plan_name` | string | 否 | 计划名称 |
| `test_type` | string | 否 | 测试类型 |
| `department` | string | 否 | 所属部门 |
| `receive_time` | string | 条件必填 | 需求接收日期；**与 `ticket_id_manual` 至少填一个**（否则 422） |
| `ticket_time` | string | 否 | 工单提起时间 |
| `ticket_id_manual` | string | 条件必填 | 手动指定工单ID；与渗透测试工单共享当日序号序列 |
| `asset_ids` | int[] | 否 | 关联资产 ID |
| `test_items` | string[] | 否 | 勾选的测试项，取值只能是 `baseline`（基线扫描）/ `host`（主机漏洞扫描）/ `web`（Web漏洞扫描）；未勾选项置 `ignored` 不参与统计 |
| `detail` | string | 否 | 备注 |

**响应（200）**

```json
{
  "id": 12,
  "system_name": "网金门户",
  "department": "网金部",
  "receive_time": "2026-09-03",
  "ticket_seq": 2,
  "ticket_id": "20260903-2",
  "asset_ids": [30],
  "items": {
    "baseline": {"status": "not_started", "first_times": 0, "retest_times": 0},
    "host":     {"status": "ignored",     "first_times": 0, "retest_times": 0},
    "web":      {"status": "not_started", "first_times": 0, "retest_times": 0}
  },
  "testing_plan_id": null,
  "linked": false,
  "actionable": true,
  "detail": "",
  "create_time": "2026-09-03T10:25:02",
  "update_time": "2026-09-03T10:25:02"
}
```

**`items` 测试项容器**

| 字段 | 说明 |
|---|---|
| `status` | `not_started` 未开始 / `testing` 测试中 / `wait_retest` 等待复测 / `retesting` 复测中 / `retest_done` 复测完成 / `ignored` 已忽略 |
| `first_times` | 初测次数（扫描次数口径按此统计，复测不重复计数） |
| `retest_times` | 复测次数 |
| `testing_plan_id` | 非空表示由渗透测试工单联动创建（共享工单ID，编辑公共字段双向同步） |
| `linked` / `actionable` | 是否联动创建 / 是否存在可进行的测试项 |

**更新语义（PUT）**：与创建同结构全量更新；`test_items` 走**合并**而非覆盖——
新勾选项置 `not_started` 且次数清零、取消勾选项置 `ignored` 但保留历史次数、未变化项原样保留。

> 测试项的状态推进（开始初测 / 完成 / 发起复测 / 通过 / 忽略）**未提供开放接口**，请在系统「漏扫基线工单」页面操作。

---

## 8. 错误码与处理

所有错误响应体均为 FastAPI 默认结构：

```json
{ "detail": "错误描述" }
```

参数校验失败（422）时 `detail` 为数组：

```json
{ "detail": [{ "loc": ["query", "size"], "msg": "Input should be less than or equal to 100", "type": "less_than_equal" }] }
```

### 8.1 完整错误对照表

| HTTP | `detail` 原文 | 触发原因 | 处理建议 |
|---|---|---|---|
| 401 | `Not authenticated` | 请求**未携带** `Authorization` 头，或格式不是 `Bearer <token>` | 检查请求头拼写与前缀空格 |
| 401 | `开放 API 仅支持个人访问令牌（Bearer tlp_xxx）` | 携带的是 **JWT 会话令牌**（前端 `access_token`）而非 PAT | 改用 `tlp_` 开头令牌；JWT 只能访问站内 `/api/v1/*`（不含 `/open`） |
| 401 | `访问令牌无效或已吊销` | 令牌不存在（输错、多复制/少复制字符）或已被吊销 | 无法找回明文，重新创建一枚令牌 |
| 401 | `访问令牌已过期，请重新生成` | 超过创建时选择的有效期 | **无续期接口**：新建令牌 → 替换调用方配置 → 吊销旧令牌 |
| 401 | `令牌所属用户不可用` | 令牌所属账号被禁用 | 联系管理员恢复账号，或换用其他账号的令牌 |
| 401 | `登录已过期，请重新登录` | 用 **PAT 访问了站内端点**（如 `/api/v1/vulns`、`/api/v1/testing-plans`） | PAT 只能访问 `/open/*`；如需站内能力请改用 JWT 登录流程 |
| 403 | `当前令牌所属账号缺少权限: special:manage` | 用 PAT 调用工单**写接口**（POST / PUT），但令牌所属账号的角色没有 `special:manage` | 换用具备专项管理权限的账号创建的令牌；查询接口不受此限制 |
| 403 | `仅认领者或管理员可修改测试状态` | 更新渗透测试工单时**改变了状态**，但操作者既不是该工单认领者，权限也不含 `*` | 先在系统内认领该工单，或改由管理员账号的令牌执行 |
| 400 | `不允许从当前状态流转到目标状态` | 工单状态流转不在状态机白名单内（见 6.2） | 按 6.2 的流转表选择目标状态 |
| 400 | `该计划存在关联漏洞，不能流转为「测试通过」` | 工单存在关联漏洞却要把状态改为 70 测试通过 | 先处理漏洞走复测流程，或改走目标状态 60 |
| 400 | `工单ID「xxx」已存在，请更换后保存` | 手动指定的工单ID 与现有工单（含漏扫基线工单）冲突 | 更换 `ticket_id_manual`，或留空由系统自动分配 |
| 400 | `已勾选「创建漏扫基线工单」，请至少选择一个非渗透测试项` 等联动校验 | 创建渗透测试工单时 `create_nonpen=true` 但未选测试项 / 未填接收日期 | 补齐 `nonpen_test_items` 或 `receive_time` |
| 404 | `Not Found` | URL 路径写错（如漏了 `/api/v1` 前缀、把 `/open/vulns` 写成 `/vulns`） | 核对完整路径 `{BaseURL}/open/vulns` |
| 404 | `渗透测试工单不存在` / `漏扫基线工单不存在` | 工单 ID 不存在或已被删除 | 核对 ID |
| 422 | 数组（见上） | 参数类型/范围非法，如 `page=0`、`size=200`、`level=abc`；或请求体校验失败，如 `system_name` 为空、漏扫工单缺少工单ID来源、`test_items` 出现非法取值 | 读取 `detail[].loc` / `detail[].msg` 定位出错字段 |
| 429 | `请求过于频繁，请稍后再试` | 单令牌 60 秒窗口内请求数超过 120 次 | 退避重试 / 降低轮询频率 / 分页批量拉取而非逐条请求 |
| 500 | `Internal Server Error` | 服务端异常 | 重试一次；持续出现请联系管理员并提供请求时间与 URL |

### 8.2 处理策略建议

| 状态码 | 是否重试 | 建议动作 |
|---|---|---|
| 200 | — | 正常解析 |
| 400 | 否 | 修正业务参数（状态流转 / 工单ID / 必填项） |
| 401 | **否** | 直接告警并停止任务（重试只会继续失败），提示人工更换令牌 |
| 403 | 否 | 改用具备 `special:manage` 的账号令牌，或先认领工单 |
| 404 | 否 | 修正 URL 或工单 ID |
| 422 | 否 | 修正参数 |
| 429 | **是** | 指数退避：`sleep(min(2^n, 60))`，最多 3–5 次；长期方案是调大 `size`、降低频率 |
| 5xx | 是 | 最多重试 2 次，仍失败则告警 |

> 限流计数发生在**认证通过后、业务逻辑执行前**，因此被限流的请求同样占用配额；设计轮询任务时请把频率控制在 **120 次/分钟/令牌**以内（建议留 20% 余量）。

---

## 9. 调用示例

### 9.1 curl

```bash
# 建议用环境变量存放令牌，不要写进脚本或命令历史
export TALOS_BASE="https://talos.example.com/api/v1"
export TALOS_TOKEN="tlp_Y7xR9xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 1) 查询高危+严重、2026 年 8 月录入、未修复的漏洞，按等级降序，第 1 页 50 条
curl -sS -X GET "$TALOS_BASE/open/vulns" \
  -H "Authorization: Bearer $TALOS_TOKEN" \
  -H "Accept: application/json" \
  --get \
  --data-urlencode "levels=10,20" \
  --data-urlencode "statuses=10" \
  --data-urlencode "submit_time_from=2026-08-01" \
  --data-urlencode "submit_time_to=2026-08-31" \
  --data-urlencode "sort=level" \
  --data-urlencode "order=desc" \
  --data-urlencode "page=1" \
  --data-urlencode "size=50"

# 2) 关键字搜索
curl -sS "$TALOS_BASE/open/vulns?search=SQL%E6%B3%A8%E5%85%A5&size=20" \
  -H "Authorization: Bearer $TALOS_TOKEN"

# 3) 态势统计（近 30 天）
curl -sS "$TALOS_BASE/open/stats?date_from=2026-08-01&date_to=2026-08-31" \
  -H "Authorization: Bearer $TALOS_TOKEN"

# 4) 只看 HTTP 状态码与错误详情，便于排查
curl -sS -o /dev/null -w "http_code=%{http_code}\n" "$TALOS_BASE/open/stats" \
  -H "Authorization: Bearer $TALOS_TOKEN"
```

> 提示：`curl -v` 可查看是否真的发出了 `Authorization` 头；`-i` 可查看响应头（401 时会带 `WWW-Authenticate: Bearer`）。

### 9.2 Python

依赖：`pip install requests`（无第三方依赖的 `urllib` 版本见 9.2.4）。

#### 9.2.1 最小示例

```python
import requests

BASE = "https://talos.example.com/api/v1"
TOKEN = "tlp_Y7xR9xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"   # 建议从环境变量/密钥库读取

resp = requests.get(
    f"{BASE}/open/vulns",
    headers={"Authorization": f"Bearer {TOKEN}"},
    params={"levels": "10,20", "statuses": "10", "page": 1, "size": 50},
    timeout=15,
)
resp.raise_for_status()
data = resp.json()
print("总数:", data["total"])
for v in data["items"]:
    print(v["id"], v["title"], v["level"], v["status"])
```

#### 9.2.2 可直接使用的客户端（含错误处理、429 退避、自动翻页）

```python
"""Talos 开放 API 客户端示例（requests）。

环境变量：
    TALOS_BASE   https://talos.example.com/api/v1
    TALOS_TOKEN  tlp_xxx
"""
import os
import time
from typing import Any, Iterator

import requests

LEVEL_NAME = {10: "严重", 20: "高危", 30: "中危", 40: "低危", 50: "安全"}
STATUS_NAME = {10: "未修复", 20: "已忽略", 35: "暂不处理", 50: "修复中", 55: "复测中", 60: "已修复"}

# 401 的细化原因，便于给出可执行的修复提示
_HINT = {
    "Not authenticated": "缺少 Authorization 头或格式不是 'Bearer <token>'",
    "开放 API 仅支持个人访问令牌（Bearer tlp_xxx）": "误用了前端 JWT，请改用 tlp_ 开头的令牌",
    "访问令牌无效或已吊销": "令牌错误或已被吊销，请重新创建",
    "访问令牌已过期，请重新生成": "令牌已过期，请新建并替换（无续期接口）",
    "令牌所属用户不可用": "令牌所属账号已禁用，请联系管理员",
    "登录已过期，请重新登录": "PAT 不能访问站内端点，仅支持 /open/* 系列接口",
    # 403 / 400：工单写入场景的常见拒绝原因
    "当前令牌所属账号缺少权限: special:manage": "工单写接口需令牌所属账号具备 special:manage 权限",
    "仅认领者或管理员可修改测试状态": "改状态需先认领该工单，或换管理员账号的令牌",
    "不允许从当前状态流转到目标状态": "状态流转不在状态机白名单内，见文档 6.2",
}


class TalosAuthError(Exception):
    """401：不可重试，需人工介入。"""


class TalosRateLimited(Exception):
    """429：可退避重试。"""


class TalosRejected(Exception):
    """400 / 403：业务或权限拒绝，需修正请求后重发。"""


class TalosClient:
    def __init__(self, base: str, token: str, timeout: int = 15, max_retries: int = 4):
        if not token.startswith("tlp_"):
            raise ValueError("令牌应以 tlp_ 开头（当前可能是前端 JWT）")
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })

    def _request(self, path: str, params: dict | None = None,
                 method: str = "get", json: dict | None = None) -> Any:
        url = f"{self.base}{path}"
        for attempt in range(self.max_retries + 1):
            resp = self.session.request(
                method, url, params=params or {}, json=json, timeout=self.timeout,
            )

            if resp.status_code in (200, 201):
                return resp.json()

            if resp.status_code == 429 and attempt < self.max_retries:
                # 指数退避：1s → 2s → 4s → 8s（上限 60s）
                time.sleep(min(2 ** attempt, 60))
                continue

            if resp.status_code == 401:
                detail = (resp.json() or {}).get("detail", "")
                raise TalosAuthError(f"401 {detail} —— {_HINT.get(detail, '请检查令牌是否有效')}")

            if resp.status_code in (400, 403):
                detail = (resp.json() or {}).get("detail", "")
                raise TalosRejected(f"{resp.status_code} {detail} —— {_HINT.get(detail, '请修正请求后重发')}")

            if resp.status_code == 422:
                bad = ", ".join(
                    f"{'.'.join(str(x) for x in e.get('loc', []))}: {e.get('msg')}"
                    for e in resp.json().get("detail", [])
                )
                raise ValueError(f"422 参数错误 -> {bad}")

            if 500 <= resp.status_code < 600 and attempt < self.max_retries:
                time.sleep(min(2 ** attempt, 30))
                continue

            resp.raise_for_status()
        raise TalosRateLimited("429 重试次数耗尽，请降低调用频率")

    # --- 业务方法：漏洞与态势（只读） ---
    def stats(self, **params) -> dict:
        return self._request("/open/stats", params)

    def vulns_page(self, page: int = 1, size: int = 100, **params) -> dict:
        return self._request("/open/vulns", {"page": page, "size": size, **params})

    def iter_vulns(self, size: int = 100, max_pages: int = 1000, **params) -> Iterator[dict]:
        """按页遍历全部漏洞（size 最大 100）。"""
        page, fetched = 1, 0
        while page <= max_pages:
            data = self.vulns_page(page=page, size=size, **params)
            items = data.get("items", [])
            yield from items
            fetched += len(items)
            if fetched >= data.get("total", 0) or not items:
                break
            page += 1

    # --- 业务方法：工单（查询 PAT 即可；写操作需 special:manage） ---
    def list_testing_plans(self, **params) -> dict:
        return self._request("/open/testing-plans", params)

    def get_testing_plan(self, plan_id: int) -> dict:
        return self._request(f"/open/testing-plans/{plan_id}")

    def create_testing_plan(self, **payload) -> dict:
        return self._request("/open/testing-plans", method="post", json=payload)

    def update_testing_plan(self, plan_id: int, **payload) -> dict:
        """全量更新：payload 需包含全部业务字段（未传字段会被重置为默认值）。"""
        return self._request(f"/open/testing-plans/{plan_id}", method="put", json=payload)

    def list_nonpen_plans(self, **params) -> dict:
        return self._request("/open/nonpen-plans", params)

    def get_nonpen_plan(self, plan_id: int) -> dict:
        return self._request(f"/open/nonpen-plans/{plan_id}")

    def create_nonpen_plan(self, **payload) -> dict:
        return self._request("/open/nonpen-plans", method="post", json=payload)

    def update_nonpen_plan(self, plan_id: int, **payload) -> dict:
        """全量更新：test_items 走合并语义，其余字段同创建。"""
        return self._request(f"/open/nonpen-plans/{plan_id}", method="put", json=payload)


if __name__ == "__main__":
    client = TalosClient(os.environ["TALOS_BASE"], os.environ["TALOS_TOKEN"])

    # 1) 态势统计
    s = client.stats(date_from="2026-08-01", date_to="2026-08-31")
    print(f"漏洞总数={s['total_vulns']} 未闭环={s['open_vulns']} 修复率={s['fix_rate']}%")
    for row in s["by_level"]:
        print(f"  {LEVEL_NAME.get(row['level'], row['level'])}: {row['count']}")

    # 2) 遍历 2026 年 8 月的高危/严重漏洞（自动翻页）
    for v in client.iter_vulns(levels="10,20", submit_time_from="2026-08-01",
                               submit_time_to="2026-08-31", sort="submit_time", order="desc"):
        print(v["id"], LEVEL_NAME.get(v["level"]), STATUS_NAME.get(v["status"]),
              "|", v["department"], "|", v["title"])

    # 3) 查询工单
    plans = client.list_testing_plans(status=20, size=50)
    print("初测中工单:", plans["total"])

    # 4) 创建渗透测试工单（工单ID按接收日期自动生成）
    plan = client.create_testing_plan(
        system_name="统一身份认证系统", plan_name="2026年三季度渗透测试",
        test_type="渗透测试", department="信息技术部", receive_time="2026-09-03", status=10,
    )
    print("新建工单:", plan["id"], plan["ticket_id"])

    # 5) 更新：先取详情再整体 PUT（未传字段会被重置为默认值！）
    detail = client.get_testing_plan(plan["id"])
    detail["department"] = "信息安全部"
    detail["status"] = 20  # 未测试 → 初测中
    updated = client.update_testing_plan(plan["id"], **detail)
    print("已更新:", updated["department"], updated["status"])
```

#### 9.2.3 导出为 CSV（常见落地场景）

```python
import csv

FIELDS = ["id", "title", "level", "status", "vul_type", "department",
          "affected_url", "submit_time", "fix_time", "testing_plan_id"]

with open("vulns.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for v in client.iter_vulns(statuses="10,50,55"):   # 未修复 / 修复中 / 复测中
        writer.writerow(v)
```

#### 9.2.4 无第三方依赖版本（urllib）

```python
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ["TALOS_BASE"]
TOKEN = os.environ["TALOS_TOKEN"]


def open_api(path: str, **params) -> dict:
    url = f"{BASE}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        if e.code == 429:
            raise RuntimeError("触发限流（120 次/分钟/令牌），请稍后重试") from e
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


data = open_api("/open/vulns", levels="10,20", statuses="10", page=1, size=50)
print(data["total"], len(data["items"]))
```

#### 9.2.5 工单调用模式

```python
from talos_client import TalosClient, TalosRejected   # 9.2.2 客户端保存为 talos_client.py

client = TalosClient(os.environ["TALOS_BASE"], os.environ["TALOS_TOKEN"])

# ① 创建漏扫基线工单（工单ID 与渗透测试工单共享当日序号）
nonpen = client.create_nonpen_plan(
    system_name="网金门户", department="网金部",
    receive_time="2026-09-03", test_items=["baseline", "web"], asset_ids=[30],
)
print(nonpen["ticket_id"], nonpen["items"]["web"]["status"])   # 20260903-N / not_started

# ② 更新漏扫基线工单：test_items 走合并（仅勾选 web 后，baseline 被置 ignored 且次数保留）
detail = client.get_nonpen_plan(nonpen["id"])
updated = client.update_nonpen_plan(nonpen["id"], **{**detail, "test_items": ["web"]})
print(updated["items"]["baseline"]["status"])   # ignored

# ③ 状态流转须遵循状态机（见 6.2），改状态者须为工单认领者或管理员
plan = client.create_testing_plan(system_name="状态流转演示系统", receive_time="2026-09-03")
try:
    client.update_testing_plan(plan["id"], system_name="状态流转演示系统",
                               receive_time="2026-09-03", status=60)  # 10 → 60 非法
except TalosRejected as exc:
    print("被拒绝:", exc)   # 400 不允许从当前状态流转到目标状态
```

### 9.3 JavaScript / Node.js

#### 9.3.1 Node.js 18+（内置 fetch）

```js
// talos-client.mjs
const BASE = process.env.TALOS_BASE;   // https://talos.example.com/api/v1
const TOKEN = process.env.TALOS_TOKEN; // tlp_xxx

const LEVEL_NAME = { 10: '严重', 20: '高危', 30: '中危', 40: '低危', 50: '安全' };
const STATUS_NAME = { 10: '未修复', 20: '已忽略', 35: '暂不处理', 50: '修复中', 55: '复测中', 60: '已修复' };

const HINT = {
  'Not authenticated': '缺少 Authorization 头或格式不是 "Bearer <token>"',
  '开放 API 仅支持个人访问令牌（Bearer tlp_xxx）': '误用了前端 JWT，请改用 tlp_ 开头的令牌',
  '访问令牌无效或已吊销': '令牌错误或已被吊销，请重新创建',
  '访问令牌已过期，请重新生成': '令牌已过期，请新建并替换（无续期接口）',
  '令牌所属用户不可用': '令牌所属账号已禁用，请联系管理员',
  '登录已过期，请重新登录': 'PAT 不能访问站内端点，仅支持 /open/vulns 与 /open/stats',
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function openApi(path, params = {}, { retries = 4, timeout = 15000, method = 'GET', body = undefined } = {}) {
  if (!TOKEN?.startsWith('tlp_')) throw new Error('令牌应以 tlp_ 开头（当前可能是前端 JWT）');
  const url = new URL(`${BASE}${path}`);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') url.searchParams.set(k, String(v));
  }

  for (let attempt = 0; attempt <= retries; attempt++) {
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), timeout);
    let res;
    try {
      res = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${TOKEN}`,
          Accept: 'application/json',
          ...(body ? { 'Content-Type': 'application/json' } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: ac.signal,
      });
    } finally {
      clearTimeout(timer);
    }

    if (res.ok) return res.json();

    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);

    if (res.status === 429 && attempt < retries) {
      await sleep(Math.min(2 ** attempt, 60) * 1000); // 1s → 2s → 4s → 8s
      continue;
    }
    if (res.status === 401) {
      throw new Error(`401 ${detail} —— ${HINT[detail] ?? '请检查令牌是否有效'}`);
    }
    if (res.status === 422) {
      const bad = (Array.isArray(body.detail) ? body.detail : [])
        .map((e) => `${e.loc.join('.')}: ${e.msg}`).join('; ');
      throw new Error(`422 参数错误 -> ${bad}`);
    }
    if (res.status >= 500 && attempt < retries) {
      await sleep(Math.min(2 ** attempt, 30) * 1000);
      continue;
    }
    throw new Error(`HTTP ${res.status}: ${detail || res.statusText}`);
  }
  throw new Error('429 重试次数耗尽，请降低调用频率');
}

/** 自动翻页拉取全部漏洞 */
async function* iterVulns(params = {}, size = 100, maxPages = 1000) {
  let page = 1, fetched = 0;
  while (page <= maxPages) {
    const data = await openApi('/open/vulns', { ...params, page, size });
    yield* data.items ?? [];
    fetched += data.items?.length ?? 0;
    if (!data.items?.length || fetched >= data.total) break;
    page += 1;
  }
}

// ---- 使用 ----
const stats = await openApi('/open/stats', { date_from: '2026-08-01', date_to: '2026-08-31' });
console.log(`总数=${stats.total_vulns} 未闭环=${stats.open_vulns} 修复率=${stats.fix_rate}%`);

for await (const v of iterVulns({ levels: '10,20', statuses: '10', sort: 'submit_time', order: 'desc' })) {
  console.log(v.id, LEVEL_NAME[v.level], STATUS_NAME[v.status], '|', v.department, '|', v.title);
}
```

运行：

```bash
export TALOS_BASE="https://talos.example.com/api/v1"
export TALOS_TOKEN="tlp_Y7xR9xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
node talos-client.mjs
```

#### 9.3.2 axios 版本

```js
import axios from 'axios';

const api = axios.create({
  baseURL: `${process.env.TALOS_BASE}`,                       // .../api/v1
  timeout: 15000,
  headers: { Authorization: `Bearer ${process.env.TALOS_TOKEN}` },
});

// 429 退避重试
api.interceptors.response.use(null, async (err) => {
  const { response, config } = err;
  if (response?.status === 429 && (config._retry ?? 0) < 4) {
    config._retry = (config._retry ?? 0) + 1;
    await new Promise((r) => setTimeout(r, Math.min(2 ** (config._retry - 1), 60) * 1000));
    return api(config);
  }
  return Promise.reject(err);
});

const { data } = await api.get('/open/vulns', {
  params: { levels: '10,20', statuses: '10,50,55', page: 1, size: 100 },
});
console.log(data.total, data.items.length);
```

#### 9.3.3 浏览器端（不推荐）

浏览器直连会因 CORS 被拦截，且会把令牌暴露给终端用户。若确需前端取数，请：
1. 由你自己的后端服务持令牌调用 Talos，再转发给前端；
2. 或将前端站点域名加入 Talos 的 `CORS_ORIGINS` 白名单（**仅在可控内网环境**）。

#### 9.3.4 工单接口示例（Node.js）

```js
// ① 创建渗透测试工单（工单ID按接收日期自动生成）
const plan = await openApi('/open/testing-plans', {}, {
  method: 'POST',
  body: {
    system_name: '统一身份认证系统',
    test_type: '渗透测试',
    department: '信息技术部',
    receive_time: '2026-09-03',
    status: 10,
  },
});
console.log(plan.id, plan.ticket_id);   // 88 / 20260903-1

// ② 更新：先取详情再整体 PUT（未传字段会被重置为默认值！）
const detail = await openApi(`/open/testing-plans/${plan.id}`);
const updated = await openApi(`/open/testing-plans/${plan.id}`, {}, {
  method: 'PUT',
  body: { ...detail, department: '信息安全部', status: 20 },   // 未测试 → 初测中
});

// ③ 业务拒绝（400/403）以 HTTPError 抛出，detail 原文在 message 里
try {
  await openApi(`/open/testing-plans/${plan.id}`, {}, {
    method: 'PUT',
    body: { ...detail, status: 60 },   // 20 → 60 非法流转
  });
} catch (e) {
  console.error(e.message);            // HTTP 400: 不允许从当前状态流转到目标状态
}

// ④ 漏扫基线工单：创建 + 合并式更新测试项
const np = await openApi('/open/nonpen-plans', {}, {
  method: 'POST',
  body: { system_name: '网金门户', receive_time: '2026-09-03', test_items: ['baseline', 'web'] },
});
const npDetail = await openApi(`/open/nonpen-plans/${np.id}`);
const npUpdated = await openApi(`/open/nonpen-plans/${np.id}`, {}, {
  method: 'PUT',
  body: { ...npDetail, test_items: ['web'] },   // baseline 取消勾选 → ignored（次数保留）
});
```

> 写接口要求令牌所属账号具备 `special:manage` 权限，否则返回 403；查询接口无此要求。

---

## 10. 令牌运维最佳实践

| 场景 | 做法 |
|---|---|
| 存放 | 存环境变量 / 密钥库 / CI Secrets，**禁止**硬编码进源码、提交到 Git、写进前端包 |
| 一令牌一用途 | 大屏、日报脚本、数据同步各建一枚，便于单独吊销与通过「最近使用」定位调用方 |
| 有效期 | 脚本类建议 90 天；临时排查用 7 天；365 天仅用于长期稳定集成 |
| 即将过期 | 系统**不提供续期接口、也不会自动续期**：提前新建一枚 → 更新调用方配置 → 验证通过后再吊销旧令牌 |
| 已过期 | 调用返回 401「访问令牌已过期，请重新生成」，只能新建替换 |
| 泄露处置 | 立即在「访问令牌」页吊销（行内「吊销」→ 确认「吊销后无法恢复，确认吊销？」），物理删除、即时生效 |
| 审计 | 创建与吊销会写入审计日志（`pat_create` / `pat_revoke`），可在「系统管理 → 审计日志」追溯 |
| 账号变动 | 用户被禁用后，其名下所有令牌立即返回 401「令牌所属用户不可用」；**修改密码不会影响 PAT**（PAT 与 JWT 的令牌版本无关） |
| 频率控制 | 单令牌 ≤ 120 次/分钟；大批量拉取优先增大 `size`（最大 100）而不是提高请求次数 |

---

## 11. 常见问题（FAQ）

**Q1：我把前端浏览器里的 `access_token` 拿去调 `/open/vulns`，为什么 401？**
A：那枚是 JWT 会话令牌，开放 API 只认 `tlp_` 开头的 PAT，错误详情为「开放 API 仅支持个人访问令牌（Bearer tlp_xxx）」。请在「访问令牌」页单独创建 PAT。

**Q2：反过来，用 PAT 调 `/api/v1/vulns` 也 401？**
A：是的，详情为「登录已过期，请重新登录」。PAT 仅限 `/open/vulns` 与 `/open/stats` 两个端点。

**Q3：明文令牌忘了怎么办？**
A：无法找回（服务端仅存 SHA-256）。吊销该令牌并新建一枚，更新到调用方配置。

**Q4：令牌能续期吗？**
A：不能。有效期在创建时固定（7/30/90/365 天），到期只能新建替换。

**Q5：我传了 `submit_time_from=2026/08/01` 却返回了全部数据？**
A：日期格式必须严格为 `YYYY-MM-DD`；格式非法时该条件被静默忽略（不报错）。

**Q6：`size=500` 为什么报错？**
A：`size` 取值范围 1–100，超限返回 422。

**Q7：怎么按「资产部门」筛选？**
A：`/open/vulns` 不提供部门参数。请拉取后用响应中的 `department` 或 `assets[].department` 在本地过滤。
注意 `/open/stats` 的 `department` 参数口径是**渗透测试工单所属部门**，与前者不同。

**Q8：返回的时间带时区吗？**
A：不带。所有时间字段为 UTC+8（北京时间）的本地时间，格式 `YYYY-MM-DDTHH:MM:SS`，解析时请勿再按 UTC 转换。

**Q9：为什么「最近使用」一直是「从未使用」？**
A：该字段只在令牌**成功通过认证**后回写；若请求被限流（429）或在认证阶段失败，不会更新。

**Q10：可以并发用多个令牌提高吞吐吗？**
A：可以，限流按**令牌**计数。但每个用户最多 20 枚有效令牌，且需自行保证数据一致性。

**Q11：谁能通过 API 创建 / 更新工单？**
A：令牌所属账号的角色需包含 `special:manage`（或通配 `*`），否则 403。查询接口不受限制。
另外更新渗透测试工单时若**改变了状态**，操作者还须是该工单的认领者或权限含 `*` 的管理员（与站内一致）。

**Q12：为什么我 PUT 更新后没传的字段被清空了？**
A：工单更新是 **PUT 全量语义**（与站内一致），请求体与创建同结构，未传字段回落到默认值。
正确姿势：先 `GET /open/testing-plans/{id}` 取详情，在返回 JSON 上修改字段后整体 PUT（只读字段会被忽略）。

**Q13：可以通过 API 删除工单、录入漏洞或推进漏扫测试项吗？**
A：不可以。开放接口仅提供工单的查询、创建与更新；删除、漏洞写入、测试项流转等请使用系统界面或站内接口（JWT 认证）。

---

## 12. 接口速查卡

```
Base URL : https://<host>/api/v1
认证头    : Authorization: Bearer tlp_xxx
限流      : 120 次/分钟/令牌

GET /open/vulns?search=&status=&statuses=&level=&levels=&vul_type=&vul_types=
                &testing_plan_id=&submit_time_from=YYYY-MM-DD&submit_time_to=YYYY-MM-DD
                &sort={id|title|level|vul_type|status|submit_time}&order={desc|asc}
                &page=1&size=20            -> { total, items: [VulOut] }

GET /open/stats?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&department=&source=&level=
                -> { total_vulns, total_assets, open_vulns, fix_rate,
                     by_status[], by_level[], by_type[], by_department[], trend[] }

GET /open/testing-plans?search=&status=&test_type=&department=
                &receive_from=YYYY-MM-DD&receive_to=YYYY-MM-DD
                &first_test_from=YYYY-MM-DD&first_test_to=YYYY-MM-DD
                &sort={id|system_name|...|create_time}&order={desc|asc}&page=1&size=20
                -> { total, items: [TestingPlanOut] }
GET /open/testing-plans/{id}                               -> TestingPlanOut
POST /open/testing-plans        body=TestingPlanIn         -> TestingPlanOut    (需 special:manage)
PUT  /open/testing-plans/{id}   body=TestingPlanIn(全量)   -> TestingPlanOut    (需 special:manage)

GET /open/nonpen-plans?search=&actionable=&sort=&order=&page=1&size=20
                -> { total, items: [NonpenPlanOut] }
GET /open/nonpen-plans/{id}                                -> NonpenPlanOut
POST /open/nonpen-plans         body=NonpenPlanIn          -> NonpenPlanOut     (需 special:manage)
PUT  /open/nonpen-plans/{id}    body=NonpenPlanIn(全量)    -> NonpenPlanOut     (需 special:manage)

工单状态: 10未测试 20初测中 30等待复测 40复测申请 50复测中 60复测完成 70测试通过
漏扫测试项: baseline基线扫描 / host主机漏洞扫描 / web Web漏洞扫描
```
