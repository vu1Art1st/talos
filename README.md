# VulnPlatform 漏洞管理平台

现代化漏洞全生命周期管理平台，基于 FastAPI + Vue 3 全量重构（前身为洞察2.0 / insight2 的现代化重写版本）。

## 功能特性

- **漏洞全生命周期管理**：待审核 → 确认 → 修复中 → 复测 → 完成 的状态机流转，全程操作日志审计
- **Word 文档导入**：按固定模板上传 Word 报告，后台自动解析生成漏洞记录（含图片提取），预览确认后批量入库
- **在线报告编辑**：TipTap 富文本编辑器，支持表格/图片/代码块，自动保存 + 乐观锁防冲突，可一键插入已有漏洞章节
- **报告导出**：一键导出 Word（docx）与 PDF（Gotenberg / LibreOffice 引擎），版式一致
- **安全态势 Dashboard**：漏洞趋势、等级/状态/类型分布、修复率等 ECharts 可视化
- **RBAC 权限**：JWT（access/refresh）认证，角色-权限点模型，前端菜单/按钮级控制
- **应用与资产管理**：应用、资产台账与漏洞关联

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · Alembic |
| 数据库/队列 | PostgreSQL 16 · Redis · arq 异步任务队列 |
| 前端 | Vue 3 · TypeScript · Vite · Pinia · Element Plus · TailwindCSS · ECharts · TipTap 2 |
| 文档处理 | python-docx（解析）· htmldocx（导出）· Gotenberg（PDF 转换） |
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

## 本地开发

后端（可免 Postgres/Redis 依赖）：

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
set VP_DATABASE_URL=sqlite+aiosqlite:///./dev.db
set VP_DISABLE_QUEUE=1
.venv/Scripts/python -m uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173，代理 /api 与 /storage 到 8000
```

运行测试：

```bash
cd backend
.venv/Scripts/python -m pytest
```

## 旧数据迁移

从旧版 insight2（MySQL）迁移数据：

```bash
python backend/scripts/migrate_from_insight2.py --help
```

明文密码不会被迁移，旧用户首次登录将被强制重置密码。

## License

仅供学习与内部安全管理使用。
