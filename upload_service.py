"""Bounded static uploads. Never execute uploaded build scripts on the host."""
import io
import os
import re
import shutil
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
from fastapi import HTTPException

REPO = Path(os.getenv("WORKS_DIR", "games_repo")).resolve()
REPO.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = 50 * 1024 * 1024
MAX_EXPANDED = 200 * 1024 * 1024
ALLOWED = {".html", ".htm", ".js", ".mjs", ".css", ".json", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".wasm", ".data", ".txt", ".xml", ".mp3", ".ogg", ".wav", ".mp4", ".webm", ".woff", ".woff2", ".ttf", ".map"}

def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise HTTPException(400, "文件路径不合法")
    return path

class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        value = attrs.get("src") or (attrs.get("href") if tag == "link" else None)
        if value:
            self.urls.append(value)

def prepare_upload(data, filename):
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(400, "请选择非空文件，最大支持 50 MB")
    key = uuid.uuid4().hex
    root = REPO / key
    root.mkdir()
    report = []
    try:
        if filename.lower().endswith(".zip"):
            try:
                archive = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                raise HTTPException(400, "压缩包损坏，请重新导出 ZIP 文件")
            with archive:
                infos = archive.infolist()
                if len(infos) > 1500 or sum(i.file_size for i in infos) > MAX_EXPANDED:
                    raise HTTPException(400, "压缩包最多 1500 个文件，解压后不得超过 200 MB")
                for info in infos:
                    name = info.filename.replace("\\", "/")
                    parts = PurePosixPath(name).parts
                    if name.startswith("/") or ".." in parts or ":" in name or stat.S_ISLNK(info.external_attr >> 16):
                        raise HTTPException(400, "压缩包包含不安全路径或符号链接")
                    if any(p.endswith((".", " ")) or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", p.split(".")[0], re.I) for p in parts):
                        raise HTTPException(400, "压缩包包含系统保留文件名，请重命名后上传")
                    if any(p.startswith(".") or p in {"__MACOSX", "node_modules"} for p in parts):
                        continue
                    if info.is_dir():
                        continue
                    if Path(name).suffix.lower() not in ALLOWED:
                        raise HTTPException(400, f"不支持的文件类型：{Path(name).suffix}。请上传浏览器可运行的静态产物")
                    dest = safe_path(root, name)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, dest.open("wb") as target:
                        shutil.copyfileobj(source, target)
            entries = sorted(root.rglob("index.html"), key=lambda p: (len(p.parts), str(p)))
            if not entries:
                raise HTTPException(400, "找不到 index.html。请先构建项目，再压缩 dist/build 目录；支持 ZIP 外层文件夹")
            built = [p for p in entries if "dist" in p.parts or "build" in p.parts]
            entry = (built or entries)[0]
            if list(root.rglob("package.json")) and not built:
                raise HTTPException(400, "检测到源码项目。请在本地运行构建并上传 dist/build 产物，服务器不会执行上传脚本")
        elif filename.lower().endswith((".html", ".htm")):
            entry = root / "index.html"
            entry.write_bytes(data)
        else:
            raise HTTPException(400, "支持 HTML 单文件或 ZIP 静态项目")
        try:
            html = entry.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(400, "入口 HTML 必须采用 UTF-8 编码")
        if not re.search(r"<(?:html|body|canvas|div|script|svg)\b", html, re.I):
            raise HTTPException(400, "入口文件不是有效的 HTML 页面")
        parser = Resources()
        parser.feed(html)
        missing, remote = [], []
        for url in parser.urls:
            parsed = urlsplit(url)
            if parsed.scheme in {"https", "http"} or url.startswith("//"):
                remote.append(url)
            elif not parsed.scheme and parsed.path:
                if url.startswith("/"):
                    missing.append(url + "（请改为相对路径）")
                else:
                    resource = safe_path(root, str(entry.parent.relative_to(root) / unquote(parsed.path)))
                    if not resource.is_file():
                        missing.append(url)
        if missing:
            raise HTTPException(400, "缺少资源或路径错误：" + "、".join(missing[:8]))
        report.append({"level": "success", "message": "文件结构、入口 HTML 和直接引用的本地资源检查通过"})
        if remote:
            report.append({"level": "warning", "message": f"检测到 {len(remote)} 个外部资源，运行依赖网络；请确认来源可信"})
        report.append({"level": "info", "message": "静态检查不代表功能正确，请在下方试运行并操作作品后发布"})
        return key, entry.relative_to(root).as_posix(), html, report
    except (zipfile.BadZipFile, RuntimeError, OSError, ValueError) as exc:
        if root.is_relative_to(REPO) and root != REPO:
            shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(400, "无法读取上传内容，请检查压缩包是否损坏、加密或包含非法文件名") from exc
    except Exception:
        if root.is_relative_to(REPO) and root != REPO:
            shutil.rmtree(root)
        raise
