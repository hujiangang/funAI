import uvicorn
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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

# 配置静态文件服务
# 确保uploads目录存在
uploads_dir = os.path.join(os.getcwd(), "uploads")
if not os.path.exists(uploads_dir):
    os.makedirs(uploads_dir)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# 包含游戏路由
app.include_router(games.router)
# 包含排行榜路由
app.include_router(leaderboard.router)
app.include_router(admin.router)  # 添加admin路由
app.include_router(ai_navigation.router)  # 添加ai_navigation路由
app.include_router(about.router)  # 添加about路由

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)