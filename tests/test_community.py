"""Isolated integration tests: never modify the user's database or uploads."""
import io
import os
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

TEMP = tempfile.TemporaryDirectory(prefix="funai-tests-")
os.environ["DATABASE_URL"] = "sqlite:///" + (Path(TEMP.name)/"test.db").as_posix()
os.environ["WORKS_DIR"] = str(Path(TEMP.name)/"works")
os.environ["APP_SECRET"] = "test-secret-only-not-for-production"
os.environ["ADMIN_PASSWORD"] = "test-admin-password-not-for-production"
import httpx
from main import app, limits
from admin_main import app as admin_app
from database import SessionLocal, Game, Reaction, SiteSetting, engine

def tearDownModule():
    engine.dispose()
    TEMP.cleanup()

HTML = b'<!doctype html><html><head><title>Test</title></head><body><canvas></canvas><script>window.test=1</script></body></html>'

def archive(files):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,"w") as z:
        for name,data in files.items(): z.writestr(name,data)
    return buffer.getvalue()

class CommunityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        limits.clear()
        self.lifespan=app.router.lifespan_context(app)
        await self.lifespan.__aenter__()
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver")
        self.admin=httpx.AsyncClient(transport=httpx.ASGITransport(app=admin_app),base_url="http://adminserver")
        await self.client.get("/")

    async def asyncTearDown(self):
        await self.client.aclose(); await self.admin.aclose()
        await self.lifespan.__aexit__(None,None,None)

    async def upload(self,data=HTML,name="demo.html",title="测试作品",category="1"):
        return await self.client.post("/upload",data={"title":title,"author":"Test","description":"Interactive test","category_id":category},files={"file":(name,data)})

    async def published(self):
        r=await self.upload(); self.assertEqual(r.status_code,200,r.text)
        game_id=r.json()["id"]
        r=await self.client.post(f"/publish/{game_id}",json={"tested":True})
        self.assertEqual(r.status_code,200,r.text)
        return game_id

    async def login(self):
        r=await self.admin.post("/admin/login",data={"password":os.environ["ADMIN_PASSWORD"]})
        self.assertEqual(r.status_code,303)
        r=await self.admin.get("/admin/dashboard")
        self.assertEqual(r.status_code,200,r.text)
        return re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)

    async def test_pages_and_public_admin_isolation(self):
        for path in ("/","/upload","/about","/privacy","/?sort=latest","/?category_id=999","/?q=nothing-found"):
            r=await self.client.get(path); self.assertEqual(r.status_code,200,r.text)
        for path in ("/admin/login","/admin/dashboard","/refresh","/uploads_list","/repo/solar_system.html","/web/ball/index.html"):
            self.assertEqual((await self.client.get(path)).status_code,404)

    async def test_draft_private_and_publish(self):
        r=await self.upload(); game_id=r.json()["id"]
        self.assertEqual((await self.client.get(f"/play/{game_id}")).status_code,200)
        listing=(await self.client.get("/api/games")).json()
        self.assertNotIn(game_id,[g["id"] for g in listing["games"]])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as other:
            self.assertEqual((await other.get(f"/play/{game_id}")).status_code,404)
            self.assertEqual((await other.get(f"/content/{game_id}")).status_code,404)
            self.assertEqual((await other.post(f"/publish/{game_id}",json={"tested":True})).status_code,404)
        self.assertEqual((await self.client.post(f"/publish/{game_id}",json={})).status_code,400)
        self.assertEqual((await self.client.post(f"/publish/{game_id}",json={"tested":True})).status_code,200)

    async def test_rating_update_and_like_toggle(self):
        game_id=await self.published()
        for score,count in [(5,1),(2,1),(4,1)]:
            r=await self.client.post(f"/rate/{game_id}",json={"rating":score})
            self.assertEqual(r.json()["rating"],score); self.assertEqual(r.json()["rating_count"],count)
        for value in (True,6,0,2.5,"5"):
            self.assertEqual((await self.client.post(f"/rate/{game_id}",json={"rating":value})).status_code,400)
        for expected in (1,0,1):
            r=await self.client.post(f"/like/{game_id}",json={})
            self.assertEqual(r.json()["likes"],expected)

    async def test_two_visitors_average(self):
        game_id=await self.published()
        await self.client.post(f"/rate/{game_id}",json={"rating":5})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as other:
            await other.get("/")
            r=await other.post(f"/rate/{game_id}",json={"rating":1})
            self.assertEqual(r.json()["rating"],3); self.assertEqual(r.json()["rating_count"],2)

    async def test_nested_zip_assets_and_sandbox(self):
        data=archive({"demo/index.html":'<html><head><script src="app.js"></script></head><body>OK</body></html>',"demo/app.js":"console.log('ok')"})
        r=await self.upload(data,"demo.zip"); self.assertEqual(r.status_code,200,r.text)
        game_id=r.json()["id"]
        content=await self.client.get(f"/content/{game_id}")
        self.assertIn("sandbox allow-scripts",content.headers["content-security-policy"])
        self.assertNotIn("allow-same-origin",content.headers["content-security-policy"])
        self.assertLess(content.text.index("funai-runtime"),content.text.index('src="app.js"'))
        base=re.search(r'<base href="([^"]+)"',content.text).group(1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as sandbox:
            asset=await sandbox.get(base+"app.js")
            self.assertEqual(asset.status_code,200); self.assertEqual(asset.headers["access-control-allow-origin"],"*")
            self.assertEqual((await sandbox.get(f"/assets/{game_id}/wrong/demo/app.js")).status_code,404)

    async def test_zip_traversal_rejected(self):
        for name in ("../escape.html","C:/escape.html","/escape.html","nested/../../escape.html","CON.txt","nested/AUX.js"):
            r=await self.upload(archive({name:HTML,"index.html":HTML}),"bad.zip")
            self.assertEqual(r.status_code,400,r.text)
        self.assertFalse((Path(TEMP.name)/"escape.html").exists())

    async def test_missing_resource_and_invalid_zip(self):
        for data,name in [(b"invalid","bad.zip"),(archive({"hello.txt":"ok"}),"missing.zip"),(b'<html><script src="missing.js"></script></html>',"missing.html"),(HTML,"run.exe")]:
            self.assertEqual((await self.upload(data,name)).status_code,400)

    async def test_source_project_rejected_build_output_accepted(self):
        data=archive({"package.json":'{"scripts":{"build":"dangerous"}}',"index.html":HTML})
        r=await self.upload(data,"source.zip"); self.assertEqual(r.status_code,400);self.assertIn("源码",r.text)
        data=archive({"project/package.json":"{}","project/dist/index.html":HTML})
        self.assertEqual((await self.upload(data,"built.zip")).status_code,200)

    async def test_empty_and_unknown_category(self):
        self.assertEqual((await self.upload(b"")).status_code,400)
        self.assertEqual((await self.upload(category="9999")).status_code,400)
        self.assertEqual((await self.upload(title=" ")).status_code,400)

    async def test_cross_origin_rejected(self):
        self.assertEqual((await self.client.post("/upload",headers={"Origin":"https://evil.example"})).status_code,403)
        self.assertEqual((await self.client.post("/like/1",headers={"Origin":"null"},json={})).status_code,403)

    async def test_admin_auth_csrf_and_categories(self):
        self.assertEqual((await self.admin.get("/admin/dashboard")).status_code,303)
        self.assertEqual((await self.admin.post("/admin/login",data={"password":"bad"})).status_code,401)
        csrf=await self.login()
        self.assertEqual((await self.admin.post("/admin/categories",data={"name":"新领域","csrf":"wrong"})).status_code,403)
        self.assertEqual((await self.admin.post("/admin/categories",data={"name":"新领域","csrf":csrf})).status_code,303)
        self.assertIn("新领域",(await self.client.get("/upload")).text)

    async def test_delete_restore_and_no_resurrection(self):
        game_id=await self.published(); csrf=await self.login()
        r=await self.admin.post(f"/admin/work/{game_id}/delete",data={"csrf":csrf}); self.assertEqual(r.status_code,303)
        self.assertEqual((await self.client.get(f"/content/{game_id}")).status_code,404)
        self.assertEqual((await self.client.get(f"/play/{game_id}")).status_code,404)
        async with app.router.lifespan_context(app):
            self.assertEqual((await self.client.get(f"/play/{game_id}")).status_code,404)
        self.assertEqual((await self.admin.post(f"/admin/work/{game_id}/restore",data={"csrf":csrf})).status_code,303)
        self.assertEqual((await self.client.get(f"/play/{game_id}")).status_code,200)

    async def test_draft_restore_stays_private(self):
        game_id=(await self.upload()).json()["id"];csrf=await self.login()
        await self.admin.post(f"/admin/work/{game_id}/delete",data={"csrf":csrf})
        await self.admin.post(f"/admin/work/{game_id}/restore",data={"csrf":csrf})
        with SessionLocal() as db: self.assertEqual(db.get(Game,game_id).status,"draft")

    async def test_ads_enable_validate_disable(self):
        csrf=await self.login()
        r=await self.admin.post("/admin/settings",data={"csrf":csrf,"ads_enabled":"1","ads_client":"bad"})
        self.assertEqual(r.status_code,400)
        config={"csrf":csrf,"ads_enabled":"1","ads_client":"ca-pub-1234567890123456","ads_slot":"1234567890"}
        self.assertEqual((await self.admin.post("/admin/settings",data=config)).status_code,303)
        self.assertIn('id="allow-ads"',(await self.client.get("/")).text)
        self.assertIn("pub-1234567890123456",(await self.client.get("/ads.txt")).text)
        config["ads_enabled"]="0"; await self.admin.post("/admin/settings",data=config)
        self.assertNotIn('id="allow-ads"',(await self.client.get("/")).text)
        self.assertEqual((await self.client.get("/ads.txt")).text,"")

    async def test_search_category_and_latest(self):
        r=await self.upload(title="DistinctSearchWork",category="2"); game_id=r.json()["id"]
        await self.client.post(f"/publish/{game_id}",json={"tested":True})
        data=(await self.client.get("/api/games?q=DistinctSearchWork&category_id=2&sort=latest")).json()
        self.assertEqual([g["id"] for g in data["games"]],[game_id])
        self.assertEqual((await self.client.get("/api/games?q=DistinctSearchWork&category_id=3")).json()["total"],0)

    async def test_invalid_json_is_actionable(self):
        game_id=await self.published()
        for body in ("{broken", "[]", "null"):
            r=await self.client.post(f"/rate/{game_id}",content=body,headers={"Content-Type":"application/json"})
            self.assertEqual(r.status_code,400,r.text)

    async def test_admin_all_views_and_logout(self):
        csrf=await self.login()
        for tab in ("works","categories","ads","trash"):
            r=await self.admin.get("/admin/dashboard?tab="+tab)
            self.assertEqual(r.status_code,200,r.text)
        await self.admin.post("/admin/logout",data={"csrf":csrf})
        self.assertEqual((await self.admin.get("/admin/dashboard")).status_code,303)

    async def test_archive_limits_and_symlink(self):
        excessive=archive({f"f{i}.txt":"a" for i in range(1501)})
        self.assertEqual((await self.upload(excessive,"large.zip")).status_code,400)
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,"w") as z:
            link=zipfile.ZipInfo("shortcut.html")
            link.create_system=3; link.external_attr=0o120777 << 16
            z.writestr(link,"../../outside")
            z.writestr("index.html",HTML)
        self.assertEqual((await self.upload(buffer.getvalue(),"link.zip")).status_code,400)

    async def test_deleted_resources_unavailable(self):
        game_id=await self.published()
        r=await self.client.get(f"/content/{game_id}")
        base=re.search(r'<base href="([^"]+)"',r.text).group(1)
        self.assertEqual((await self.client.get(base+"index.html")).status_code,200)
        csrf=await self.login();await self.admin.post(f"/admin/work/{game_id}/delete",data={"csrf":csrf})
        self.assertEqual((await self.client.get(base+"index.html")).status_code,404)

    async def test_upload_rate_limit(self):
        for _ in range(6):
            await self.client.post("/upload")
        self.assertEqual((await self.client.post("/upload")).status_code,429)

if __name__=="__main__":
    unittest.main()
