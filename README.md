# Talos 漏洞管理平台

Talos（塔罗斯）取名自希腊神话中守卫克里特岛的青铜巨人——刀枪不入却因脚踝上唯一的弱点而倒下，恰如安全工作：找到并修复那一个致命漏洞。

现代化漏洞全生命周期管理平台，基于 FastAPI + Vue 3 全量重构（前身为洞察2.0 / insight2 的现代化重写版本）。

## 功能特性

- **漏洞全生命周期管理**：待审核 → 确认 → 修复中 → 复测 → 完成 的状态机流转，全程操作日志审计
- **Word 文档导入**：按固定模板上传 Word 报告，后台自动解析生成漏洞记录（含图片提取），预览确认后批量入库
- **在线报告编辑**：TipTap 富文本编辑器，支持表格/图片/代码块，自动保存 + 乐观锁防冲突，可一键插入已有漏洞章节
- **报告导出**：一键导出 Word（docx）与 PDF（Gotenberg 引擎），版式一致；目录以 TOC 域承载（`updateFields` 打开自动刷新），导出后前端提示用户手动更新域或打开 WPS/Word 自动更新
- **安全态势 Dashboard**：漏洞趋势、等级/状态/类型分布、修复率等 ECharts 可视化
- **RBAC 权限**：JWT（access/refresh）认证，角色-权限点模型，前端菜单/按钮级控制
- **应用与资产管理**：应用、资产台账与漏洞关联

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · Alembic |
| 数据库/队列 | PostgreSQL 16 · Redis · arq 异步任务队列 |
| 前端 | Vue 3 · TypeScript · Vite · Pinia · Element Plus · TailwindCSS · ECharts · TipTap 2 |
| 文档处理 | python-docx（解析）· htmldocx + pygments（导出）· Gotenberg（PDF 转换） |
| 部署 | Docker Compose（api / worker / frontend / postgres / redis / gotenberg） |

## 目录结构

```
├── backend/
│   ├── app/
│   │   ├── api/v1/        # auth, users, apps, assets, vulns, reports, imports, dashboard
│   │   ├── core/          # 配置、安全、依赖注入
│   │   ├── models/        # SQLAlchemy 模型
│   │   ├── schemas/       # Pydantic 模型
│   │   ├── services/      # 状态机、docx 解析、报告构建、导出
│   │   └── workers/       # arq 后台任务
│   ├── alembic/           # 数据库迁移
│   ├── scripts/           # migrate_from_insight2.py 旧数据迁移
│   └── tests/             # pytest 集成测试
├── frontend/
│   └── src/{api, stores, router, views, components, layouts}
├── dev.ps1 / dev.sh       # 一键本地开发脚本
└── docker-compose.yml
```

## 快速部署（Docker Compose）

```bash
docker compose up -d
```

- 前端入口：http://localhost （80 端口）
- API 文档：http://localhost:8000/api/docs
- 默认账号：`admin` / `admin123`

> **安全提醒**：生产部署前请务必修改 `docker-compose.yml` 中的 `VP_SECRET_KEY` 与数据库口令，并在首次登录后立即修改 admin 密码。

## PDF 转换服务（Gotenberg）配置

`VP_GOTENBERG_URL` 指定 DOCX→PDF 转换服务地址，供「报告 PDF 导出」与「导入原件在线预览」使用。后端默认值 `http://localhost:3000`（见 `backend/app/core/config.py`，所有配置项统一使用 `VP_` 前缀，可写入 `.env` 或以环境变量注入）。

| 环境 | 配置方式 |
| --- | --- |
| 生产（Docker Compose） | `docker-compose.yml` 已内置 `gotenberg/gotenberg:8` 服务，并为 api / worker 注入 `VP_GOTENBERG_URL: http://gotenberg:3000`，开箱即用，无需额外配置 |
| 本地开发 | 可选：`docker run --rm -p 3000:3000 gotenberg/gotenberg:8`，再设 `VP_GOTENBERG_URL=http://localhost:3000`（默认值即为此，通常无需显式设置） |

未部署 Gotenberg 时，仅 PDF 预览/导出会返回 502 并在前端提示「转换服务不可用」，漏洞、报告、资产、导入等其它功能均不受影响。

**最佳实践**：生产环境将 Gotenberg 置于内网、不对外暴露 3000 端口；转换较大文档时可调整 `--api-timeout`（`docker-compose.yml` 已设为 120s）。

## 本地开发

推荐一键脚本（自动创建虚拟环境、安装依赖，SQLite + 免队列模式，无需 Postgres/Redis）：

```bash
# Windows
powershell -ExecutionPolicy Bypass -File .\dev.ps1

# Linux / macOS
bash dev.sh
```

启动后访问 http://localhost:27014（服务绑定 0.0.0.0，也可通过 http://<服务器IP>:27014 外部访问，需放行该端口），默认账号 `admin` / `admin123`，Ctrl+C 一并停止前后端。可用 `FRONTEND_PORT` / `BACKEND_PORT` 环境变量（或 dev.ps1 的 `-FrontendPort` / `-BackendPort` 参数）覆盖默认端口 27014 / 27015。

<details>
<summary>手动步骤</summary>

后端（可免 Postgres/Redis 依赖）：

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
set VP_DATABASE_URL=sqlite+aiosqlite:///./dev.db
set VP_DISABLE_QUEUE=1
.venv/Scripts/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 27015
```

前端：

```bash
cd frontend
npm install
npm run dev   # http://localhost:27014，代理 /api 与 /storage 到 27015
```

</details>

运行测试：

```bash
cd backend
.venv/Scripts/python -m pytest
```

## 功能规划

后续功能设计详见 [docs/ROADMAP.md](docs/ROADMAP.md)。

## 版本发布

版本号遵循语义化版本 `x.y.z` 管理，历次更新记录详见 [docs/RELEASE.md](docs/RELEASE.md)。

## 旧数据迁移

从旧版 insight2（MySQL）迁移数据：

```bash
python backend/scripts/migrate_from_insight2.py --help
```

明文密码不会被迁移，旧用户首次登录将被强制重置密码。

## License

仅供学习与内部安全管理使用。
