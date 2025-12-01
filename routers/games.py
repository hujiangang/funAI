import os
import uuid
import shutil
import zipfile
import re
import subprocess
import logging
from fastapi import APIRouter, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from tools.npm_build_helper import build_project

# 从父级目录导入数据库和工具函数
from database import get_db, Game, Category
from utils import sync_games_from_folder

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# --- 构建辅助函数 ---
def needs_build(directory: str) -> bool:
    """检查目录是否包含需要构建的 Node.js 项目"""
    return os.path.exists(os.path.join(directory, "package.json"))

def find_build_output_dir(directory: str) -> str:
    """查找构建输出目录 (dist, build, 或 out)"""
    common_dirs = ['dist', 'build', 'out']
    for dir_name in common_dirs:
        dir_path = os.path.join(directory, dir_name)
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            return dir_name
    return None

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, category_id: int = None, db: Session = Depends(get_db)):
    # 获取所有分类
    categories = db.query(Category).all()
    
    # 根据分类筛选游戏
    if category_id:
        games = db.query(Game).filter(Game.category_id == category_id).order_by(Game.views.desc()).all()
    else:
        games = db.query(Game).order_by(Game.views.desc()).all()
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "games": games,
            "categories": categories,
            "selected_category": category_id
        }
    )

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
    game.rating = round(game.rating_total / game.rating_count, 1)
    
    db.commit()
    db.refresh(game)

    return {"rating": game.rating, "rating_count": game.rating_count}

# --- ⭐ 新增：显示上传页面 ---
@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request, db: Session = Depends(get_db)):
    categories = db.query(Category).all()
    return templates.TemplateResponse("upload.html", {"request": request, "categories": categories})

# --- ⭐ 新增：处理上传请求 ---
@router.post("/upload")
async def handle_upload(
    title: str = Form(...),
    author: str = Form(...),
    ai_model: str = Form(...),
    description: str = Form(...),
    prompt: str = Form(...),
    category_id: int = Form(1),        # 新增：分类ID，默认1
    html_code: str = Form(None),       # 允许为空，因为可能是上传Zip
    zip_file: UploadFile = File(None), # 新增：Zip文件上传
    custom_ai_model: str = Form(None),
    edit_password: str = Form(""),
    db: Session = Depends(get_db)
):
    # 1. 生成唯一ID
    unique_id = uuid.uuid4().hex[:8]
    filename = f"upload_{unique_id}.html"
    
    is_multi_file = 0
    directory_name = ""
    final_html_code = html_code or ""

    # 处理 Zip 文件
    if zip_file and zip_file.filename.endswith(".zip"):
        is_multi_file = 1
        directory_name = unique_id
        upload_dir = os.path.join("games_repo", directory_name)
        os.makedirs(upload_dir, exist_ok=True)
        
        # 保存并解压 zip 文件
        zip_content = await zip_file.read()
        zip_path = os.path.join(upload_dir, "temp.zip")
        
        with open(zip_path, "wb") as f:
            f.write(zip_content)
        
        # 解压 zip 文件
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(upload_dir)
            os.remove(zip_path)
        except Exception as e:
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"解压ZIP文件失败: {str(e)}")
        
        # 检查项目是否需要构建
        if needs_build(upload_dir):
            # 构建项目
            success, error_msg = build_project(upload_dir)
            if not success:
                shutil.rmtree(upload_dir, ignore_errors=True)
                raise HTTPException(status_code=400, detail=f"项目构建失败: {error_msg}")
            
            # 查找并使用构建输出目录
            build_dir = find_build_output_dir(upload_dir)
            if not build_dir:
                shutil.rmtree(upload_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=400, 
                    detail="构建成功但未找到输出目录（dist/build/out）。请确保项目的构建脚本会生成这些目录之一。"
                )
            
            # 将构建输出移到根目录并清理源文件
            build_path = os.path.join(upload_dir, build_dir)
            temp_dir = upload_dir + "_temp"
            shutil.move(build_path, temp_dir)
            shutil.rmtree(upload_dir)
            shutil.move(temp_dir, upload_dir)
        
        # 验证 index.html 存在（构建后或解压后）
        index_path = os.path.join(upload_dir, "index.html")
        if not os.path.exists(index_path):
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise HTTPException(
                status_code=400,
                detail="未找到 index.html 文件。请确保 ZIP 包含 index.html（或构建后生成 index.html）。"
            )
    
    # 确定最终的 AI 模型名称
    final_ai_model = custom_ai_model if ai_model == "其他" and custom_ai_model else ai_model
    
    # 当没有上传 zip 文件时，使用单文件模式
    if not zip_file or not zip_file.filename.endswith(".zip"):
        file_path = os.path.join("games_repo", filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_code)

    # 3. 存入数据库
    new_game = Game(
        title=title,
        author=author,
        ai_model=final_ai_model, 
        description=description,
        prompt=prompt,
        category_id=category_id,        # 新增：分类ID
        filename=filename,
        html_code=final_html_code,
        edit_password=edit_password,
        is_multi_file=is_multi_file,
        directory_name=directory_name
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
    
    if game.is_multi_file:
        # 为多文件游戏读取并修改 index.html，注入 base 标签以修复资源路径问题
        index_file_path = os.path.join("games_repo", game.directory_name, "index.html")
        
        # 检查 index.html 是否存在
        if not os.path.exists(index_file_path):
            return HTMLResponse("Game index.html not found", status_code=404)
        
        # 读取游戏的 index.html 内容
        try:
            with open(index_file_path, "r", encoding="utf-8") as f:
                html_content = f.read()
        except Exception as e:
            return HTMLResponse(f"Error reading game file: {str(e)}", status_code=500)
        
        # 在 <head> 标签后注入 <base> 标签，确保所有路径相对于游戏目录解析
        base_tag = f'<base href="/repo/{game.directory_name}/">'
        
        # 查找 <head> 标签并在其后插入 base 标签
        head_pattern = re.compile(r'(<head[^>]*>)', re.IGNORECASE)
        match = head_pattern.search(html_content)
        
        if match:
            insert_pos = match.end()
            modified_html = html_content[:insert_pos] + '\n    ' + base_tag + html_content[insert_pos:]
        else:
            modified_html = base_tag + '\n' + html_content
        
        return HTMLResponse(content=modified_html)
    else:
        return HTMLResponse(content=game.html_code)

# --- ⭐ 新增：编辑页面 ---
@router.get("/edit/{game_id}", response_class=HTMLResponse)
async def edit_page(request: Request, game_id: int, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return templates.TemplateResponse("upload.html", {"request": request, "game": game})

# --- ⭐ 新增：处理编辑请求 ---
@router.post("/edit/{game_id}")
async def handle_edit(
    game_id: int,
    title: str = Form(...),
    author: str = Form(...),
    ai_model: str = Form(...),
    description: str = Form(...),
    prompt: str = Form(...),
    html_code: str = Form(...),
    custom_ai_model: str = Form(None),
    edit_password: str = Form(...),
    db: Session = Depends(get_db)
):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # 验证密码
    if game.edit_password and game.edit_password != edit_password:
        return HTMLResponse("<h3>❌ 密码错误，无法保存修改。</h3><p>请返回上一页重试。</p>", status_code=403)

    # 确定最终的 AI 模型名称
    final_ai_model = custom_ai_model if ai_model == "其他" and custom_ai_model else ai_model

    # 更新数据库字段
    game.title = title
    game.author = author
    game.ai_model = final_ai_model
    game.description = description
    game.prompt = prompt
    game.html_code = html_code
    
    # 更新文件内容（仅单文件游戏）
    if not game.is_multi_file:
        file_path = os.path.join("games_repo", game.filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_code)

    db.commit()
    db.refresh(game)

    return RedirectResponse(url=f"/play/{game.id}", status_code=303)