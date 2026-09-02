# Talos 漏洞管理平台

**简体中文** | [English](README_EN.md)

Talos（塔罗斯）取名自希腊神话中守卫克里特岛的青铜巨人——刀枪不入，却因脚踝上唯一的弱点而倒下。安全工作亦是如此：找到并修复那一个致命漏洞。

Talos 是一个现代化漏洞全生命周期管理平台，基于 FastAPI + Vue 3 对内部平台「洞察 2.0 / insight2」的全量重写，覆盖漏洞提交、审核确认、修复跟踪、复测闭环到报告交付的完整流程。

## 功能特性

### 漏洞管理

- **全生命周期状态机**：待审核 → 已确认 → 修复中 → 复测 → 已完成 流转，全程操作留痕；支持多轮复测记录与结论联动
- **CVSS 3.1 评分**：表单内嵌计算器，8 项指标实时评分并按评分同步风险等级，支持向量（vector）留存
- **漏洞知识库**：沉淀典型漏洞模板，提交时一键套用，导入入库时自动回填
- **应用与资产台账**：资产与漏洞多对多关联，记录公网/内网 URL，供工单与报告取用

### 报告中心

- **Word 报告导入**：按固定模板上传初测/复测 Word 报告，后台自动解析（含图片提取）、预览确认后批量入库；导入列表支持批量关联工单与确认导出
- **在线报告编辑**：TipTap 富文本编辑器，支持表格/图片/代码块，自动保存 + 乐观锁防冲突，可一键插入已有漏洞章节
- **一键导出**：Word（docx）与 PDF（Gotenberg 引擎）版式一致；目录以 TOC 域承载，打开文档自动刷新；导出走任务队列，支持重复导出检测与导出历史
- **报告测试目标自动解析**：被测账号、测试周期、参测人员、被测系统 URL 等字段按「工单 → 资产」链路自动带出

### 专项工单

- **测试计划（渗透测试工单）**：工单编号、被测系统、测试类型、人天统计，关联漏洞与报告；被测系统 URL 自动带出资产地址
- **远程测试 / 专项行动 / 漏扫基线工单**：通报处置、专项行动公文、主机/Web/基线扫描类工单独立流转，与测试计划平级管理

### 态势与管理

- **安全态势 Dashboard**：漏洞趋势、等级/状态/类型分布、修复率等 ECharts 可视化
- **RBAC 权限**：JWT（access/refresh）认证，refresh token 空闲滑动过期；角色-权限点模型，权限目录化管理，前端菜单/按钮级控制
- **通知渠道**：企业微信/钉钉 webhook + SMTP 邮件，漏洞创建、工单认领、状态流转、复测完成四类事件可订阅
- **开放 API**：个人访问令牌（PAT，明文仅显示一次）+ 开放接口（漏洞/态势只读，渗透测试工单与漏扫基线工单查询/创建/更新），按令牌限流；使用指南见 [docs/OPEN_API_GUIDE.md](docs/OPEN_API_GUIDE.md)（访问令牌页内亦可查阅）
- **审计日志**：登录成败（IP/UA）与敏感操作统一记录，可查询追溯

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · Alembic |
| 数据库/队列 | PostgreSQL 16（本地开发 SQLite）· Redis · arq 异步任务队列 |
| 前端 | Vue 3 · TypeScript · Vite · Pinia · Element Plus · TailwindCSS · ECharts · TipTap 2 |
| 文档处理 | python-docx（解析）· htmldocx + pygments（导出）· Gotenberg（PDF 转换） |
| 部署 | Docker Compose（api / worker / frontend / postgres / redis / gotenberg） |

## 快速部署（Docker Compose）

前置：服务器已安装 Docker 与 Docker Compose 插件。

1. 准备环境变量（`.env` 已被 `.gitignore` 忽略，切勿入库）：

   ```bash
   cp .env.example .env
   # 编辑 .env，至少填写：
   #   VP_SECRET_KEY     —— JWT 签名密钥，>=32 位强随机：openssl rand -hex 32
   #   POSTGRES_PASSWORD —— 数据库口令
   ```

   > 两项均有强校验，未设置会拒绝启动。

2. 一键启动：

   ```bash
   docker compose up -d --build
   ```

   数据库表结构、内置角色/字典、admin 账号均自动创建，无需手工初始化。

3. 获取初始 admin 口令（`.env` 未设 `VP_INITIAL_ADMIN_PASSWORD` 时随机生成，仅打印一次，且首次登录强制改密）：

   ```bash
   docker compose logs api | grep -i "初始密码"
   ```

4. 访问：

   - 前端入口：http://localhost:27012 （可在 `docker-compose.yml` 的 `ports` 中修改映射）
   - 前端 nginx 已将 `/api` 同源反代到后端，通常无需对外暴露 8000 端口，也无需额外配置 CORS
   - API 文档仅在调试模式（`VP_DEBUG=1`）下开放：`/api/docs`

> **安全提醒**：生产环境务必保持 `VP_DEBUG` 关闭、修改强随机 `VP_SECRET_KEY` 与数据库口令；显式设置 `VP_INITIAL_ADMIN_PASSWORD` 时首次登录后也应尽快修改 admin 密码。

**版本升级 / 备份 / 迁移**：分别使用 `bash scripts/upgrade.sh`（备份 → 拉代码 → 重建镜像 → 迁移数据库 → 重启）、`bash scripts/backup.sh`、`bash scripts/restore.sh backups/<时间戳>`；详细步骤与排障见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 本地开发

一键脚本（自动创建虚拟环境、安装依赖；SQLite + 免队列模式，无需 Postgres/Redis；固定内置账号 `admin / admin123`）：

```bash
# Windows
powershell -ExecutionPolicy Bypass -File .\dev.ps1

# Linux / macOS
bash dev.sh
```

启动后访问 http://localhost:27014（服务绑定 0.0.0.0，可通过 http://<主机IP>:27014 外部访问），API 文档 http://localhost:27014/api/docs。Ctrl+C 一并停止前后端。可用 `FRONTEND_PORT` / `BACKEND_PORT` 环境变量（或 dev.ps1 的 `-FrontendPort` / `-BackendPort` 参数）覆盖默认端口 27014 / 27015。

<details>
<summary>手动步骤</summary>

后端（可免 Postgres/Redis 依赖）：

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
set VP_DATABASE_URL=sqlite+aiosqlite:///./dev.db
set VP_DISABLE_QUEUE=1
set VP_DEBUG=1
set VP_INITIAL_ADMIN_PASSWORD=admin123
.venv/Scripts/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 27015
```

前端（包管理统一使用 pnpm）：

```bash
cd frontend
pnpm install
pnpm run dev   # http://localhost:27014，代理 /api 与 /storage 到 27015
```

</details>

运行测试：

```bash
cd backend
.venv/Scripts/python -m pytest          # 后端 pytest

cd frontend
pnpm test                               # 前端 vitest
```

## PDF 转换服务（Gotenberg）

`VP_GOTENBERG_URL` 指定 DOCX→PDF 转换服务地址，供「报告 PDF 导出」与「导入原件在线预览」使用（后端默认 `http://localhost:3000`，所有配置项统一 `VP_` 前缀，可写入 `.env` 或以环境变量注入）。

| 环境 | 配置方式 |
| --- | --- |
| Docker Compose | 已内置 `gotenberg/gotenberg:8` 服务并注入地址，开箱即用 |
| 本地开发 | 可选：`docker run --rm -p 3000:3000 gotenberg/gotenberg:8`（默认值即指向此地址） |

未部署 Gotenberg 时仅 PDF 预览/导出返回 502 并提示「转换服务不可用」，其余功能不受影响。生产建议将其置于内网、不对外暴露 3000 端口。

## 目录结构

```
├── backend/
│   ├── app/
│   │   ├── api/v1/        # 路由：auth / users / vulns / assets / reports / imports / dashboard /
│   │   │                  #   knowledge / remote_testing / testing_plan / spring_action / nonpen /
│   │   │                  #   audit / notify / pats / open_api / misc
│   │   ├── core/          # 配置、安全、依赖注入、分页排序、聚合筛选、限流、消毒、时区、xlsx
│   │   ├── models/        # SQLAlchemy 模型
│   │   ├── schemas/       # Pydantic 模型包（按域拆分，__init__.py 统一重导出）
│   │   ├── services/      # 状态机、docx 解析、导入入库、报告构建、导出、态势聚合、审计、通知
│   │   ├── constants.py   # 全部枚举/字典与展示色值唯一来源（经 /meta 下发前端）
│   │   └── workers/       # arq 后台任务（解析、报告导出、通知分发）
│   ├── alembic/           # 数据库迁移
│   ├── scripts/           # 旧数据迁移、数据库纳管、种子数据等运维脚本
│   └── tests/             # pytest 测试
├── frontend/
│   └── src/{api, stores, router, views, components, composables, utils, layouts}
├── docs/                  # DEPLOY（部署运维）/ RELEASE（版本记录）/ ROADMAP（演进路线）
├── scripts/               # upgrade.sh / backup.sh / restore.sh / migrate.sh 等部署脚本
├── dev.ps1 / dev.sh       # 一键本地开发脚本
└── docker-compose.yml
```

## 旧数据迁移

从旧版 insight2（MySQL）迁移数据：

```bash
python backend/scripts/migrate_from_insight2.py --help
```

明文密码不会被迁移，旧用户首次登录将被强制重置密码。

## 功能规划与版本

- 路线与规划：[docs/ROADMAP.md](docs/ROADMAP.md)
- 版本号遵循语义化版本（SemVer），历次更新记录见 [docs/RELEASE.md](docs/RELEASE.md)（唯一版本真相源），当前版本 **2.6.0**

## License

仅供学习与内部安全管理使用。
