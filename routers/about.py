import os
import uuid
from fastapi import APIRouter, Request, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db, AboutConfig, Like

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request, db: Session = Depends(get_db)):
    """关于页面"""
    # 获取关于页面配置
    about_config = db.query(AboutConfig).first()
    if not about_config:
        # 如果没有配置，创建默认配置
        about_config = AboutConfig(
            purpose="这是一个AI游戏实验室，旨在探索AI技术在游戏开发中的应用。",
            reward_enabled=1,
            reward_image_url="",
            reward_description="感谢您的支持！"
        )
        db.add(about_config)
        db.commit()
        db.refresh(about_config)
    
    # 获取点赞数量
    like_count = db.query(Like).count()
    
    return templates.TemplateResponse(
        "about.html",
        {
            "request": request,
            "about_config": about_config,
            "like_count": like_count
        }
    )

@router.post("/api/about/like")
async def like_about(request: Request, db: Session = Depends(get_db)):
    """点赞功能"""
    # 获取用户IP地址
    client_ip = request.client.host
    
    # 检查用户是否已经点赞过
    existing_like = db.query(Like).filter(Like.ip_address == client_ip).first()
    if existing_like:
        return JSONResponse({"status": "error", "message": "您已经点赞过了"})
    
    # 添加点赞记录
    new_like = Like(ip_address=client_ip)
    db.add(new_like)
    db.commit()
    
    # 获取最新点赞数量
    like_count = db.query(Like).count()
    
    return JSONResponse({"status": "success", "like_count": like_count})

@router.get("/api/about/config")
async def get_about_config(db: Session = Depends(get_db)):
    """获取关于页面配置"""
    about_config = db.query(AboutConfig).first()
    if not about_config:
        return JSONResponse({"status": "error", "message": "配置不存在"})
    
    return JSONResponse({
        "status": "success",
        "config": {
            "id": about_config.id,
            "purpose": about_config.purpose,
            "reward_enabled": about_config.reward_enabled,
            "reward_image_url": about_config.reward_image_url,
            "reward_description": about_config.reward_description
        }
    })

@router.post("/api/about/config")
async def update_about_config(
    request: Request,
    db: Session = Depends(get_db),
    purpose: str = Form(None),
    reward_enabled: int = Form(None),
    reward_image_url: str = Form(None),
    reward_description: str = Form(None),
    reward_image_upload: UploadFile = File(None)
):
    """更新关于页面配置，支持文件上传"""
    # 处理JSON请求的情况
    if not purpose:
        try:
            data = await request.json()
            purpose = data.get("purpose")
            reward_enabled = data.get("reward_enabled")
            reward_image_url = data.get("reward_image_url")
            reward_description = data.get("reward_description")
        except Exception:
            # 如果不是JSON请求，直接返回错误
            return JSONResponse({"status": "error", "message": "无效的请求格式"})
    
    # 处理文件上传
    if reward_image_upload:
        # 确保uploads目录存在
        upload_dir = "uploads"
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        
        # 生成唯一的文件名
        file_extension = os.path.splitext(reward_image_upload.filename)[1]
        unique_filename = f"reward_{uuid.uuid4().hex[:8]}{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # 保存文件
        try:
            content = await reward_image_upload.read()
            with open(file_path, "wb") as f:
                f.write(content)
            
            # 生成文件URL
            reward_image_url = f"/uploads/{unique_filename}"
        except Exception as e:
            return JSONResponse({"status": "error", "message": f"文件上传失败：{str(e)}"})
    
    # 获取或创建关于页面配置
    about_config = db.query(AboutConfig).first()
    if not about_config:
        # 如果没有配置，创建新配置
        about_config = AboutConfig(
            purpose=purpose,
            reward_enabled=reward_enabled,
            reward_image_url=reward_image_url,
            reward_description=reward_description
        )
        db.add(about_config)
    else:
        # 更新现有配置
        if purpose is not None:
            about_config.purpose = purpose
        if reward_enabled is not None:
            about_config.reward_enabled = reward_enabled
        if reward_image_url is not None:
            about_config.reward_image_url = reward_image_url
        if reward_description is not None:
            about_config.reward_description = reward_description
    
    db.commit()
    db.refresh(about_config)
    
    return JSONResponse({
        "status": "success",
        "config": {
            "id": about_config.id,
            "purpose": about_config.purpose,
            "reward_enabled": about_config.reward_enabled,
            "reward_image_url": about_config.reward_image_url,
            "reward_description": about_config.reward_description
        }
    })
