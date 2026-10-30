import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session
from database import Category, Game, Reaction, SiteSetting, get_db
from upload_service import REPO, MAX_UPLOAD, prepare_upload, safe_path

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
SECRET = os.getenv("APP_SECRET", "")
if not SECRET:
    secret_path = Path(__file__).parent / ".runtime" / "app-secret"
    secret_path.parent.mkdir(exist_ok=True)
    try:
        with secret_path.open("x", encoding="ascii") as secret_file:
            secret_file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    SECRET = secret_path.read_text(encoding="ascii").strip()

def token(value):
    return hmac.new(SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()

async def json_body(request):
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "请求数据不是有效 JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "请求数据必须是 JSON 对象")
    return body

def settings(db):
    return {row.key: row.value for row in db.query(SiteSetting).all()}

def context(request, db, **extra):
    categories = db.query(Category).order_by(Category.id).all()
    counts = dict(db.query(Game.category_id, func.count(Game.id)).filter(Game.status == "published").group_by(Game.category_id).all())
    return {"request": request, "categories": categories, "counts": counts,
            "category_names": {c.id:c.name for c in categories}, "settings": settings(db),
            "current_year": datetime.now().year, **extra}

def listing(db, category_id, q, sort):
    query = db.query(Game).filter(Game.status == "published")
    if category_id:
        query = query.filter(Game.category_id == category_id)
    if q:
        escaped = q.replace("%", "\\%").replace("_", "\\_")
        query = query.filter(or_(Game.title.contains(escaped, escape="\\"), Game.description.contains(escaped, escape="\\"), Game.author.contains(escaped, escape="\\")))
    order = {"latest": Game.created_at.desc(), "rating": Game.rating.desc(), "hot": (Game.views + Game.likes * 8 + Game.rating_count * 5).desc()}
    return query.order_by(order.get(sort, order["hot"]), Game.id.desc())

@router.get("/", response_class=HTMLResponse)
def index(request: Request, category_id: int = 0, q: str = "", sort: str = "hot", page: int = 1, db: Session = Depends(get_db)):
    q = q.strip()[:100]
    page = max(1, page)
    query = listing(db, category_id, q, sort)
    total = query.count()
    page = min(page, max(1, (total+11)//12))
    featured = db.query(Game).filter(Game.status == "published", or_(Game.title.contains("引力"), Game.title.contains("Solar"))).first()
    if not featured:
        featured = listing(db, 0, "", "hot").first()
    def url(**changes):
        return "/?" + urlencode({"category_id": category_id, "q": q, "sort": sort, "page": 1, **changes})
    liked_ids = {r.game_id for r in db.query(Reaction).filter_by(visitor=token(request.state.visitor), liked=1).all()}
    return templates.TemplateResponse("index.html", context(request, db, games=query.offset((page-1)*12).limit(12).all(), liked_ids=liked_ids, selected_category=category_id, q=q, sort=sort, page=page, total_pages=(total+11)//12, total=total, featured=featured, url=url, total_works=db.query(Game).filter(Game.status=="published").count(), total_views=db.query(func.sum(Game.views)).filter(Game.status=="published").scalar() or 0))

@router.get("/api/games")
def api_games(category_id: int = 0, q: str = "", sort: str = "hot", page: int = 1, db: Session = Depends(get_db)):
    query = listing(db, category_id, q[:100], sort)
    return {"games": [{k:getattr(g,k) for k in ("id","title","description","author","ai_model","category_id","rating","rating_count","views","likes")} for g in query.offset((max(page,1)-1)*12).limit(12)], "total": query.count()}

def work(db, game_id, request):
    game = db.get(Game, game_id)
    if not game or game.status == "deleted" or (game.status == "draft" and game.owner_token != token(request.state.visitor)):
        raise HTTPException(404, "作品不存在或尚未发布")
    return game

@router.get("/play/{game_id}")
def play(game_id: int, request: Request, db: Session = Depends(get_db)):
    game = work(db, game_id, request)
    if game.status == "published":
        db.execute(update(Game).where(Game.id == game_id).values(views=Game.views+1))
        db.commit()
        db.refresh(game)
    reaction = db.query(Reaction).filter_by(game_id=game_id, visitor=token(request.state.visitor)).first()
    return templates.TemplateResponse("play.html", context(request, db, game=game, report=json.loads(game.check_report or "[]"), reaction=reaction))

@router.get("/upload")
def upload_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("upload.html", context(request, db))

@router.post("/upload")
async def upload(request: Request, title: str = Form(...), author: str = Form("匿名创作者"), description: str = Form(""), ai_model: str = Form("AI 辅助"), prompt: str = Form(""), category_id: int = Form(...), html_code: str = Form(""), file: UploadFile = File(None), db: Session = Depends(get_db)):
    if not title.strip() or len(title)>80 or len(description)>1000 or len(author)>40 or len(ai_model)>60 or len(prompt)>10000:
        raise HTTPException(400, "请检查字段长度：标题 80 字、简介 1000 字、作者 40 字、模型 60 字、提示词 10000 字以内")
    if not db.get(Category, category_id):
        raise HTTPException(400, "请选择有效分类")
    data = await file.read(MAX_UPLOAD+1) if file and file.filename else html_code.encode("utf-8")
    key, entry, html, report = await run_in_threadpool(prepare_upload, data, file.filename if file and file.filename else "index.html")
    game = Game(title=title.strip(), author=author.strip() or "匿名创作者", description=description.strip(), ai_model=ai_model.strip() or "AI 辅助", prompt=prompt, category_id=category_id, filename=key+".html", html_code=html, is_multi_file=1, directory_name=key, entry_path=entry, status="draft", owner_token=token(request.state.visitor), check_report=json.dumps(report,ensure_ascii=False))
    db.add(game)
    db.commit()
    return {"url": f"/play/{game.id}", "id": game.id}

@router.post("/publish/{game_id}")
async def publish(game_id: int, request: Request, db: Session = Depends(get_db)):
    game = work(db, game_id, request)
    if game.owner_token != token(request.state.visitor):
        raise HTTPException(403, "仅上传者可以发布")
    body = await json_body(request)
    if body.get("tested") is not True:
        raise HTTPException(400, "请先试运行作品并确认可以正常使用")
    game.status = "published"
    db.commit()
    return {"url": f"/play/{game_id}"}

@router.post("/like/{game_id}")
@router.post("/rate/{game_id}")
async def react(game_id: int, request: Request, db: Session = Depends(get_db)):
    game = work(db, game_id, request)
    if game.status != "published":
        raise HTTPException(400, "发布后才可互动")
    # Serialize SQLite reaction writes so counters and per-visitor rows remain consistent.
    db.rollback()
    from sqlalchemy import text
    db.execute(text("BEGIN IMMEDIATE"))
    game = db.get(Game, game_id)
    if not game or game.status != "published":
        raise HTTPException(404, "作品已下架")
    visitor = token(request.state.visitor)
    row = db.query(Reaction).filter_by(game_id=game_id, visitor=visitor).first()
    if not row:
        row = Reaction(game_id=game_id, visitor=visitor, liked=0, score=0)
        db.add(row)
    if request.url.path.startswith("/like"):
        row.liked = 1 - row.liked
        game.likes = max(0, game.likes + (1 if row.liked else -1))
    else:
        body = await json_body(request)
        score = body.get("rating")
        if type(score) is not int or not 1 <= score <= 5:
            raise HTTPException(400, "评分必须为 1–5 的整数")
        game.rating_total += score - row.score
        game.rating_count += int(row.score == 0)
        row.score = score
        game.rating = round(game.rating_total/game.rating_count, 1)
    db.commit()
    return {"likes": game.likes, "liked": bool(row.liked), "rating": game.rating, "rating_count": game.rating_count, "score": row.score}

# CSP sandbox is applied even when uploaded HTML is opened directly.
CONTENT_CSP = "sandbox allow-scripts allow-pointer-lock; default-src 'self' https: data: blob: 'unsafe-inline' 'unsafe-eval'; object-src 'none'; form-action 'none'; base-uri 'self'"
BRIDGE = '''<script>(function(){const send=(kind,message)=>parent.postMessage({source:'funai-runtime',kind,message:String(message).slice(0,1200)},'*');addEventListener('error',e=>send('error',e.message?e.message+' @ '+e.filename+':'+e.lineno:'资源加载失败：'+(e.target.src||e.target.href||'未知资源')),true);addEventListener('unhandledrejection',e=>send('error',e.reason?.message||e.reason));addEventListener('load',()=>send('loaded','页面已加载，请操作作品检查功能'));setInterval(()=>send('heartbeat',''),1500);})();</script>'''

@router.get("/content/{game_id}")
def content(game_id: int, request: Request, db: Session = Depends(get_db)):
    game = work(db, game_id, request)
    access = token(f"preview:{game.id}:{game.owner_token}")
    base = f"/assets/{game.id}/{access}/"
    if game.is_multi_file:
        root = safe_path(REPO, game.directory_name)
        entry = safe_path(root, game.entry_path or "index.html")
        if not entry.is_file():
            raise HTTPException(404, "作品入口文件缺失，请联系管理员")
        html = entry.read_text(encoding="utf-8-sig")
        parent = Path(game.entry_path or "index.html").parent.as_posix()
        if parent != ".":
            base += quote(parent)+"/"
    else:
        html = game.html_code or ""
    # Insert before author scripts so early syntax/resource failures are observable.
    import re
    injection = f'<base href="{base}">' + BRIDGE
    match = re.search(r"<head\b[^>]*>", html, re.I)
    html = html[:match.end()] + injection + html[match.end():] if match else injection + html
    return HTMLResponse(html, headers={"Content-Security-Policy": CONTENT_CSP, "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"})

@router.get("/assets/{game_id}/{access}/{path:path}")
def asset(game_id: int, access: str, path: str, request: Request, db: Session = Depends(get_db)):
    game = db.get(Game, game_id)
    if not game or game.status == "deleted" or not game.is_multi_file:
        raise HTTPException(404, "资源不存在")
    if not hmac.compare_digest(access, token(f"preview:{game.id}:{game.owner_token}")):
        raise HTTPException(404, "资源不存在")
    root = safe_path(REPO, game.directory_name)
    target = safe_path(root, path)
    from upload_service import ALLOWED
    if not target.is_file() or target.suffix.lower() not in ALLOWED:
        raise HTTPException(404, "资源不存在")
    return FileResponse(target, headers={"Content-Security-Policy": CONTENT_CSP, "Access-Control-Allow-Origin": "*", "X-Content-Type-Options": "nosniff"})

@router.get("/leaderboard")
def leaderboard():
    return RedirectResponse("/?sort=rating")

@router.get("/about")
@router.get("/privacy")
def about(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("about.html", context(request, db))

@router.get("/ads.txt", response_class=PlainTextResponse)
def ads_txt(db: Session = Depends(get_db)):
    config = settings(db)
    publisher = config.get("ads_client", "")
    if config.get("ads_enabled") == "1" and publisher:
        return f"google.com, {publisher.removeprefix('ca-')}, DIRECT, f08c47fec0942fa0\n"
    return ""
