import os
import secrets
import time
import re
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from database import SessionLocal, Category
from community import router

@asynccontextmanager
async def lifespan(app):
    if os.getenv("APP_ENV") == "production":
        if len(os.getenv("APP_SECRET", "")) < 32 or os.getenv("COOKIE_SECURE") != "1":
            raise RuntimeError("生产模式需要至少 32 字符的 APP_SECRET 和 COOKIE_SECURE=1")
    with SessionLocal() as db:
        for name in ("游戏", "物理", "数学", "生成艺术", "天文", "创意实验"):
            if not db.query(Category).filter_by(name=name).first():
                db.add(Category(name=name))
        db.commit()
    yield

app = FastAPI(title="funAI · 灵感实验室", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(router)
limits = defaultdict(deque)

@app.middleware("http")
async def protection(request, call_next):
    visitor = request.cookies.get("funai_visitor", "")
    fresh = not re.fullmatch(r"[a-f0-9]{64}", visitor)
    request.state.visitor = secrets.token_hex(32) if fresh else visitor
    if request.method == "POST":
        origin = request.headers.get("origin")
        if (origin and origin != str(request.base_url).rstrip("/")) or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail":"请求来源不合法，请刷新后重试"}, 403)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail":"无效请求长度"},400)
        if length > (52*1024*1024 if request.url.path == "/upload" else 16384):
            return JSONResponse({"detail":"请求过大：上传最大 50 MB，互动请求最大 16 KB"}, 413)
        key = (request.client.host if request.client else "local", "upload" if request.url.path == "/upload" else "action")
        now = time.monotonic()
        if len(limits) > 10000:
            for old_key in list(limits):
                if not limits[old_key] or now-limits[old_key][-1] > 60:
                    limits.pop(old_key, None)
        queue = limits[key]
        while queue and now-queue[0] > 60:
            queue.popleft()
        if len(queue) >= (6 if key[1] == "upload" else 60):
            return JSONResponse({"detail":"操作太频繁，请稍后再试"}, 429)
        queue.append(now)
    response = await call_next(request)
    if fresh:
        response.set_cookie("funai_visitor", request.state.visitor, max_age=365*86400, httponly=True, samesite="lax", secure=os.getenv("COOKIE_SECURE") == "1")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not request.url.path.startswith(("/content/", "/assets/")):
        response.headers["X-Frame-Options"] = "DENY"
    return response

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
