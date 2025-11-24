import os
import uuid
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# 从父级目录导入数据库和工具函数
from database import get_db, Game
from utils import sync_games_from_folder

router = APIRouter()
templates = Jinja2Templates(directory="templates") # 假设 templates 目录在项目根目录

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    games = db.query(Game).order_by(Game.views.desc()).all()
    return templates.TemplateResponse("index.html", {"request": request, "games": games})

@router.get("/play/{game_id}", response_class=HTMLResponse)
async def play(request: Request, game_id: int, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game: return HTMLResponse("游戏未找到", 404)
    
    game.views += 1
    db.commit()
    db.refresh(game)
    return templates.TemplateResponse("play.html", {"request": request, "game": game})

# --- ⭐ 新增：处理游戏评分 ---
@router.post("/rate/{game_id}")
async def rate_game(request: Request, game_id: int, db: Session = Depends(get_db)):
    """接收用户对游戏的评分"""
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    try:
        data = await request.json()
        rating = data.get("rating")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON data")

    if rating is None or not (isinstance(rating, int) and 1 <= rating <= 5):
        raise HTTPException(status_code=400, detail="Invalid rating. Must be an integer between 1 and 5.")

    game.rating_total += rating
    game.rating_count += 1
    game.rating = round(game.rating_total / game.rating_count, 1) # 保留一位小数
    
    db.commit()
    db.refresh(game)

    return {"rating": game.rating, "rating_count": game.rating_count}

# --- ⭐ 新增：显示上传页面 ---
@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

# --- ⭐ 新增：处理上传请求 ---
@router.post("/upload")
async def handle_upload(
    title: str = Form(...),
    author: str = Form(...),
    ai_model: str = Form(...),
    description: str = Form(...),
    prompt: str = Form(...),
    html_code: str = Form(...),
    custom_ai_model: str = Form(None), # 新增：用于接收用户手动填写的AI模型
    db: Session = Depends(get_db)
):
    # 1. 生成一个唯一的文件名
    filename = f"upload_{uuid.uuid4().hex[:8]}.html"

    # 确定最终的 AI 模型名称
    final_ai_model = custom_ai_model if ai_model == "其他" and custom_ai_model else ai_model
    
    # 2. 保存到 games_repo 文件夹 (这样数据不仅在数据库，还在硬盘里)
    file_path = os.path.join("games_repo", filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_code)
    
    # 3. 存入数据库
    new_game = Game(
        title=title,
        author=author,
        ai_model=final_ai_model, # 使用最终确定的模型名称
        description=description,
        prompt=prompt,
        filename=filename,
        html_code=html_code
    )
    db.add(new_game)
    db.commit()
    db.refresh(new_game)
    
    # 4.直接跳转到玩游戏页面
    return RedirectResponse(url=f"/play/{new_game.id}", status_code=303)

@router.get("/refresh")
async def refresh_library():
    sync_games_from_folder()
    return RedirectResponse(url="/")

# --- ⭐ 修复：新增一个接口，专门只返回游戏的纯 HTML 代码 ---
@router.get("/content/{game_id}", response_class=HTMLResponse)
async def game_content(game_id: int, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        return HTMLResponse("Game not found", status_code=404)
    return HTMLResponse(content=game.html_code)