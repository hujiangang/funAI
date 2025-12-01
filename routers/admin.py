import os
from fastapi import APIRouter, Request, Depends, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import secrets

# 从父级目录导入数据库和工具函数
from database import get_db, Game, Category
from utils import sync_games_from_folder

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# 管理员密钥
ADMIN_KEY = "admin123"

# 简单的cookie验证函数
def verify_admin_cookie(request: Request):
    """验证管理员cookie"""
    cookie_value = request.cookies.get("admin_key")
    if cookie_value != ADMIN_KEY:
        # 如果验证失败，可以重定向回登录页，或者抛出403
        # 这里为了安全起见，API通常抛出异常，但为了用户体验也可以改成 RedirectResponse
        raise HTTPException(status_code=403, detail="未授权访问")
    return True

# --- 管理员登录页面 ---
@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """管理员登录页面"""
    return templates.TemplateResponse("admin_login.html", {"request": request})

# --- 管理员登录处理 (已修复) ---
@router.post("/admin/login")
async def admin_login(
    request: Request,
    api_key: str = Form(...)
):
    """处理管理员登录请求"""
    if api_key == ADMIN_KEY:
        # 1. 创建重定向响应对象
        redirect_response = RedirectResponse(url="/admin/dashboard", status_code=303)
        
        # 2. 在这个重定向对象上设置 Cookie
        redirect_response.set_cookie(
            key="admin_key",
            value=ADMIN_KEY,
            httponly=True,
            secure=False,  # 本地开发设为False，线上HTTPS设为True
            path="/"
        )
        
        # 3. 返回这个对象
        return redirect_response
    else:
        return templates.TemplateResponse(
            "admin_login.html", 
            {"request": request, "error": "错误的API密钥"}
        )

# --- 管理员仪表盘 ---
@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_cookie)
):
    """管理员仪表盘"""
    games = db.query(Game).all()
    categories = db.query(Category).all()
    total_games = len(games)
    # 处理空列表的情况，防止 sum 报错（虽然 sum 空列表是 0，但为了健壮性）
    total_views = sum(game.views for game in games) if games else 0
    total_ratings = sum(game.rating_count for game in games) if games else 0
    
    return templates.TemplateResponse(
        "admin_dashboard.html", 
        {
            "request": request, 
            "games": games, 
            "categories": categories,
            "total_games": total_games, 
            "total_views": total_views, 
            "total_ratings": total_ratings
        }
    )

# --- 删除游戏功能 ---
@router.post("/admin/delete/{game_id}")
async def admin_delete_game(
    game_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_cookie)
):
    """删除游戏"""
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="游戏未找到")
    
    # 删除文件
    # 建议加个判断，防止 filename 为空的情况
    if game.filename:
        file_path = os.path.join("games_repo", game.filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"删除文件失败: {e}")
    
    # 删除数据库记录
    db.delete(game)
    db.commit()
    
    return RedirectResponse(url="/admin/dashboard", status_code=303)

# --- 管理员登出 (已修复) ---
@router.get("/admin/logout")
async def admin_logout():
    """管理员登出"""
    # 1. 创建重定向对象
    response = RedirectResponse(url="/", status_code=303)
    
    # 2. 在该对象上删除 Cookie
    response.delete_cookie(key="admin_key", path="/")
    
    # 3. 返回对象
    return response

# --- 添加分类 ---
@router.post("/admin/add_category")
async def add_category(
    name: str = Form(...),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_cookie)
):
    """添加新分类"""
    # 检查分类是否已存在
    existing_category = db.query(Category).filter(Category.name == name).first()
    if existing_category:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    
    # 创建新分类
    new_category = Category(name=name)
    db.add(new_category)
    db.commit()
    
    return RedirectResponse(url="/admin/dashboard", status_code=303)

# --- 删除分类 ---
@router.post("/admin/delete_category/{category_id}")
async def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_cookie)
):
    """删除分类，将该分类下的游戏默认归到游戏分类"""
    # 不能删除默认分类
    if category_id == 1:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    
    # 查找分类
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    
    # 将该分类下的游戏默认归到游戏分类（ID=1）
    db.query(Game).filter(Game.category_id == category_id).update({"category_id": 1})
    
    # 删除分类
    db.delete(category)
    db.commit()
    
    return RedirectResponse(url="/admin/dashboard", status_code=303)

# --- 刷新游戏库 ---
@router.get("/admin/refresh")
async def admin_refresh_library(
    _: bool = Depends(verify_admin_cookie)
):
    """刷新游戏库"""
    sync_games_from_folder()
    return RedirectResponse(url="/admin/dashboard", status_code=303)