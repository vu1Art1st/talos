---
kind: configuration_system
name: Talos 配置系统：基于 pydantic-settings 的环境变量驱动配置
category: configuration_system
scope:
    - '**'
source_files:
    - backend/app/core/config.py
    - backend/app/main.py
    - docker-compose.yml
    - backend/alembic.ini
    - backend/alembic/env.py
    - frontend/vite.config.ts
    - frontend/src/api/client.ts
    - backend/app/workers/main.py
    - backend/app/workers/dispatch.py
---

## 1. 使用的系统与框架
- 后端配置：使用 **pydantic-settings** 的 `BaseSettings`，通过环境变量注入与 `.env` 文件加载。
- 构建/部署配置：Docker Compose 统一编排所有服务（PostgreSQL、Redis、Gotenberg、API、Worker、前端 Nginx），并通过 `environment` 字段向 API/Worker 注入配置。
- 前端开发配置：Vite 的 `vite.config.ts` 中定义开发代理与端口；生产环境由 Nginx 反向代理到后端 `/api` 和 `/storage`。
- 数据库迁移：Alembic 通过 `alembic.ini` + `alembic/env.py` 从同一 `settings.DATABASE_URL` 读取连接串。

## 2. 核心文件与位置
- `backend/app/core/config.py`：全局 Settings 模型与 `get_settings()` 单例缓存。
- `backend/app/main.py`：FastAPI 应用入口，挂载路由、静态目录、健康检查，并在 lifespan 中初始化 arq 连接池。
- `docker-compose.yml`：服务编排与环境变量注入（全部以 `VP_` 前缀）。
- `backend/alembic.ini` 与 `backend/alembic/env.py`：迁移脚本读取 `VP_DATABASE_URL`。
- `frontend/vite.config.ts`：开发服务器代理配置。
- `frontend/src/api/client.ts`：前端 Axios 实例 baseURL 为 `/api/v1`，依赖 Nginx/代理转发。
- `backend/app/workers/main.py`：arq Worker 设置，复用 `settings.REDIS_URL`。
- `backend/app/workers/dispatch.py`：任务分发器，在 Redis 不可用时降级为进程内执行。

## 3. 架构与设计决策
- **单一配置源**：所有运行时配置集中在 `app.core.config.Settings`，通过 `model_config = SettingsConfigDict(env_prefix="VP_", env_file=".env", extra="ignore")` 实现。
- **环境变量覆盖**：每个配置项均可被 `VP_` 前缀的环境变量覆盖（如 `VP_DATABASE_URL`、`VP_REDIS_URL`、`VP_GOTENBERG_URL`、`VP_SECRET_KEY`、`VP_STORAGE_DIR`、`VP_DISABLE_QUEUE` 等）。
- **默认值策略**：Settings 提供合理的本地开发默认值（localhost:5432、redis://localhost:6379/0、http://localhost:3000），便于单机快速启动。
- **懒加载与缓存**：`get_settings()` 使用 `@lru_cache` 保证全局唯一实例，避免重复解析。
- **路径安全构造**：`storage_path` 与 `storage_sub` 自动创建目录并返回 `Path` 对象，确保存储目录存在。
- **渐进式降级**：当 `DISABLE_QUEUE=True` 或 Redis 不可用时，后台任务自动降级为 FastAPI 进程内异步执行，提升开发/测试体验。
- **前后端分离但共享配置约定**：前端通过 Vite/Nginx 将 `/api` 和 `/storage` 请求代理到后端 8000 端口，无需硬编码后端地址。

## 4. 约定与约束
- **环境变量命名规范**：所有后端配置必须使用 `VP_` 前缀（由 `env_prefix="VP_"` 强制）。
- **敏感信息处理**：`SECRET_KEY`、SMTP 密码等敏感字段通过环境变量注入，不在代码中硬编码。
- **存储路径约定**：`STORAGE_DIR` 默认为 `storage`，实际路径由 `settings.storage_path` 返回，子目录通过 `storage_sub` 生成。
- **模板路径约定**：`REPORT_TEMPLATE` 默认指向 `backend/app/templates/report_template.docx`，可通过环境变量覆盖。
- **迁移配置同步**：Alembic 的 `sqlalchemy.url` 由 `env.py` 动态设置为 `settings.DATABASE_URL`，避免配置文件分裂。
- **Worker 与 API 共享配置**：Worker 通过相同 `WorkerSettings.redis_settings` 使用 `settings.REDIS_URL`，确保队列一致性。
- **开发/生产环境切换**：通过 `DEBUG`、`DISABLE_QUEUE` 等布尔开关控制行为差异。
- **前端代理约定**：开发时 Vite 将 `/api` 和 `/storage` 代理到 `http://localhost:8000`，生产环境由 Nginx 统一转发。