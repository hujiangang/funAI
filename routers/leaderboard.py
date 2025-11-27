from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

# 从父级目录导入数据库和Game模型
from database import get_db, Game

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request, db: Session = Depends(get_db)):
    """获取本周排行榜，按评分和查看次数排序"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

# 从父级目录导入数据库和Game模型
from database import get_db, Game

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request, db: Session = Depends(get_db)):
    """获取本周排行榜，按评分和查看次数排序"""
    # 计算本周的开始时间（周一）
    now = datetime.utcnow()
    days_since_monday = now.weekday()
    week_start = now - timedelta(days=days_since_monday, hours=now.hour, minutes=now.minute, 
                               seconds=now.second, microseconds=now.microsecond)
    
    # 查询所有游戏，按评分降序排序，评分相同时按查看次数降序排序
    # 限制只返回前10个游戏
    games = db.query(Game).order_by(
        Game.rating.desc(),
        Game.views.desc()
    ).limit(10).all()
    
    # 返回排行榜页面
    return templates.TemplateResponse("leaderboard.html", {
        "request": request,
        "games": games
    })