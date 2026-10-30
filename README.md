# funAI · 灵感实验室

分享 AI 生成的物理/数学演示动画、可视化实验和创意游戏。FastAPI + SQLite + Jinja2 + 本地 CSS/JavaScript，无前端构建步骤。

## 本地启动

在项目目录执行（Python 3.11+）：

```powershell
python -m pip install -r requirements.txt
python main.py
```

前台：<http://127.0.0.1:8000>。

后台是独立应用，另开一个终端：

```powershell
python start_admin.py
```

按终端提示输入至少 16 位管理密码（输入不回显），打开 <http://127.0.0.1:8001>。也可以通过进程环境变量 `ADMIN_PASSWORD` 配置，再运行 `python admin_main.py`。没有默认密码，未配置有效密码时后台拒绝启动。后台会话使用随机令牌，8 小时过期；服务重启需要重新登录。当前内存会话设计要求后台使用单进程。

## 已实现

- **发现广场**：全部作品、分类筛选、搜索、分页；热度、最新、高分排序。热度为 `浏览次数 + 点赞数 × 8 + 评分人数 × 5`。
- **视觉**：深石墨 / 深海蓝 / 浅雾白三种持久化主题；Canvas 动态轨道主视觉和按作品 ID 生成的装饰封面；适配移动端、键盘焦点、减少动态效果偏好。卡片封面是程序生成的装饰图，**不是作品截图**。
- **上传**：HTML/HTM 单文件、粘贴 HTML、ZIP 静态目录；分类、作者、模型、介绍、提示词。
- **检查与预览**：先生成私有草稿；验证格式、入口和 HTML 直接引用的本地资源；显示外部资源提醒；点击运行后接收脚本错误、资源加载失败、Promise 异常及心跳状态。作者实际操作并确认后发布。
- **互动**：点赞可取消，1–5 星评分可修改。匿名随机浏览器 Cookie 对同一作品只保留一份评分；事务保护计数一致性。这是浏览器级去重，不是实名账号防刷，清理 Cookie 或换设备仍可能重复投票。
- **独立后台**：作品搜索、下架至回收站、恢复、新增分类、AdSense 开关及 ID 配置。草稿恢复后仍是草稿。
- **广告**：默认关闭；配置开启后在发现页列表下方展示响应式广告位，访客允许加载才请求 Google 脚本；自动输出 `/ads.txt`。拒绝偏好可在隐私页重置。

## 上传规范与隔离边界

1. 单文件最大 50 MB，ZIP 最多 1500 项，解压后最多 200 MB。反向代理必须同时限制请求体大小，拦截流式超限请求。
2. ZIP 支持外层文件夹，需包含 `index.html`，资源使用相对路径。React/Vite 等项目先本地构建，上传 `dist` / `build` 产物。服务器**不会安装依赖或执行上传者的 shell/npm/Python 脚本**。RAR、7z、可执行程序及压缩 Unity `.gz/.br` 产物当前不支持。
3. 拒绝路径穿越、绝对路径、符号链接、危险后缀；忽略隐藏目录、`node_modules` 和 macOS 元数据。
4. 作品 iframe 只开放脚本、指针锁定、全屏；响应同时设置 CSP sandbox，即使直接打开上传 HTML 也受到沙箱约束。没有 `allow-same-origin`，无法访问主站 DOM/Cookie/localStorage。依赖同源存储、摄像头、弹窗、跨源隔离线程等能力的作品需要适配。
5. 草稿资源使用签名能力 URL，浏览器沙箱无需携带登录 Cookie。持有该资源链接的人可以访问对应草稿资源，请勿分享未公开草稿的资源链接。作品下架后入口和资源均停止访问。
6. 静态检查只覆盖 HTML 直接引用，不完整解析 CSS/JS 动态依赖；试运行只覆盖实际执行的路径。跨域脚本可能仅给出 `Script error`。诊断是尽力检查，不是恶意代码审计，也不能保证页面永不卡死。
7. 首次启动会生成 `.runtime/app-secret`。应持久化并备份此文件；更换它会让原草稿归属和匿名互动标识失效。生产环境推荐显式配置长期稳定的 `APP_SECRET`（至少 32 字符）。

## 数据与兼容

保留原 `games.db` 和 `games_repo`。启动时自动新增必要列和表，不覆盖作品标题、作者、已有评分与浏览数据。默认补充分类，不擅自重分类原作品。原有单文件作品通过 `/content/{id}` 继续运行。

旧 `routers/`、导航/打赏模板和工具保留在仓库作为历史实现，**新入口不挂载这些路由**。旧 `/refresh`、`/repo`、原始上传目录列表、前台 `/admin` 等入口不再开放。也不会启动时自动同步目录，避免已删除作品重新出现。

新增上传保存在 `games_repo/<随机 ID>/`，先进入 draft。数据库 `status` 区分 `draft / published / deleted`。回收站为可恢复下架，**不做永久磁盘删除**。正式迁移前备份数据库和作品目录；运行中的 SQLite 使用数据库备份 API，避免直接复制正在写入的数据库。

可用环境变量：

| 变量 | 用途 |
| --- | --- |
| `DATABASE_URL` | 默认 `sqlite:///./games.db`，当前事务实现针对 SQLite |
| `WORKS_DIR` | 默认 `games_repo` |
| `APP_SECRET` | 持久化签名密钥，生产环境至少 32 字符 |
| `ADMIN_PASSWORD` | 后台管理密码，至少 16 字符 |
| `COOKIE_SECURE=1` | HTTPS 部署必须开启；本地 HTTP 留空 |
| `APP_ENV=production` | 启动时强制校验签名密钥及 Secure Cookie 配置 |

## 部署

提供 `deploy/nginx.conf.example` 作为 HTTPS 反向代理模板。替换域名、证书路径后使用；前台监听 127.0.0.1:8000，后台保持 127.0.0.1:8001，通过 SSH 隧道或受控内网访问。不要把仓库根目录、`games_repo`、数据库、`.runtime` 直接映射为 Nginx 静态目录，否则会绕过访问校验。

```text
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
python -m uvicorn admin_main:app --host 127.0.0.1 --port 8001 --workers 1
```

正式环境配置 `APP_ENV=production`、`APP_SECRET`、`COOKIE_SECURE=1`；本机后台 HTTP 进程可单独使用本地开发配置，或通过 HTTPS 管理入口访问后再开启 Secure Cookie。前台当前限流存于内存，适用于单进程；大规模或多实例部署应换用 Redis 限流及共享会话。配置进程守护、定时备份、磁盘容量监控及部署环境中的依赖安全更新。

AdSense 实际展示需使用自己的发布商 ID、广告单元 ID 和已审核站点，无法通过本地代码测试代替账户审核。当前本地“允许加载”控件不等同于 Google 认证 CMP。面向 EEA、英国、瑞士投放时应先配置适用的认证 CMP，可使用 AdSense 的 Privacy & messaging 配置。参考 [Google AdSense 广告代码](https://support.google.com/adsense/answer/9183460?hl=en) 和 [Google 同意管理要求](https://support.google.com/adsense/answer/13554116?hl=en)。

## 验证

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m compileall -q main.py community.py admin_main.py database.py upload_service.py
node --check static/app.js
```

集成测试使用临时 SQLite 和临时作品目录，不操作真实作品。覆盖上传、ZIP 攻击路径、草稿隔离、沙箱资源、发布、评分更新、点赞、分类查询、独立后台身份/CSRF、删除恢复和广告配置。

本轮浏览器自动化因工具无法可靠确定 Windows 浏览器 URL 而被停止，尚未完成真实 Chrome 的视觉与交互验收。上线前请在本地 Chrome 检查桌面/移动宽度、上传试运行、全屏、浏览器错误提示与后台流程。当前没有发布到公网，也未接入真实 AdSense 账户。
