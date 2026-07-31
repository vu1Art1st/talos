from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 默认占位密钥集合：生产环境（DEBUG=False）不允许使用，防止 JWT 令牌伪造
_INSECURE_KEYS = {"please-change-me-in-production", "change-me-to-a-long-random-string"}


class Settings(BaseSettings):
    """全局配置，全部支持环境变量覆盖（前缀 VP_）。"""

    APP_NAME: str = "Talos"
    # 版本号遵循语义化版本 x.y.z，发布时同步更新 docs/RELEASE.md 与 frontend/package.json
    APP_VERSION: str = "0.7.0"
    DEBUG: bool = False

    SECRET_KEY: str = "please-change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 内置 admin 初始口令：留空则首次启动随机生成并打印到日志（仅显示一次）
    INITIAL_ADMIN_PASSWORD: str = ""
    # 登录防爆破：同一用户名+IP 在窗口期内允许的最大失败次数与锁定窗口（秒）
    LOGIN_MAX_FAILURES: int = 10
    LOGIN_LOCK_SECONDS: int = 900

    # 允许携带凭证的跨域来源白名单（前端部署地址），生产环境务必按实际域名收窄
    CORS_ORIGINS: list[str] = ["http://localhost", "http://localhost:27012"]

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

    @model_validator(mode="after")
    def _check_secret(self) -> "Settings":
        # 生产环境拒绝弱密钥：默认占位符或长度不足 32 字符，避免令牌可被伪造
        if not self.DEBUG and (self.SECRET_KEY in _INSECURE_KEYS or len(self.SECRET_KEY) < 32):
            raise ValueError(
                "VP_SECRET_KEY 必须为 >=32 字符的随机值且非默认占位符（可用 `openssl rand -hex 32` 生成）"
            )
        return self

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
