import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.orm import sessionmaker, Session, declarative_base

# --- 1. 数据库配置 ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./games.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 分类模型
class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# 更新后的模型：增加了 ai_model, prompt, author, category
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
    category_id = Column(Integer, default=1)      # 分类ID，默认1（游戏）
    
    # 多文件游戏支持
    is_multi_file = Column(Integer, default=0)   # 0=单文件, 1=多文件(zip)
    directory_name = Column(String, default="")  # 多文件游戏的目录名
    edit_password = Column(String, default="")   # 编辑密码
    
    rating = Column(Float, default=0)            # 综合平均分
    rating_total = Column(Integer, default=0)    # 总评分
    rating_count = Column(Integer, default=0)    # 评分次数
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

# AI分类模型
class AICategory(Base):
    __tablename__ = "ai_categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# AI功能模型
class AIFeature(Base):
    __tablename__ = "ai_features"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, unique=True, index=True)
    url = Column(String)
    description = Column(Text)
    category_id = Column(Integer)
    company_name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_approved = Column(Integer, default=1)  # 0=待审核, 1=已通过, 2=已拒绝，默认直接通过

# 关于页面配置模型
class AboutConfig(Base):
    __tablename__ = "about_config"
    id = Column(Integer, primary_key=True, index=True)
    purpose = Column(Text, default="")  # 设计初衷
    reward_enabled = Column(Integer, default=1)  # 打赏开关：0=关闭, 1=开启
    reward_image_url = Column(String, default="")  # 打赏图片URL
    reward_description = Column(String, default="感谢您的支持！")  # 打赏描述
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 点赞模型
class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, index=True)  # 用户IP地址，用于防刷
    created_at = Column(DateTime, default=datetime.utcnow)

# 确保数据库表在模块导入时被创建
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()