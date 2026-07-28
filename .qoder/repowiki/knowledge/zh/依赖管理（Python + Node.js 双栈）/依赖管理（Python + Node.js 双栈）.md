---
kind: dependency_management
name: 依赖管理（Python + Node.js 双栈）
category: dependency_management
scope:
    - '**'
source_files:
    - backend/requirements.txt
    - backend/requirements-dev.txt
    - frontend/package.json
    - frontend/package-lock.json
    - backend/Dockerfile
    - frontend/Dockerfile
    - docker-compose.yml
---

本仓库采用前后端分离的双栈依赖管理策略：后端使用 Python pip + requirements.txt，前端使用 npm + package.json + package-lock.json，并通过 Docker Compose 统一编排运行时依赖（PostgreSQL、Redis、Gotenberg）。

**后端依赖管理**
- 包管理器：pip，依赖声明位于 `backend/requirements.txt`，开发依赖位于 `backend/requirements-dev.txt`（通过 `-r requirements.txt` 引用生产依赖）。
- 版本约束：全部使用 `>=` 宽松语义（如 `fastapi>=0.115`、`sqlalchemy[asyncio]>=2.0.30`），未锁定具体版本号，也未生成 `requirements.lock` / `Pipfile.lock`。
- 构建与安装：`backend/Dockerfile` 中通过 `pip install --no-cache-dir -r requirements.txt` 在镜像构建时安装依赖；本地开发通过 `.venv` 虚拟环境运行。
- 无私有源或代理配置，直接连接 PyPI。

**前端依赖管理**
- 包管理器：npm，依赖声明位于 `frontend/package.json`，精确锁文件 `frontend/package-lock.json`（lockfileVersion: 3）已提交至仓库。
- 版本约束：所有依赖均使用 `^` 语义化版本前缀（如 `vue@^3.4.27`、`element-plus@^2.7.5`），允许小版本自动升级。
- 构建与安装：`frontend/Dockerfile` 中通过 `npm install --registry=https://registry.npmmirror.com` 指定国内镜像源加速安装；`package.json` 提供 `dev`、`build`、`preview` 脚本。
- 依赖分类：明确区分 `dependencies`（运行时）与 `devDependencies`（构建期工具如 vite、typescript、tailwindcss）。

**容器化与运行时依赖**
- `docker-compose.yml` 统一管理数据库（postgres:16-alpine）、缓存队列（redis:7-alpine）、文档转换服务（gotenberg/gotenberg:8）以及 api、worker、frontend 三个应用服务。
- 服务间通过环境变量注入连接信息（如 `VP_DATABASE_URL`、`VP_REDIS_URL`、`VP_GOTENBERG_URL`），依赖健康检查确保启动顺序。
- 数据持久化通过命名卷 `pg_data`、`storage_data` 挂载。

**约定与约束**
- 后端不锁定具体版本，便于快速跟进上游更新，但可能带来可重现性风险。
- 前端通过 lockfile 保证构建一致性，且使用国内 npm 镜像提升下载速度。
- 无 vendoring、无私有 PyPI/NPM 仓库配置，所有第三方包均来自公共注册表。