"""Separate administrator service; bind to loopback by default."""
import hmac
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import Game, Category, SiteSetting, get_db
from community import templates, context

PASSWORD = os.getenv("ADMIN_PASSWORD", "")
sessions, attempts = {}, {}

@asynccontextmanager
async def lifespan(app):
    if len(PASSWORD) < 16:
        raise RuntimeError("请设置至少 16 位的 ADMIN_PASSWORD 环境变量后启动后台")
    yield

app = FastAPI(title="funAI 管理中心", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

def auth(request: Request):
    session = sessions.get(request.cookies.get("funai_admin", ""))
    if not session or session["expires"] < time.time():
        raise HTTPException(303, headers={"Location": "/admin/login"})
    return session

@app.middleware("http")
async def headers(request, call_next):
    if request.method == "POST":
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail":"请求来源不合法"},403)
    response = await call_next(request)
    response.headers.update({"X-Frame-Options":"DENY","Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
    return response

@app.get("/")
def root():
    return RedirectResponse("/admin/dashboard")

@app.get("/admin/login")
def login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request":request})

@app.post("/admin/login")
def login(request: Request, password: str = Form(...)):
    host = request.client.host if request.client else "local"
    now = time.time()
    for key in list(attempts):
        if now-attempts[key][0] > 600: attempts.pop(key)
    first,count = attempts.get(host, (now,0))
    if count >= 10: raise HTTPException(429,"尝试过多，请 10 分钟后再试")
    if not PASSWORD or not hmac.compare_digest(password.encode(),PASSWORD.encode()):
        attempts[host] = (first,count+1)
        return templates.TemplateResponse("admin/login.html", {"request":request,"error":"管理密码不正确"},status_code=401)
    attempts.pop(host,None)
    for key in list(sessions):
        if sessions[key]["expires"] < now: sessions.pop(key)
    sid = secrets.token_urlsafe(32)
    sessions[sid] = {"csrf":secrets.token_urlsafe(32), "expires":now+8*3600}
    response = RedirectResponse("/admin/dashboard",303)
    response.set_cookie("funai_admin",sid,httponly=True,samesite="strict",secure=os.getenv("COOKIE_SECURE")=="1",max_age=8*3600)
    return response

@app.get("/admin/dashboard")
def dashboard(request: Request, tab: str="works", q: str="", db: Session=Depends(get_db), session=Depends(auth)):
    query = db.query(Game)
    if q: query = query.filter(Game.title.contains(q[:100],autoescape=True))
    works = query.filter(Game.status == "deleted" if tab == "trash" else Game.status != "deleted").order_by(Game.id.desc()).limit(200).all()
    return templates.TemplateResponse("admin/dashboard.html",context(request,db,admin_mode=True,tab=tab,games=works,csrf=session["csrf"],q=q,total_works=db.query(Game).filter(Game.status=="published").count(),draft_count=db.query(Game).filter(Game.status=="draft").count(),trash_count=db.query(Game).filter(Game.status=="deleted").count(),notice=request.query_params.get("notice","")))

def check_csrf(session, csrf):
    if not hmac.compare_digest(session["csrf"],csrf): raise HTTPException(403,"页面已过期，请刷新后重试")

@app.post("/admin/work/{game_id}/{action}")
def manage(game_id:int, action:str, csrf:str=Form(...), db:Session=Depends(get_db), session=Depends(auth)):
    check_csrf(session,csrf)
    game=db.get(Game,game_id)
    if not game: raise HTTPException(404,"作品不存在")
    if action=="delete" and game.status != "deleted":
        db.merge(SiteSetting(key=f"restore_{game.id}",value=game.status))
        game.status="deleted"
    elif action=="restore" and game.status=="deleted":
        previous=db.get(SiteSetting,f"restore_{game.id}")
        game.status=previous.value if previous and previous.value in ("published","draft") else "draft"
    else: raise HTTPException(400,"无效操作")
    db.commit()
    return RedirectResponse("/admin/dashboard?notice=saved",303)

@app.post("/admin/categories")
def add_category(name:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db),session=Depends(auth)):
    check_csrf(session,csrf)
    name=name.strip()
    if not name or len(name)>20: raise HTTPException(400,"分类名称限 1–20 字")
    if not db.query(Category).filter_by(name=name).first():
        db.add(Category(name=name)); db.commit()
    return RedirectResponse("/admin/dashboard?tab=categories&notice=saved",303)

@app.post("/admin/settings")
def save_settings(csrf:str=Form(...),ads_enabled:str=Form("0"),ads_client:str=Form(""),ads_slot:str=Form(""),db:Session=Depends(get_db),session=Depends(auth)):
    check_csrf(session,csrf)
    ads_client,ads_slot=ads_client.strip(),ads_slot.strip()
    if ads_client and not re.fullmatch(r"ca-pub-\d{16}",ads_client): raise HTTPException(400,"发布商 ID 格式应为 ca-pub- 后接 16 位数字")
    if ads_slot and not re.fullmatch(r"\d{10}",ads_slot): raise HTTPException(400,"广告单元 ID 应为 10 位数字")
    if ads_enabled=="1" and (not ads_client or not ads_slot): raise HTTPException(400,"启用前请填写发布商与广告单元 ID")
    for key,value in {"ads_enabled":"1" if ads_enabled=="1" else "0","ads_client":ads_client,"ads_slot":ads_slot}.items():
        db.merge(SiteSetting(key=key,value=value))
    db.commit()
    return RedirectResponse("/admin/dashboard?tab=ads&notice=saved",303)

@app.post("/admin/logout")
def logout(request:Request,csrf:str=Form(...),session=Depends(auth)):
    check_csrf(session,csrf)
    sessions.pop(request.cookies.get("funai_admin"),None)
    response=RedirectResponse("/admin/login",303)
    response.delete_cookie("funai_admin")
    return response

if __name__=="__main__":
    import uvicorn
    uvicorn.run("admin_main:app",host="127.0.0.1",port=8001)
