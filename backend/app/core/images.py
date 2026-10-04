"""图片上传的共享校验与头像规范化。"""
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
AVATAR_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_MAX_SIDE = 4096
AVATAR_SIZE = 256


def is_allowed_image(data: bytes) -> bool:
    """校验图片文件头魔术字节，防止伪造扩展名的非图片文件入库。"""
    return (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        or data.startswith(b"\xff\xd8\xff")
        or data[:6] in (b"GIF87a", b"GIF89a")
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
    )


def normalize_avatar(data: bytes) -> bytes:
    """校验、纠正方向、居中裁剪并输出 256x256 WebP。"""
    if len(data) > AVATAR_MAX_BYTES:
        raise ValueError("头像大小不能超过 2MB")
    if not is_allowed_image(data):
        raise ValueError("文件内容不是有效的图片")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width > AVATAR_MAX_SIDE or source.height > AVATAR_MAX_SIDE:
                raise ValueError("头像尺寸不能超过 4096x4096")
            image = ImageOps.exif_transpose(source).convert("RGB")
            side = min(image.width, image.height)
            left = (image.width - side) // 2
            top = (image.height - side) // 2
            image = image.crop((left, top, left + side, top + side))
            image = image.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="WEBP", quality=88, method=6)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("文件内容不是有效的图片") from exc
