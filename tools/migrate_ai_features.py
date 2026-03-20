import sqlite3

# 连接到数据库
conn = sqlite3.connect("./games.db")
cursor = conn.cursor()

# 创建ai_categories表
try:
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ ai_categories表创建成功")
except Exception as e:
    print(f"❌ 创建ai_categories表失败: {e}")

# 检查ai_features表是否存在category_id列
cursor.execute("PRAGMA table_info(ai_features)")
columns = [column[1] for column in cursor.fetchall()]

# 添加category_id列
if 'category_id' not in columns:
    try:
        cursor.execute('ALTER TABLE ai_features ADD COLUMN category_id INTEGER')
        print("✅ category_id列添加成功")
    except Exception as e:
        print(f"❌ 添加category_id列失败: {e}")
else:
    print("ℹ️ category_id列已存在")

# 添加company_name列
if 'company_name' not in columns:
    try:
        cursor.execute('ALTER TABLE ai_features ADD COLUMN company_name TEXT')
        print("✅ company_name列添加成功")
    except Exception as e:
        print(f"❌ 添加company_name列失败: {e}")
else:
    print("ℹ️ company_name列已存在")

# 添加is_approved列（如果不存在）
if 'is_approved' not in columns:
    try:
        cursor.execute('ALTER TABLE ai_features ADD COLUMN is_approved INTEGER DEFAULT 1')
        print("✅ is_approved列添加成功")
    except Exception as e:
        print(f"❌ 添加is_approved列失败: {e}")
else:
    print("ℹ️ is_approved列已存在")

# 初始化默认分类
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
    try:
        cursor.execute('INSERT OR IGNORE INTO ai_categories (name) VALUES (?)', (category_name,))
    except Exception as e:
        print(f"❌ 插入分类 {category_name} 失败: {e}")

# 提交更改并关闭连接
conn.commit()
conn.close()

print("✅ 数据库迁移完成")