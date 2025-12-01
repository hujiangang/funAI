from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import re
import urllib.parse
import requests
from urllib.parse import urlparse

from database import get_db, AIFeature, AICategory

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# 初始化默认分类
async def init_default_categories(db: Session):
    """初始化默认分类"""
    default_categories = [
        "📝 文本生成",
        "🎨 图像生成",
        "🎤 语音交互",
        "💻 代码开发",
        "📊 数据分析",
        "🎬 视频编辑",
        "🎵 音乐生成",
        "🗿 3D建模",
        "🔍 其他"
    ]
    
    for category_name in default_categories:
        existing_category = db.query(AICategory).filter(AICategory.name == category_name).first()
        if not existing_category:
            new_category = AICategory(name=category_name)
            db.add(new_category)
    db.commit()

# 从URL提取公司名
async def extract_company_name(url: str):
    """从URL提取公司名"""
    try:
        # 解析URL
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # 移除www.
        if domain.startswith("www."):
            domain = domain[4:]
        
        # 提取主域名
        main_domain = domain.split(".")[-2] if len(domain.split(".")) > 1 else domain
        
        # AI相关公司域名映射
        company_mapping = {
            "openai": "OpenAI",
            "deepseek": "DeepSeek",
            "anthropic": "Anthropic",
            "google": "Google",
            "microsoft": "Microsoft",
            "amazon": "Amazon",
            "github": "GitHub",
            "midjourney": "Midjourney",
            "canva": "Canva",
            "deepcode": "DeepCode",
            "sourcegraph": "Sourcegraph",
            "bytedance": "字节",
            "baidu": "百度",
            "tencent": "腾讯",
            "alibaba": "阿里巴巴",
            "netease": "网易",
            "bilibili": "哔哩哔哩",
            "zhihu": "知乎",
            "jianshu": "简书",
            "medium": "Medium",
            "gitlab": "GitLab",
            "bitbucket": "Bitbucket",
            "stackoverflow": "Stack Overflow",
            "quora": "Quora",
            "reddit": "Reddit",
            "discord": "Discord",
            "slack": "Slack",
            "zoom": "Zoom",
            "teams": "Microsoft Teams",
            "whatsapp": "WhatsApp",
            "telegram": "Telegram",
            "signal": "Signal",
            "line": "Line"
        }
        
        # 返回映射的公司名或默认值
        return company_mapping.get(main_domain.lower(), main_domain.capitalize())
    except Exception as e:
        # 出错时返回默认值
        return "未知公司"

# 检查链接有效性
async def check_url_validity(url: str):
    """检查链接有效性"""
    try:
        # 基本URL格式验证
        parsed_url = urlparse(url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            return False
        
        # 知名AI网站白名单，直接返回有效
        trusted_domains = [
            "openai.com", "chat.openai.com",
            "deepseek.com", "chat.deepseek.com",
            "anthropic.com", "claude.ai",
            "doubao.com", "www.doubao.com",
            "baidu.com", "wenxin.baidu.com",
            "tencent.com", "hunyuan.tencent.com",
            "bytedance.com", "www.bytedance.com"
        ]
        
        domain = parsed_url.netloc
        if domain in trusted_domains or any(domain.endswith(f".{trusted}") for trusted in trusted_domains):
            return True
        
        # 尝试HEAD请求，超时时间增加到10秒
        try:
            response = requests.head(url, timeout=10, allow_redirects=True, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            })
            return response.status_code < 400
        except Exception:
            # HEAD请求失败，尝试GET请求但只获取前1000字节
            try:
                response = requests.get(url, timeout=10, allow_redirects=True, stream=True, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                })
                response.raw.read(1000)
                return response.status_code < 400
            except Exception:
                return False
    except Exception as e:
        return False

@router.get("/ai_navigation", response_class=HTMLResponse)
async def ai_navigation(request: Request, db: Session = Depends(get_db)):
    """AI导航页面"""
    # 初始化默认分类
    await init_default_categories(db)
    
    # 从数据库获取所有分类
    categories = db.query(AICategory).all()
    
    # 从数据库获取所有已通过审核的AI功能
    ai_features = db.query(AIFeature).filter(AIFeature.is_approved == 1).all()
    
    # 按分类分组
    categories_with_features = []
    for category in categories:
        # 获取该分类下的所有AI功能
        features = [feature for feature in ai_features if feature.category_id == category.id]
        if features:
            categories_with_features.append({
                "id": category.id,
                "name": category.name,
                "features": features
            })
    
    return templates.TemplateResponse("ai_navigation.html", {"request": request, "categories": categories_with_features})

@router.get("/ai_navigation/refresh")
async def refresh_ai_navigation():
    """刷新AI导航页面"""
    return RedirectResponse(url="/ai_navigation")

@router.post("/ai_navigation/add_feature")
async def handle_add_ai_feature(
    title: str = Form(...),
    url: str = Form(...),
    description: str = Form(...),
    category_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """处理增加AI功能的表单提交"""
    # 检查是否重复（标题或URL）
    existing_feature = db.query(AIFeature).filter((AIFeature.title == title) | (AIFeature.url == url)).first()
    if existing_feature:
        return JSONResponse({"success": False, "message": "该AI功能已存在或URL已被使用"})
    
    # 检查链接有效性
    is_valid = await check_url_validity(url)
    if not is_valid:
        return JSONResponse({"success": False, "message": "链接无效，请检查URL是否正确"})
    
    # 提取公司名
    company_name = await extract_company_name(url)
    
    # 创建新的AI功能，默认已审核
    new_feature = AIFeature(
        title=title,
        url=url,
        description=description,
        category_id=category_id,
        company_name=company_name,
        is_approved=1  # 默认已审核
    )
    
    # 保存到数据库
    db.add(new_feature)
    db.commit()
    db.refresh(new_feature)
    
    return JSONResponse({"success": True, "message": "AI链接已成功添加"})

# 分类管理路由
@router.post("/ai_navigation/add_category")
async def add_category(
    name: str = Form(...),
    db: Session = Depends(get_db)
):
    """添加新分类"""
    # 检查是否重复
    existing_category = db.query(AICategory).filter(AICategory.name == name).first()
    if existing_category:
        return JSONResponse({"success": False, "message": "该分类已存在"})
    
    # 创建新分类
    new_category = AICategory(name=name)
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    
    return JSONResponse({"success": True, "message": "分类已成功添加"})

@router.post("/ai_navigation/delete_category/{category_id}")
async def delete_category(
    category_id: int,
    db: Session = Depends(get_db)
):
    """删除分类"""
    # 检查分类是否存在
    category = db.query(AICategory).filter(AICategory.id == category_id).first()
    if not category:
        return JSONResponse({"success": False, "message": "分类不存在"})
    
    # 删除分类
    db.delete(category)
    db.commit()
    
    return JSONResponse({"success": True, "message": "分类已成功删除"})

@router.get("/ai_navigation/categories")
async def get_categories(db: Session = Depends(get_db)):
    """获取所有分类"""
    # 初始化默认分类
    await init_default_categories(db)
    
    # 从数据库获取所有分类
    categories = db.query(AICategory).all()
    
    # 返回分类列表
    return [{"id": category.id, "name": category.name} for category in categories]

@router.get("/ai_navigation/admin", response_class=HTMLResponse)
async def ai_navigation_admin(request: Request, db: Session = Depends(get_db)):
    """AI导航管理页面"""
    try:
        # 初始化默认分类
        await init_default_categories(db)
        
        # 从数据库获取所有分类
        categories = db.query(AICategory).all()
        
        # 从数据库获取所有AI功能
        ai_features = db.query(AIFeature).all()
        
        return templates.TemplateResponse("ai_navigation_admin.html", {
            "request": request, 
            "categories": categories,
            "ai_features": ai_features
        })
    except Exception as e:
        return f"<h1>错误</h1><p>{str(e)}</p>"

@router.get("/ai_navigation/get_feature/{feature_id}")
async def get_feature(feature_id: int, db: Session = Depends(get_db)):
    """获取AI功能详情"""
    feature = db.query(AIFeature).filter(AIFeature.id == feature_id).first()
    if not feature:
        return {"error": "AI功能不存在"}
    
    return {
        "id": feature.id,
        "title": feature.title,
        "url": feature.url,
        "company_name": feature.company_name,
        "category_id": feature.category_id,
        "description": feature.description
    }

@router.post("/ai_navigation/update_feature/{feature_id}")
async def update_feature(
    feature_id: int,
    title: str = Form(...),
    url: str = Form(...),
    company_name: str = Form(...),
    category_id: int = Form(...),
    description: str = Form(...),
    db: Session = Depends(get_db)
):
    """更新AI功能"""
    # 检查AI功能是否存在
    feature = db.query(AIFeature).filter(AIFeature.id == feature_id).first()
    if not feature:
        return JSONResponse({"success": False, "message": "AI功能不存在"})
    
    # 检查标题是否已被其他AI功能使用
    existing_feature = db.query(AIFeature).filter(
        (AIFeature.title == title) & (AIFeature.id != feature_id)
    ).first()
    if existing_feature:
        return JSONResponse({"success": False, "message": "该标题已被使用"})
    
    # 检查URL是否已被其他AI功能使用
    existing_feature = db.query(AIFeature).filter(
        (AIFeature.url == url) & (AIFeature.id != feature_id)
    ).first()
    if existing_feature:
        return JSONResponse({"success": False, "message": "该URL已被使用"})
    
    # 更新AI功能
    feature.title = title
    feature.url = url
    feature.company_name = company_name
    feature.category_id = category_id
    feature.description = description
    
    # 保存到数据库
    db.commit()
    db.refresh(feature)
    
    return JSONResponse({"success": True, "message": "AI功能已成功更新"})

@router.post("/ai_navigation/delete_feature/{feature_id}")
async def delete_feature(feature_id: int, db: Session = Depends(get_db)):
    """删除AI功能"""
    # 检查AI功能是否存在
    feature = db.query(AIFeature).filter(AIFeature.id == feature_id).first()
    if not feature:
        return JSONResponse({"success": False, "message": "AI功能不存在"})
    
    # 删除AI功能
    db.delete(feature)
    db.commit()
    
    return JSONResponse({"success": True, "message": "AI功能已成功删除"})