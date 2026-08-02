---
kind: logging_system
name: 基于 Python 标准库 logging 的轻量级日志系统
category: logging_system
scope:
    - '**'
source_files:
    - backend/app/main.py
    - backend/app/workers/dispatch.py
    - backend/alembic/env.py
    - backend/Dockerfile
---

## 系统与框架
后端使用 Python 标准库 `logging` 模块作为唯一日志实现，未引入第三方日志框架（如 loguru、structlog）。通过 `logging.getLogger(__name__)` 在每个模块创建独立 logger，遵循 Python 标准命名空间约定。

## 关键文件与位置
- `backend/app/main.py`：应用入口，定义全局 logger 并记录 Redis/队列连接状态
- `backend/app/workers/dispatch.py`：异步任务分发器，记录 arq 队列投递失败降级逻辑
- `backend/alembic/env.py`：迁移脚本通过 `logging.config.fileConfig` 加载配置文件
- `backend/Dockerfile`：通过 uvicorn 启动，默认使用 uvicorn 内置日志配置

## 架构与约定
1. **模块级 Logger**：每个需要日志的模块通过 `logger = logging.getLogger(__name__)` 获取 logger，保证日志来源可追溯
2. **日志级别策略**：仅使用 `warning` 级别记录运行时异常（Redis 连接失败、arq 投递失败），未实现完整的 debug/info/error 分级体系
3. **无集中配置**：未发现 `logging.conf`、`LOGGING` 字典或 `dictConfig` 调用，日志格式和输出目标依赖 uvicorn 默认配置
4. **结构化字段缺失**：日志输出为简单字符串拼接，未采用 JSON 结构化日志格式
5. **统一入口**：所有业务逻辑通过 FastAPI 路由暴露，日志集中在应用层而非中间件层

## 约束与规范
- 当前未定义统一的日志格式规范，不同模块的日志输出格式可能不一致
- 未实现日志轮转、文件输出或外部日志收集（如 ELK、Loki）
- Alembic 迁移脚本预留了 `fileConfig` 接口但未实际使用配置文件
- 生产环境日志输出完全依赖 uvicorn 默认行为，缺乏可观测性增强