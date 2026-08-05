"""LibreOffice 目录域自动更新：检测 soffice 环境，通过 Basic 宏刷新 docx 的 TOC 域。

背景：纯 python-docx 只能向文档插入 TOC 域代码，页码计算依赖 Word/LibreOffice 的
排版引擎。本模块在报告导出时按需调用 soffice headless + Basic 宏打开文档、更新
全部目录索引并另存，实现「打开即用」的完整目录；当环境未安装 LibreOffice 时，
`update_toc_in_docx` 返回 False，由前端提示用户打开 Word 后手动更新域（F9）。

资源策略（面向 2 核 2G 的小型服务器）：
- 不常驻 soffice 进程：每次导出按需冷启动，宏执行完进程自动退出，避免常驻占用内存；
- 使用独立 UserInstallation（-env:UserInstallation）隔离 user profile，避免与
  gotenberg 等其它 LibreOffice 调用共用配置互相干扰；
- 进程内线程锁 + 跨进程文件锁串行化并发导出，避免同 profile 锁冲突；
- 宏采用「无参 + 路径哨兵文件」而非命令行传参，规避路径空格 / 特殊字符转义问题。
"""
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Basic 宏源码：从哨兵文件读取目标 docx，打开后更新全部目录索引 / 域并另存。
_TOC_MACRO_SRC = """Sub UpdateTOC
    Dim oDesktop As Object
    Dim oDoc As Object
    Dim oIndexes As Object
    Dim oArgs(0) As New com.sun.star.beans.PropertyValue
    Dim sFile As String
    Dim sUrl As String
    Dim i As Integer
    sFile = GetTocPath()
    If sFile = "" Then
        Exit Sub
    End If
    oArgs(0).Name = "Hidden"
    oArgs(0).Value = True
    oDesktop = StarDesktop
    sUrl = ConvertToUrl(sFile)
    oDoc = oDesktop.loadComponentFromURL(sUrl, "_blank", 0, oArgs())
    If IsNull(oDoc) Then
        Exit Sub
    End If
    oIndexes = oDoc.getDocumentIndexes()
    For i = 0 To oIndexes.getCount() - 1
        oIndexes.getByIndex(i).update()
    Next i
    oDoc.getTextFields().refresh()
    oDoc.store()
    oDoc.close(False)
End Sub

Function GetTocPath() As String
    Dim sHome As String
    Dim sPath As String
    Dim sTmp As String
    Dim oF As Integer
    sHome = Environ("HOME")
    If sHome = "" Then
        sHome = Environ("USERPROFILE")
    End If
    If sHome <> "" Then
        sPath = sHome & "/.talos_toc_path"
        If FileExists(sPath) Then
            oF = FreeFile
            Open sPath For Input As oF
            Line Input #oF, sPath
            Close #oF
            GetTocPath = sPath
            Exit Function
        End If
    End If
    sTmp = "/tmp/talos_toc_path"
    If FileExists(sTmp) Then
        oF = FreeFile
        Open sTmp For Input As oF
        Line Input #oF, sTmp
        Close #oF
        GetTocPath = sTmp
    Else
        GetTocPath = ""
    End If
End Function

Function ConvertToUrl(sPath As String) As String
    If Left(sPath, 1) = "/" Then
        ConvertToUrl = "file://" & sPath
    Else
        ConvertToUrl = "file:///" & Replace(sPath, "\\", "/")
    End If
End Function
"""

_MACRO_MODULE_NAME = "Module1"
_MACRO_SUB_NAME = "UpdateTOC"
# 目标 docx 绝对路径的哨兵文件（写入 HOME 与临时目录两份，宏按 HOME → /tmp 查找）
_PATH_FILENAME = ".talos_toc_path"
# 供 Basic 宏使用的隔离 user profile 目录名（置于系统临时目录下）
_PROFILE_DIRNAME = "talos_lo_profile"

_MACRO_URL = (
    f"vnd.sun.star.script:Standard.{_MACRO_MODULE_NAME}.{_MACRO_SUB_NAME}"
    "?language=Basic&location=application"
)

# 同一进程内串行化 soffice 调用
_PROC_LOCK = threading.Lock()


def find_soffice() -> str | None:
    """定位 soffice 可执行文件（Linux/macOS/Windows 常见名称与安装路径）。"""
    for name in ("soffice", "libreoffice", "soffice.exe"):
        p = shutil.which(name)
        if p:
            return p
    for c in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ):
        if Path(c).exists():
            return c
    return None


def is_libreoffice_available() -> bool:
    """环境是否具备 LibreOffice（决定导出的目录能否自动更新）。"""
    return find_soffice() is not None


def update_toc_in_docx(docx_path: str, timeout: int = 180) -> bool:
    """用 LibreOffice 更新 docx 目录域。

    成功返回 True；环境不可用 / 执行失败 / 超时均返回 False 并记录日志，
    绝不抛异常破坏导出主流程（目录域仍可由用户打开 Word 手动刷新）。
    """
    soffice = find_soffice()
    if not soffice:
        logger.info("未检测到 LibreOffice，报告目录将由 Word/WPS 打开时刷新")
        return False
    src = Path(docx_path)
    if not src.exists():
        logger.warning("目录更新跳过：文件不存在 %s", docx_path)
        return False
    with _PROC_LOCK, _process_file_lock():
        return _run_update(soffice, src, timeout)


# ---------- 内部实现 ----------


def _run_update(soffice: str, src: Path, timeout: int) -> bool:
    profile_dir = _profile_dir()
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
        _ensure_macro(profile_dir)
        _write_path_file(src)
        cmd = [
            soffice,
            f"-env:UserInstallation=file://{_url_encode_path(profile_dir)}",
            "--headless",
            "--invisible",
            "--norestore",
            "--nologo",
            "--nofirststartwizard",
            "--nodefault",
            _MACRO_URL,
        ]
        logger.info("执行 LibreOffice 宏更新目录：%s", src.name)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0:
            logger.info("LibreOffice 目录更新完成：%s", src.name)
            return True
        logger.warning(
            "LibreOffice 目录更新失败 rc=%s stderr=%s",
            proc.returncode, (proc.stderr or "")[-500:],
        )
        return False
    except subprocess.TimeoutExpired:
        logger.warning("LibreOffice 目录更新超时（%ss）：%s", timeout, src.name)
        return False
    except Exception:
        logger.exception("LibreOffice 目录更新异常：%s", src.name)
        return False


def _ensure_macro(profile_dir: Path) -> None:
    """把 UpdateTOC 宏写入 LibreOffice user profile 的 Standard 库（幂等）。"""
    basic_std = profile_dir / "user" / "basic" / "Standard"
    basic_std.mkdir(parents=True, exist_ok=True)
    module_xba = basic_std / f"{_MACRO_MODULE_NAME}.xba"
    if module_xba.exists():
        src = module_xba.read_text(encoding="utf-8", errors="ignore")
        if f"Sub {_MACRO_SUB_NAME}" in src:
            return
        marker = "</script:module>"
        if marker in src:  # 已有其它宏：在模块内追加，避免覆盖用户已有脚本
            module_xba.write_text(
                src.replace(marker, f"{_TOC_MACRO_SRC}\n{marker}"),
                encoding="utf-8",
            )
            return
    module_xba.write_text(_module_xml(), encoding="utf-8")
    (basic_std / "script.xlb").write_text(_script_xlb_xml(), encoding="utf-8")


def _module_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">\n'
        '<script:module xmlns:script="http://openoffice.org/2000/script" '
        f'script:name="{_MACRO_MODULE_NAME}" script:language="StarBasic">\n'
        f"{_TOC_MACRO_SRC}\n"
        "</script:module>\n"
    )


def _script_xlb_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">\n'
        '<library:library xmlns:library="http://openoffice.org/2000/library" '
        f'library:name="Standard" library:readonly="false" library:passwordprotected="false">\n'
        f' <library:element library:name="{_MACRO_MODULE_NAME}"/>\n'
        "</library:library>\n"
    )


def _profile_dir() -> Path:
    base = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))
    return base / _PROFILE_DIRNAME


def _url_encode_path(p: Path) -> str:
    """路径 → UserInstallation 所需的 file:/// 形式（百分号编码空格等）。"""
    path = str(p.resolve()).replace("\\", "/")
    if not path.startswith("/"):
        path = "/" + path
    return quote(path)


def _write_path_file(src: Path) -> None:
    """把目标 docx 绝对路径写入哨兵文件（HOME 一份 + 临时目录一份）。"""
    payload = str(src.resolve())
    home = Path.home()
    try:
        home.mkdir(parents=True, exist_ok=True)
        (home / _PATH_FILENAME).write_text(payload, encoding="utf-8")
    except OSError:
        logger.debug("写入 HOME 哨兵文件失败", exc_info=True)
    try:
        (Path(tempfile.gettempdir()) / _PATH_FILENAME).write_text(payload, encoding="utf-8")
    except OSError:
        logger.debug("写入临时目录哨兵文件失败", exc_info=True)


@contextmanager
def _process_file_lock():
    """跨进程文件锁：串行化不同 worker 进程对同一 profile 目录的 soffice 调用。"""
    lock_path = _profile_dir() / ".talos_lo.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        f.close()
