"""storage 相对路径的安全解析与校验（安全审计 TALOS-2026-001/002 修复）。

背景：春耕行动「原始报告附件」与远程检测「申诉附件」的存储路径历史上由客户端提交并直接
落库，下载/删除时以 `settings.storage_path / 字段` 裸拼接，导致两类越界：
- `../` 路径穿越与绝对路径（`/etc/passwd`、`C:\\Windows\\win.ini`）可读取进程可访问的任意文件；
- 同一路径在替换附件/删除记录时被 `unlink`，可删除任意文件。

约定（新代码强制）：
- 写入侧用 `require_attachment_path()`（路由层校验，非法值 400）；
- 读取/删除侧用 `resolve_storage_path()`（越界或目标不存在一律 404，不区分原因以免泄露目录结构）；
- 禁止再出现 `settings.storage_path / <请求体或数据库字段>` 的裸拼接
  （结构守卫见 `tests/test_source_guard.py`）。

注意：写入校验**不做成 pydantic 字段类型**——`RemoteTestingOut` / `SpringActionOut` 继承对应
写入模型，若在写入模型上挂校验器，存量脏数据会在**输出序列化**时被判非法（列表/详情直接 500，
本仓库已有同类踩坑记录）。故校验放在路由层显式调用，输出模型不受影响。
"""
import re
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings

# 附件相对路径白名单：`uploads/<子目录>/<32 位十六进制文件名>.<扩展名>`
# 与 services/upload_store.save_upload 的产物严格一致（服务端 uuid4 命名 + 小写扩展名）。
# 该格式下客户端不可能构造出目录穿越、绝对路径或指向 storage 之外的文件。
ATTACHMENT_PATH_RE = re.compile(r"^uploads/[a-z][a-z0-9_]*/[0-9a-f]{32}\.[a-z0-9]{1,8}$")

_ILLEGAL_PATH_MSG = "附件路径非法：请通过本系统上传附件（不支持手工填写或外部路径）"


def is_attachment_path(rel: str | None, *, subdir: str = "") -> bool:
    """是否为系统上传接口生成的标准附件相对路径（subdir 非空时同时限定子目录）。"""
    text = rel or ""
    if not ATTACHMENT_PATH_RE.match(text):
        return False
    return not subdir or text.startswith(f"uploads/{subdir}/")


def require_attachment_path(rel: str, *, subdir: str = "") -> str:
    """路由层写入校验：非标准附件路径抛 400；空串合法（表示未上传附件）。"""
    if not rel:
        return ""
    if not is_attachment_path(rel, subdir=subdir):
        raise HTTPException(400, _ILLEGAL_PATH_MSG)
    return rel


def _unsafe_relative(rel: str) -> bool:
    """相对路径是否含越界特征：空值、NUL、绝对路径（POSIX/Windows/UNC）、`..` 段。"""
    if not rel or "\x00" in rel:
        return True
    # 统一分隔符后再判断：Windows 客户端可能提交反斜杠路径
    normalized = rel.replace("\\", "/")
    if normalized.startswith("/"):  # POSIX 绝对路径 / UNC（//server/share）
        return True
    if re.match(r"^[A-Za-z]:", normalized):  # Windows 盘符
        return True
    return ".." in normalized.split("/")


def resolve_storage_path(rel: str, *, not_found_detail: str = "附件已被清理") -> Path:
    """把 storage 相对路径解析为 storage 根目录内的绝对文件路径。

    拒绝：空值 / NUL / 绝对路径 / `..` 段 / 解析后越出 storage 根（含符号链接指向外部）/
    目标不存在或不是文件。以上情况统一 404 且文案一致，避免把内部目录结构透给调用方。
    """
    rel = (rel or "").strip()
    if _unsafe_relative(rel):
        raise HTTPException(404, not_found_detail)
    root = settings.storage_path.resolve()
    try:
        candidate = (root / rel).resolve()
    except OSError as exc:  # 路径过长、非法字符等
        raise HTTPException(404, not_found_detail) from exc
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise HTTPException(404, not_found_detail)
    return candidate
