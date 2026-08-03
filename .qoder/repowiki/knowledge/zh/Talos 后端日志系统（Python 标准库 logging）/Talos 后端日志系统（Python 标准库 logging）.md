---
kind: logging_system
name: Talos 后端日志系统（Python 标准库 logging）
category: logging_system
scope:
    - '**'
source_files:
    - backend/app/main.py
    - backend/app/workers/dispatch.py
    - backend/alembic/env.py
    - backend/requirements.txt
---

Talos 后端的日志系统基于 Python 标准库 `logging`，未引入第三方日志框架（如 structlog、loguru、logzero）。当前实现较为简单，主要特点如下：

1. **框架与初始化**：各模块通过 `logging.getLogger(__name__)` 获取独立 logger 实例，未在应用启动时统一配置 handler/formatter。Alembic 迁移脚本通过 `logging.config.fileConfig` 加载配置文件，但项目根目录未见独立的 logging 配置文件。
2. **使用范围**：目前仅在 `app/main.py` 和 `app/workers/dispatch.py` 中实际使用 `logger.warning()` 记录 Redis/arq 连接失败等降级场景；其他业务模块尚未集成结构化日志输出。
3. **日志级别策略**：仅观察到 `warning` 级别的使用，用于记录可恢复的异常（Redis 不可用、arq 投递失败），未建立统一的 debug/info/error/critical 分级规范。
4. **输出格式**：未配置自定义 formatter，默认使用 Python logging 的简单文本格式，无结构化字段（如 request_id、user_id、trace_id）。
5. **前端日志**：前端代码未发现专门的日志框架或集中式日志收集，仅依赖浏览器控制台输出。
6. **依赖关系**：`requirements.txt` 中未包含任何第三方日志库，完全依赖 Python 标准库。

整体而言，该项目的日志系统处于最简实现状态，尚未形成统一的日志规范、结构化输出或集中式收集方案。