import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI
# from fastapi.staticfiles import StaticFiles # 原始代码中未使用，故移除

# 导入工具函数和路由
from utils import sync_games_from_folder
from routers import games

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在应用启动时运行文件同步逻辑
    sync_games_from_folder()
    yield

app = FastAPI(lifespan=lifespan)

# 如果有静态文件，可以取消注释并配置
# app.mount("/static", StaticFiles(directory="static"), name="static")

# 包含游戏路由
app.include_router(games.router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
