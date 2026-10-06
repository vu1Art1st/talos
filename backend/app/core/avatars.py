"""预置头像的资源定位与 URL 生成（唯一出口）。

预置头像与用户上传头像共用 `/storage/...` 前缀，但走不同的路由：

- 上传头像：`/storage/uploads/images/<32 hex>.webp`，内容随用户变化，服务前要查引用与数据范围；
- 预置头像：`/storage/avatars/<id>.webp`，是随镜像分发的静态资源，只按白名单命中文件。

`avatar` 字段的三种取值形态在此收敛：

- `""`：无头像，前端回落为首字母色块；
- `"uploads/images/<name>"`：用户上传；
- `"preset:<id>"`：预置，`<id>` 必须是 `app.constants.AVATAR_PRESETS` 的键。
"""
import re
from pathlib import Path

from app.constants import AVATAR_PRESETS

# 预置头像静态资源目录：app/assets/avatars/<id>.webp
AVATAR_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "avatars"

PRESET_PREFIX = "preset:"
PRESET_URL_PREFIX = "/storage/avatars/"

# id 形如 `zzz/3.2/01`：分段与长度都受限，配合 AVATAR_PRESETS 白名单双重校验
_PRESET_ID_RE = re.compile(r"^[a-z0-9]{1,16}/[0-9]{1,2}\.[0-9]{1,2}/[0-9]{2}$")


def preset_id(avatar: str) -> str:
    """从 `preset:<id>` 取出 id；非预置形态返回空串。"""
    if not avatar.startswith(PRESET_PREFIX):
        return ""
    return avatar[len(PRESET_PREFIX):]


def is_preset_id(value: str) -> bool:
    """是否为合法预置 id（白名单命中且形态受限）。"""
    return value in AVATAR_PRESETS and bool(_PRESET_ID_RE.match(value))


def preset_url(value: str) -> str:
    """预置 id -> 前端 URL；未命中白名单返回空串（前端回落首字母）。"""
    return f"{PRESET_URL_PREFIX}{value}.webp" if is_preset_id(value) else ""


def avatar_url(avatar: str) -> str:
    """`avatar` 字段 -> 前端可直接使用的 URL（用户上传与预置统一出口）。"""
    if avatar.startswith("uploads/"):
        return f"/storage/{avatar}"
    return preset_url(preset_id(avatar))


def preset_file(value: str) -> Path | None:
    """预置 id -> 静态资源绝对路径；不在白名单或文件缺失一律返回 None。

    路径只由白名单里的 id 拼出，不接受任何请求侧的自由路径，因此不存在越界读取面。
    """
    if not is_preset_id(value):
        return None
    path = AVATAR_ASSET_DIR / f"{value}.webp"
    return path if path.is_file() else None
