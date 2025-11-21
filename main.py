import os
import uuid
import uvicorn
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, Session, declarative_base

# --- 1. 数据库配置 ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./games.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# 更新后的模型：增加了 ai_model, prompt, author
class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    filename = Column(String, unique=True)
    html_code = Column(Text)
    
    # 新增字段
    author = Column(String, default="匿名玩家")
    ai_model = Column(String, default="Unknown") # 例如 GPT-4o
    prompt = Column(Text, default="")            # 提示词
    
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 2. 文件同步逻辑 (保持不变) ---
def sync_games_from_folder():
    db = SessionLocal()
    folder = "games_repo"
    if not os.path.exists(folder):
        os.makedirs(folder)
        return

    print(f"🔄 正在扫描 {folder}...")
    files = [f for f in os.listdir(folder) if f.endswith(".html")]
    
    for filename in files:
        path = os.path.join(folder, filename)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        title = filename.replace(".html", "").replace("_", " ").title()
        existing = db.query(Game).filter(Game.filename == filename).first()
        
        if not existing:
            new_game = Game(title=title, description="本地文件导入", filename=filename, html_code=content)
            db.add(new_game)
        else:
            if existing.html_code != content:
                existing.html_code = content
    
    db.commit()
    db.close()
    print("✅ 同步完成！")

@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_games_from_folder()
    yield

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# --- 3. 路由 ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    games = db.query(Game).order_by(Game.views.desc()).all()
    return templates.TemplateResponse("index.html", {"request": request, "games": games})

@app.get("/play/{game_id}", response_class=HTMLResponse)
async def play(request: Request, game_id: int, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game: return HTMLResponse("游戏未找到", 404)
    
    game.views += 1
    db.commit()
    db.refresh(game)
    return templates.TemplateResponse("play.html", {"request": request, "game": game})

# --- ⭐ 新增：显示上传页面 ---
@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

# --- ⭐ 新增：处理上传请求 ---
@app.post("/upload")
async def handle_upload(
    title: str = Form(...),
    author: str = Form(...),
    ai_model: str = Form(...),
    description: str = Form(...),
    prompt: str = Form(...),
    html_code: str = Form(...),
    db: Session = Depends(get_db)
):
    # 1. 生成一个唯一的文件名
    filename = f"upload_{uuid.uuid4().hex[:8]}.html"
    
    # 2. 保存到 games_repo 文件夹 (这样数据不仅在数据库，还在硬盘里)
    file_path = os.path.join("games_repo", filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_code)
    
    # 3. 存入数据库
    new_game = Game(
        title=title,
        author=author,
        ai_model=ai_model,
        description=description,
        prompt=prompt,
        filename=filename,
        html_code=html_code
    )
    db.add(new_game)
    db.commit()
    db.refresh(new_game)
    
    # 4. 直接跳转到玩游戏页面
    return RedirectResponse(url=f"/play/{new_game.id}", status_code=303)

@app.get("/refresh")
async def refresh_library():
    sync_games_from_folder()
    return RedirectResponse(url="/")


# --- ⭐ 修复：新增一个接口，专门只返回游戏的纯 HTML 代码 ---
# 这样 iframe src="/content/..." 就不会因为引号问题崩坏了
@app.get("/content/{game_id}", response_class=HTMLResponse)
async def game_content(game_id: int, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        return HTMLResponse("Game not found", status_code=404)
    return HTMLResponse(content=game.html_code)

# ... (if __name__ == "__main__": ...)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)