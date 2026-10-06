"""预置头像目录与头像规范化的护栏（静态资源白名单 + 透明通道）。"""
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.constants import AVATAR_PRESETS
from app.core.avatars import AVATAR_ASSET_DIR, avatar_url, is_preset_id, preset_file, preset_url
from app.core.images import AVATAR_SIZE, normalize_avatar


def _png(*, alpha: bool, size: tuple[int, int] = (1000, 1000)) -> bytes:
    """造一张测试图：alpha=True 时四角全透明、中心一块不透明。"""
    if alpha:
        image = Image.new("RGBA", size, (10, 20, 30, 0))
        ImageDraw.Draw(image).rectangle((400, 400, 600, 600), fill=(200, 30, 40, 255))
    else:
        image = Image.new("RGB", size, (200, 30, 40))
    buf = BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def test_preset_catalog_matches_shipped_assets():
    """目录与随镜像分发的静态资源一一对应，避免改名后线上 404。"""
    missing = [preset for preset in AVATAR_PRESETS if preset_file(preset) is None]
    assert not missing, f"AVATAR_PRESETS 里这些 id 找不到资源文件：{missing[:5]}"
    assert AVATAR_ASSET_DIR.is_dir()
    assert len(AVATAR_PRESETS) >= 1


def test_preset_id_rejects_traversal_and_unknown_ids():
    assert preset_file("zzz/../../etc/passwd") is None
    assert preset_file("zzz/1.3/001") is None
    assert preset_file("zzz/9.9/01") is None
    assert preset_file("") is None
    assert not is_preset_id("../secret")


def test_avatar_url_maps_all_three_shapes():
    first = next(iter(AVATAR_PRESETS))
    assert avatar_url(f"preset:{first}") == f"/storage/avatars/{first}.webp"
    assert avatar_url("uploads/images/abc.webp") == "/storage/uploads/images/abc.webp"
    assert avatar_url("") == ""
    # 已下线的旧预设解析不出 URL，前端回落首字母
    assert avatar_url("preset:07") == ""
    assert preset_url("07") == ""


def test_normalize_avatar_keeps_transparency():
    with Image.open(BytesIO(normalize_avatar(_png(alpha=True)))) as image:
        assert image.size == (AVATAR_SIZE, AVATAR_SIZE)
        assert image.mode == "RGBA"
        assert image.getpixel((2, 2))[3] == 0
        assert image.getpixel((AVATAR_SIZE // 2, AVATAR_SIZE // 2))[3] == 255


def test_normalize_avatar_can_flatten_onto_white():
    out = normalize_avatar(_png(alpha=True), background=(255, 255, 255))
    with Image.open(BytesIO(out)) as image:
        assert image.mode == "RGB"
        assert image.getpixel((2, 2)) == (255, 255, 255)


def test_normalize_avatar_opaque_source_stays_rgb():
    with Image.open(BytesIO(normalize_avatar(_png(alpha=False)))) as image:
        assert image.mode == "RGB"


def test_normalize_avatar_rejects_non_image():
    with pytest.raises(ValueError):
        normalize_avatar(b"definitely not an image")
