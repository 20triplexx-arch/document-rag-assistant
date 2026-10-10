"""仅在本机创建真实管理员；不覆盖同名账号，不保存明文密码。"""
from __future__ import annotations

import argparse
from pathlib import Path
import secrets

from study_rag.store import Store


def main():
    parser = argparse.ArgumentParser(description="本机管理员初始化（不可通过网页注册管理员）")
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()
    password = secrets.token_urlsafe(18)
    store = Store(Path(__file__).resolve().parent / "output" / "users.sqlite3")
    try:
        user = store.create_admin(args.username, password)
    except ValueError as error:
        parser.exit(1, f"未创建：{error}（没有覆盖或提升现有账号）\n")
    print(f"管理员已创建：{user['username']}")
    print(f"登录密码（仅本次显示，数据库只存哈希）：{password}")
    print("权限：查看管理概览；仍不能读取、删除其他人的私有讨论。")


if __name__ == "__main__":
    main()
