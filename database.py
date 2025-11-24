import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.orm import sessionmaker, Session, declarative_base

# --- 1. 数据库配置 ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./games.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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
    
    rating = Column(Float, default=0)            # 综合平均分
    rating_total = Column(Integer, default=0)    # 总评分
    rating_count = Column(Integer, default=0)    # 评分次数
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

# 确保数据库表在模块导入时被创建
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()