import sqlite3

# 连接到数据库
conn = sqlite3.connect("./games.db")
cursor = conn.cursor()

# 查询所有AI功能
cursor.execute('SELECT id, title, url, company_name, category_id, is_approved FROM ai_features')
features = cursor.fetchall()

print("数据库中的AI功能:")
print("ID | 标题 | URL | 公司名 | 分类ID | 是否通过审核")
print("---|------|-----|--------|--------|------------")
for feature in features:
    print(f"{feature[0]} | {feature[1]} | {feature[2]} | {feature[3]} | {feature[4]} | {feature[5]}")

# 查询所有分类
cursor.execute('SELECT id, name FROM ai_categories')
categories = cursor.fetchall()

print("\n数据库中的分类:")
print("ID | 名称")
print("---|------")
for category in categories:
    print(f"{category[0]} | {category[1]}")

# 关闭连接
conn.close()