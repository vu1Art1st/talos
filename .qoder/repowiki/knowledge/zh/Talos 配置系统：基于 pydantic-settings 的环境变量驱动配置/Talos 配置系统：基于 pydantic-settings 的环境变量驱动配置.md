---
kind: configuration_system
name: Talos 配置系统：基于 pydantic-settings 的环境变量驱动配置
category: configuration_system
scope:
    - '**'
source_files:
    - backend/app/core/config.py
    - backend/app/main.py
    - backend/app/db.py
    - backend/app/workers/main.py
    - docker-compose.yml
    - backend/requirements.txt
---

## 1. 使用的系统与框架
- 后端使用 pydantic-settings（BaseSettings + SettingsConfigDict）作为统一的配置加载器，支持类型校验、默认值与环境变量覆盖。
- 前端通过 Vite 构建，无独立运行时配置文件，API 地址等由构建期常量或环境变量注入。
- 容器编排通过 docker-compose.yml 集中声明各服务的运行环境变量，统一注入到 API/Worker 进程。

## 2. 核心文件与位置
- backend/app/core/config.py：全局 Settings 模型定义、默认值、.env 加载、VP_ 前缀、缓存单例。
- backend/app/main.py：FastAPI 应用入口，启动时读取 settings 初始化数据库连接池、CORS、静态文件挂载与健康检查。
- backend/app/db.py：依赖 settings.DATABASE_URL 创建异步 SQLAlchemy Engine 与 SessionMaker。
- backend/app/workers/main.py：arq Worker 通过 settings.REDIS_URL 连接 Redis，并复用同一 Settings 实例。
- docker-compose.yml：为 api/worker 服务统一设置 VP_DATABASE_URL、VP_REDIS_URL、VP_GOTENBERG_URL、VP_SECRET_KEY、VP_STORAGE_DIR 等环境变量。
- backend/requirements.txt：声明 pydantic-settings>=2.3 为配置系统的依赖。

## 3. 架构与设计约定
- 单一配置源：所有后端模块通过 from app.core.config import settings 获取全局单例，避免分散的 config 对象。
- 环境变量优先：model_config = SettingsConfigDict(env_prefix="VP_", env_file=".env", extra="ignore") 表明：
  - 所有配置项可通过 VP_ 前缀的环境变量覆盖（如 VP_DATABASE_URL、VP_SECRET_KEY）。
  - 本地开发可放置 .env 文件，按字段名自动映射。
  - 未声明的额外环境变量会被忽略，防止误注入。
- 默认值与类型安全：每个字段都有 Python 默认值（如 DEBUG: bool = False、ACCESS_TOKEN_EXPIRE_MINUTES: int = 120），由 pydantic 在加载时校验类型。
- 懒加载与缓存：get_settings() 使用 @lru_cache 缓存 Settings 实例，确保进程内唯一。
- 存储路径辅助方法：storage_path 属性与 storage_sub(*parts) 方法自动创建目录并返回 Path，被 workers 和 main 中静态文件挂载共用。
- 降级策略：main.py 的 lifespan 中尝试连接 Redis，失败则记录警告并将后台任务降级为进程内执行；DISABLE_QUEUE=True 时可完全禁用 arq。

## 4. 配置分层与环境差异
- 默认值：config.py 字段默认值，本地开发可直接运行，无需额外配置。
- .env 文件：backend/.env（未被 git 跟踪），开发者本地覆盖，如修改数据库密码、调试开关。
- Docker Compose：docker-compose.yml 的 environment，容器化部署时注入生产级配置（数据库、Redis、Gotenberg、Secret Key、存储路径）。
- 运行时环境变量：宿主环境 / CI/CD 平台，最高优先级，可覆盖 .env 与 compose 中的值。

## 5. 关键约束与约定
- 环境变量命名规范：所有配置项必须以 VP_ 为前缀（如 VP_DATABASE_URL、VP_REDIS_URL、VP_GOTENBERG_URL、VP_SECRET_KEY、VP_STORAGE_DIR、VP_DISABLE_QUEUE、VP_SMTP_*）。
- 敏感信息不入库：SECRET_KEY、SMTP 密码等通过环境变量注入，不在代码中硬编码。
- 存储目录自动创建：STORAGE_DIR 指向的路径会在首次访问时自动创建，支持子目录 uploads/imports/{batch_id} 与 exports。
- 调试模式控制日志：DEBUG=True 时 SQLAlchemy 会打印 SQL 语句（echo=settings.DEBUG）。
- 队列开关：DISABLE_QUEUE=True 时跳过 arq 连接，所有任务在 API 进程内同步执行，适用于测试或单机部署。
- 版本管理：APP_VERSION 与 docs/RELEASE.md、frontend/package.json 需同步更新，体现配置与文档的一致性约定。

## 6. 前端配置
- 前端为纯静态 SPA，通过 Vite 构建后由 Nginx 托管，无运行时配置文件。
- API 基础地址由构建期常量或代理配置决定（见 frontend/src/api/client.ts 与 nginx.conf），不依赖运行时环境变量。

## 7. 总结
该项目的配置系统以 pydantic-settings 为核心，采用“默认值 → .env → 环境变量”的分层覆盖机制，配合 docker-compose 统一管理多服务依赖的配置注入。所有配置项具备强类型与默认值，敏感信息通过环境变量注入，整体设计简洁、可移植性强，适合本地开发与容器化部署的统一体验。