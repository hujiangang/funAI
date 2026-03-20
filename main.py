import uvicorn
from contextlib import asynccontextmanager
import os
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# 导入工具函数和路由
from utils import sync_games_from_folder
# 导入路由
from routers import games, leaderboard, admin, ai_navigation, about  # 添加admin、ai_navigation和about导入

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在应用启动时运行文件同步逻辑
    sync_games_from_folder()
    yield

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# 配置静态文件服务
# 确保uploads目录存在
uploads_dir = os.path.join(os.getcwd(), "uploads")
if not os.path.exists(uploads_dir):
    os.makedirs(uploads_dir)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/web", StaticFiles(directory="web"), name="web")

# 包含游戏路由
app.include_router(games.router)
# 包含排行榜路由
app.include_router(leaderboard.router)
app.include_router(admin.router)  # 添加admin路由
app.include_router(ai_navigation.router)  # 添加ai_navigation路由
app.include_router(about.router)  # 添加about路由

# 添加uploads文件列表端点
@app.get("/uploads_list", response_class=HTMLResponse)
async def uploads_list(request: Request):
    """显示uploads目录中的文件列表"""
    uploads_dir = os.path.join(os.getcwd(), "uploads")
    files = []
    
    # 获取uploads目录中的所有文件
    for filename in os.listdir(uploads_dir):
        file_path = os.path.join(uploads_dir, filename)
        if os.path.isfile(file_path):
            # 获取文件信息
            file_stats = os.stat(file_path)
            file_size = file_stats.st_size
            modified_time = file_stats.st_mtime
            
            # 格式化文件大小
            def format_size(size_bytes):
                if size_bytes == 0:
                    return "0 B"
                size_names = ["B", "KB", "MB", "GB"]
                i = 0
                while size_bytes >= 1024 and i < len(size_names) - 1:
                    size_bytes /= 1024
                    i += 1
                return f"{size_bytes:.2f} {size_names[i]}"
            
            # 格式化修改时间
            formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(modified_time))
            
            # 获取文件扩展名
            file_extension = os.path.splitext(filename)[1].lower()[1:] if os.path.splitext(filename)[1] else ""
            
            # 添加文件信息到列表
            files.append({
                "name": filename,
                "size": format_size(file_size),
                "modified": formatted_time,
                "extension": file_extension,
                "url": f"/uploads/{filename}"
            })
    
    # 按修改时间倒序排序
    files.sort(key=lambda x: x["modified"], reverse=True)
    
    return templates.TemplateResponse(
        "uploads_list.html",
        {
            "request": request,
            "files": files,
            "current_year": time.strftime("%Y")
        }
    )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)