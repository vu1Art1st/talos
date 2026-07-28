from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，全部支持环境变量覆盖（前缀 VP_）。"""

    APP_NAME: str = "Talos"
    # 版本号遵循语义化版本 x.y.z，发布时同步更新 docs/RELEASE.md 与 frontend/package.json
    APP_VERSION: str = "0.4.0"
    DEBUG: bool = False

    SECRET_KEY: str = "please-change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DATABASE_URL: str = "postgresql+asyncpg://vuln:vulnpass@localhost:5432/vulnplatform"
    REDIS_URL: str = "redis://localhost:6379/0"
    # 为 True 时不连接 arq 队列，后台任务在 API 进程内执行（测试/单机部署）
    DISABLE_QUEUE: bool = False

    GOTENBERG_URL: str = "http://localhost:3000"

    # 报告导出 Word 基底模板，默认使用包内模板，可用环境变量指向定制文件
    REPORT_TEMPLATE: str = str(Path(__file__).resolve().parent.parent / "templates" / "report_template.docx")

    STORAGE_DIR: str = "storage"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 25
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = ""

    model_config = SettingsConfigDict(env_prefix="VP_", env_file=".env", extra="ignore")

    @property
    def storage_path(self) -> Path:
        p = Path(self.STORAGE_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def storage_sub(self, *parts: str) -> Path:
        p = self.storage_path.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
