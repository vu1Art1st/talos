"""账号标识规范化：邮箱统一大小写与首尾空白，供模型写入与查询共用。"""
import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def is_valid_email(value: str) -> bool:
    email = normalize_email(value)
    return bool(email) and len(email) <= 128 and bool(_EMAIL_RE.match(email))
