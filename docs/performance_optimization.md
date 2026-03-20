# 游戏列表性能优化方案

当游戏数量较多时，服务器全渲染会导致页面加载慢、服务器压力大等问题。以下是几种优化方案：

## 1. 分页显示

### 后端实现
```python
# routers/games.py
@router.get("/", response_class=HTMLResponse)
async def games(request: Request, db: Session = Depends(get_db), page: int = 1, limit: int = 12):
    """游戏列表页面，支持分页"""
    # 计算偏移量
    offset = (page - 1) * limit
    
    # 查询游戏总数
    total_games = db.query(Game).count()
    
    # 查询当前页的游戏
    games = db.query(Game).offset(offset).limit(limit).all()
    
    # 计算总页数
    total_pages = (total_games + limit - 1) // limit
    
    return templates.TemplateResponse("games.html", {
        "request": request, 
        "games": games,
        "current_page": page,
        "total_pages": total_pages,
        "limit": limit
    })
```

### 前端实现
```html
<!-- 在games.html中添加分页控件 -->
<div class="flex justify-center mt-8">
    <div class="flex space-x-2">
        {% if current_page > 1 %}
            <a href="/?page={{ current_page - 1 }}" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded">上一页</a>
        {% endif %}
        
        {% for i in range(1, total_pages + 1) %}
            <a href="/?page={{ i }}" 
               class="px-4 py-2 {% if i == current_page %}bg-purple-600{% else %}bg-gray-800 hover:bg-gray-700{% endif %} rounded">
                {{ i }}
            </a>
        {% endfor %}
        
        {% if current_page < total_pages %}
            <a href="/?page={{ current_page + 1 }}" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded">下一页</a>
        {% endif %}
    </div>
</div>
```

## 2. 懒加载（无限滚动）

### 后端实现
```python
# routers/games.py
@router.get("/api/games")
async def get_games_api(db: Session = Depends(get_db), page: int = 1, limit: int = 12):
    """获取游戏列表的API，返回JSON数据"""
    offset = (page - 1) * limit
    games = db.query(Game).offset(offset).limit(limit).all()
    
    return {
        "games": [{
            "id": game.id,
            "title": game.title,
            "description": game.description,
            "filename": game.filename,
            "author": game.author,
            "ai_model": game.ai_model,
            "rating": game.rating,
            "rating_count": game.rating_count,
            "views": game.views,
            "created_at": game.created_at
        } for game in games],
        "page": page,
        "limit": limit
    }
```

### 前端实现
```html
<!-- 修改games.html，使用懒加载 -->
<div id="games-container" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
    <!-- 初始游戏列表 -->
    {% for game in games %}
        <div class="game-card">
            <!-- 游戏卡片内容 -->
        </div>
    {% endfor %}
</div>
<div id="loading" class="text-center py-4 hidden">
    <p>加载中...</p>
</div>

<script>
    let currentPage = 2;
    let isLoading = false;
    
    // 监听滚动事件
    window.addEventListener('scroll', () => {
        if (isLoading) return;
        
        // 当滚动到页面底部时加载更多
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 200) {
            loadMoreGames();
        }
    });
    
    async function loadMoreGames() {
        isLoading = true;
        document.getElementById('loading').classList.remove('hidden');
        
        try {
            const response = await fetch(`/api/games?page=${currentPage}`);
            const data = await response.json();
            
            if (data.games.length === 0) {
                // 没有更多游戏了
                window.removeEventListener('scroll', arguments.callee);
                document.getElementById('loading').textContent = '没有更多游戏了';
                return;
            }
            
            // 渲染新游戏
            const container = document.getElementById('games-container');
            data.games.forEach(game => {
                const gameCard = document.createElement('div');
                gameCard.className = 'game-card';
                gameCard.innerHTML = `
                    <!-- 游戏卡片HTML -->
                `;
                container.appendChild(gameCard);
            });
            
            currentPage++;
        } catch (error) {
            console.error('加载游戏失败:', error);
        } finally {
            isLoading = false;
            document.getElementById('loading').classList.add('hidden');
        }
    }
</script>
```

## 3. 缓存优化

### 使用FastAPI缓存
```python
# main.py
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化Redis缓存
    redis = aioredis.from_url("redis://localhost:6379")
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
    yield
    # 关闭Redis连接
    await redis.close()

# routers/games.py
from fastapi_cache.decorator import cache

@router.get("/", response_class=HTMLResponse)
@cache(expire=300)  # 缓存5分钟
async def games(request: Request, db: Session = Depends(get_db)):
    # 游戏列表逻辑
    pass
```

## 4. 静态资源优化

### 图片懒加载
```html
<img src="placeholder.jpg" data-src="{{ game.image_url }}" class="lazyload" alt="{{ game.title }}">

<script>
    // 简单的图片懒加载实现
    document.addEventListener('DOMContentLoaded', () => {
        const lazyImages = document.querySelectorAll('.lazyload');
        
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.classList.remove('lazyload');
                    observer.unobserve(img);
                }
            });
        });
        
        lazyImages.forEach(img => observer.observe(img));
    });
</script>
```

## 5. 数据库查询优化

### 添加索引
```python
# database.py
class Game(Base):
    __tablename__ = "games"
    # 其他字段
    created_at = Column(DateTime, default=datetime.utcnow, index=True)  # 添加索引
    views = Column(Integer, default=0, index=True)  # 添加索引
```

### 只查询需要的字段
```python
# 只查询需要的字段
games = db.query(Game.id, Game.title, Game.description, Game.filename).offset(offset).limit(limit).all()
```

## 6. 异步渲染

### 使用HTMX实现无刷新更新
```html
<!-- 安装htmx: <script src="https://unpkg.com/htmx.org@1.9.10"></script> -->
<div id="games-container">
    <!-- 初始游戏列表 -->
</div>
<button hx-get="/api/games?page=2" hx-target="#games-container" hx-swap="afterend" hx-indicator="#loading">
    加载更多
</button>
<div id="loading" class="htmx-indicator">加载中...</div>
```

## 优化方案对比

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| 分页显示 | 实现简单，用户可控 | 需要用户手动翻页 | 游戏数量适中 |
| 懒加载 | 自动加载，用户体验好 | 实现较复杂，依赖JavaScript | 游戏数量较多 |
| 缓存优化 | 减少数据库查询，提高响应速度 | 需要额外的缓存服务 | 游戏更新不频繁 |
| 静态资源优化 | 减少初始加载时间 | 实现较复杂 | 包含大量图片等资源 |
| 数据库查询优化 | 提高查询效率 | 需要数据库知识 | 数据库查询较慢 |
| 异步渲染 | 无刷新更新，用户体验好 | 依赖JavaScript库 | 对用户体验要求高 |

## 推荐组合方案

1. **基础优化**：分页显示 + 数据库查询优化
2. **进阶优化**：懒加载 + 静态资源优化
3. **高级优化**：缓存优化 + 异步渲染

根据实际情况选择合适的优化方案，或者组合使用多种方案，以达到最佳的性能优化效果。