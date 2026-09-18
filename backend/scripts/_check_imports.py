"""一次性自检：静态校验 scripts/*.py 对 app 模块的引用是否仍然有效。

背景（2026-09-19 生产踩坑）：批次 C 把 `_sync_vul_retest_html` 从 `app.api.v1.vulns` 迁到
`app.services.vul_service.sync_vul_retest_html`，`scripts/backfill_retest.py` 未同步更新，
直到运维在容器里执行回填脚本时才暴露 ImportError —— 脚本不参与测试收集，这类断链不会被 CI 发现。

检查两类引用（只做 AST 解析 + 目标模块导入，不执行脚本自身）：
1. `from app.x import y`：y 是否为该模块的属性或子模块；
2. 「模块别名.属性」：如 `from app.services import vul_service` 后的
   `vul_service.sync_vul_retest_html` 是否存在。

正式守卫：`tests/test_source_guard.py::test_scripts_app_references_resolve` 复用本模块的
`collect_problems()`，本文件同时可作为命令行自检（`python -m scripts._check_imports`）。
"""
import ast
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SCRIPTS_DIR = Path(__file__).resolve().parent


def _import(module_path: str):
    try:
        return importlib.import_module(module_path)
    except Exception:  # noqa: BLE001  导入失败（含配置缺失）：由调用方决定是否记问题
        return None


def _resolves(module, name: str, module_path: str) -> bool:
    """`from <module_path> import <name>` 是否有效（含子模块形态）。"""
    if hasattr(module, name):
        return True
    return _import(f"{module_path}.{name}") is not None


def _module_aliases(tree: ast.AST) -> dict[str, str]:
    """收集「本地别名 → app 模块路径」，用于校验别名属性访问。"""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app."):
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.") and alias.asname:
                    aliases[alias.asname] = alias.name
    return aliases


def collect_problems() -> list[str]:
    """返回全部失效引用（空列表 = 通过）。同一问题去重后按脚本名排序。"""
    problems: set[str] = set()
    for path in sorted(_SCRIPTS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app."):
                module = _import(node.module)
                if module is None:
                    problems.add(f"{path.name}: 无法导入 {node.module}")
                    continue
                for alias in node.names:
                    if not _resolves(module, alias.name, node.module):
                        problems.add(f"{path.name}: {node.module} 中没有 {alias.name}")
        for local, module_path in _module_aliases(tree).items():
            module = _import(module_path)
            if module is None:
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == local
                    and not hasattr(module, node.attr)
                ):
                    problems.add(f"{path.name}: {module_path}.{node.attr} 不存在")
    return sorted(problems)


def main() -> int:
    problems = collect_problems()
    if problems:
        print("发现失效引用：")
        for p in problems:
            print("  -", p)
        return 1
    count = len([p for p in _SCRIPTS_DIR.glob("*.py") if not p.name.startswith("_")])
    print(f"scripts 引用自检通过（{count} 个脚本）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
