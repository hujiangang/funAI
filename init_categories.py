from database import SessionLocal, Category

def init_categories():
    db = SessionLocal()
    try:
        # 检查是否已存在分类
        existing_categories = db.query(Category).count()
        if existing_categories == 0:
            # 创建默认分类
            default_category = Category(name="游戏")
            db.add(default_category)
            db.commit()
            print("✅ 默认分类 '游戏' 已创建")
        else:
            print("✅ 分类已存在，跳过初始化")
    finally:
        db.close()

if __name__ == "__main__":
    init_categories()
