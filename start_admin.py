"""Interactive local launcher without storing an administrator password on disk."""
import getpass
import os

if __name__ == "__main__":
    if not os.getenv("ADMIN_PASSWORD"):
        password = getpass.getpass("设置本次后台管理密码（至少 16 位，输入不回显）: ")
        if len(password) < 16:
            raise SystemExit("密码长度不足，后台未启动。")
        os.environ["ADMIN_PASSWORD"] = password
    import uvicorn
    uvicorn.run("admin_main:app", host="127.0.0.1", port=8001)
