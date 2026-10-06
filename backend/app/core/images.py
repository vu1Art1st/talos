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


def _has_transparency(image: Image.Image) -> bool:
    """图片是否真的用了透明通道（P 模式还要看 transparency 信息）。"""
    if image.mode in ("RGBA", "LA"):
        return image.getchannel("A").getextrema()[0] < 255
    if image.mode == "P":
        return "transparency" in image.info
    return False


def normalize_avatar(data: bytes, *, background: tuple[int, int, int] | None = None) -> bytes:
    """校验、纠正方向、居中裁剪并输出 256x256 WebP。"""
    if len(data) > AVATAR_MAX_BYTES:
        raise ValueError("头像大小不能超过 2MB")
    if not is_allowed_image(data):
        raise ValueError("文件内容不是有效的图片")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width > AVATAR_MAX_SIDE or source.height > AVATAR_MAX_SIDE:
                raise ValueError("头像尺寸不能超过 4096x4096")
            image = ImageOps.exif_transpose(source)
            keep_alpha = _has_transparency(image)
            image = image.convert("RGBA") if keep_alpha else image.convert("RGB")
            side = min(image.width, image.height)
            left = (image.width - side) // 2
            top = (image.height - side) // 2
            image = image.crop((left, top, left + side, top + side))
            if keep_alpha:
                # 透明像素的 RGB 是任意值（官方素材里白/黑混杂），先按预乘 alpha 缩放再还原，
                # 否则插值会把那些颜色带进边缘，形成黑边/白边。
                image = image.convert("RGBa").resize(
                    (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS
                ).convert("RGBA")
                if background is not None:
                    canvas = Image.new("RGBA", image.size, (*background, 255))
                    image = Image.alpha_composite(canvas, image).convert("RGB")
            else:
                image = image.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="WEBP", quality=88, method=6)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("文件内容不是有效的图片") from exc
