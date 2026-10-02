"""DOCX 解析差分对照（批次 E-2 的等价性验收工具）。

用途：对同一批 `.docx`，把 **legacy 实现**（`app.services.docx_parser`，基于 python-docx）与
候选实现（后续的 `lxml.iterparse` 自写 reader）的解析结果逐字段比对。这是 `docs/ROADMAP.md`
6.4.1 要求的差分 harness：**任一项不一致即失败**，禁止用「看起来对」判断。

比对口径
--------
1. 返回的 `doc_kind` 与 `meta` 完全相等；
2. `records` 列表逐条完全相等（含 `errors` / `level_source` / `level_mismatch` / 各级 HTML）；
3. 落盘图片：文件名（uuid）每次都不同，故比对**数量 + 每张图的 sha256 排序集合**。

用法（backend 目录；仓库根 `.env` 需可读时请在仓库根执行）
--------------------------------------------------------
    # 基线自比：验证 harness 自身与 legacy 的确定性
    backend/.venv/Scripts/python -m scripts.diff_docx_reader --source ../xxx.docx

    # 候选实现在位后（默认仍走 legacy，未全绿不得切换）
    backend/.venv/Scripts/python -m scripts.diff_docx_reader --source ../xxx.docx --candidate lxml

输出以 `RESULT` 开头，便于筛选；退出码非 0 表示存在差异。
"""
import argparse
import hashlib
import importlib
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))
os.environ.setdefault("VP_DEBUG", "1")
os.environ.setdefault("VP_DISABLE_QUEUE", "1")
os.environ.setdefault("VP_DISABLE_REDIS", "1")

_URL_PREFIX = "/storage/uploads/images"
# 图片文件名是每次解析新生成的 uuid，无法逐字比对；比对前归一化为占位符，
# 图片**字节**另由 sha256 集合比对（见 _collect_images）。
_IMAGE_NAME_RE = re.compile(r"/storage/uploads/images/[0-9a-f]{32}\.[a-z]+")


def _normalize_images(value):
    """递归把图片 uuid 文件名替换为占位符，保留出现次数与位置。

    已知局限：同一段落内两张图互换位置不会被检出（uuid 随机，无法还原写出顺序）；
    由「数量 + 内容集合」兜底，单图顺序由 tests/test_docx_contract.py 覆盖。
    """
    if isinstance(value, str):
        return _IMAGE_NAME_RE.sub("/storage/uploads/images/<IMG>", value)
    if isinstance(value, dict):
        return {k: _normalize_images(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_images(v) for v in value]
    return value


def _iter_docx(source: Path) -> list[Path]:
    if source.is_dir():
        return sorted(p for p in source.rglob("*.docx") if not p.name.startswith("~$"))
    return [source]


def _collect_images(image_dir: Path) -> list[str]:
    """图片按内容 sha256 排序比对（uuid 文件名与顺序不作要求）。"""
    digests = [
        hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(image_dir.glob("*"))
        if p.is_file()
    ]
    return sorted(digests)


def _run(reader_mode: str, docx_path: Path, image_dir: Path):
    """按 `VP_DOCX_READER` 口径跑一次解析（同一进程内切换 settings，避免起两个进程）。"""
    parser = importlib.import_module("app.services.docx_parser")
    settings = importlib.import_module("app.core.config").settings
    previous = settings.DOCX_READER
    settings.DOCX_READER = reader_mode
    try:
        started = time.perf_counter()
        kind, meta, records = parser.parse_any_docx(
            str(docx_path), str(image_dir), _URL_PREFIX, docx_path.name
        )
        elapsed = round(time.perf_counter() - started, 3)
    finally:
        settings.DOCX_READER = previous
    return {
        "kind": kind,
        "meta": meta,
        "records": records,
        "images": _collect_images(image_dir),
        "seconds": elapsed,
    }


def _first_diff(left, right, path: str = "root") -> str | None:
    if type(left) is not type(right):
        return f"{path}: 类型不同 {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, dict):
        if set(left) != set(right):
            return f"{path}: 键集合不同 {sorted(set(left) ^ set(right))}"
        for key in sorted(left):
            diff = _first_diff(left[key], right[key], f"{path}.{key}")
            if diff:
                return diff
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: 长度不同 {len(left)} != {len(right)}"
        for index, (a, b) in enumerate(zip(left, right)):
            diff = _first_diff(a, b, f"{path}[{index}]")
            if diff:
                return diff
        return None
    if left != right:
        return f"{path}: {left!r} != {right!r}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="DOCX 解析差分对照（批次 E-2）")
    parser.add_argument("--source", required=True, help="待比对 .docx 文件或目录")
    parser.add_argument(
        "--candidate",
        choices=("legacy", "lxml"),
        default="legacy",
        help="候选实现（默认 legacy，即自比；lxml = 自写 iterparse reader）",
    )
    args = parser.parse_args()

    source = Path(args.source).resolve()
    paths = _iter_docx(source)
    if not paths:
        print(f"RESULT error=no-docx-found source={source}")
        return 1

    # 不用 mkdtemp：某些受管环境下它创建的目录随后不可再写入；显式建子目录更稳。
    base_tmp = Path(tempfile.gettempdir()) / f"talos_diff_{os.getpid()}"
    if base_tmp.exists():
        shutil.rmtree(base_tmp, ignore_errors=True)
    base_tmp.mkdir(parents=True, exist_ok=True)
    failures = 0
    try:
        for docx_path in paths:
            results = {}
            for label, reader_mode in (("legacy", "legacy"), ("candidate", args.candidate)):
                image_dir = base_tmp / f"{docx_path.stem}_{label}" / "images"
                image_dir.mkdir(parents=True, exist_ok=True)
                results[label] = _run(reader_mode, docx_path, image_dir)
            legacy, candidate = results["legacy"], results["candidate"]
            comparable = ("kind", "meta", "records", "images")
            diff = _first_diff(
                {k: _normalize_images(legacy[k]) for k in comparable},
                {k: _normalize_images(candidate[k]) for k in comparable},
            )
            status = "equal" if diff is None else "DIFF"
            print(
                f"RESULT file={docx_path.name} status={status} "
                f"records={len(legacy['records'])} images={len(legacy['images'])} "
                f"legacy={legacy['seconds']}s candidate={candidate['seconds']}s"
            )
            if diff:
                failures += 1
                print(f"RESULT   first_diff={diff}")
    finally:
        shutil.rmtree(base_tmp, ignore_errors=True)

    print(f"RESULT summary=files:{len(paths)} diff:{failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
