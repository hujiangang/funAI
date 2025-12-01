import os
from sqlalchemy.orm import Session
import re # 导入正则表达式模块

# 从同级目录的 database.py 导入 SessionLocal 和 Game 模型
from database import SessionLocal, Game

# --- 文件同步逻辑 ---
def sync_games_from_folder():
    db = SessionLocal()
    folder = "games_repo"
    if not os.path.exists(folder):
        os.makedirs(folder)
        return

    print(f"🔄 正在扫描 {folder}...")
    # 扫描所有 .html 文件，包括上传的和手动放入的
    files = [f for f in os.listdir(folder) if f.endswith(".html")]
    
    for filename in files:
        path = os.path.join(folder, filename)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        existing = db.query(Game).filter(Game.filename == filename).first()
        
        if not existing:
            # 优先从 HTML 的 <title> 标签中提取标题
            title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
            else:
                # 如果没有 <title> 标签，再用文件名作为备选方案
                title = filename.replace(".html", "").replace("_", " ").title()

            new_game = Game(title=title, description="暂无介绍", filename=filename, html_code=content, category_id=1)
            db.add(new_game)
        else:
            # 游戏已存在，仅当文件内容有变化时才更新数据库中的 html_code
            # 这样可以避免不必要的数据库写入，并且不会覆盖上传时填写的标题等信息
            if existing.html_code != content: 
                existing.html_code = content
    
    db.commit()
    db.close()
    print("✅ 同步完成！")