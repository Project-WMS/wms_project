#!/usr/bin/env python3
"""Công cụ dòng lệnh của dự án (giống manage.py của Django).

  python manage.py runserver [--host 0.0.0.0] [--port 8000] [--no-reload]
  python manage.py init-db [--demo] [--reset] [--yes]
  python manage.py create-admin
"""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="WMS - công cụ quản trị dự án")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("runserver", help="Chạy web server (FastAPI + Uvicorn)")
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8000)
    run.add_argument("--no-reload", action="store_true")

    init = sub.add_parser("init-db", help="Tạo/đồng bộ bảng, trigger BR06 trên PostgreSQL")
    init.add_argument("--demo", action="store_true", help="Nạp dữ liệu mẫu + tài khoản mẫu (khi CSDL chưa có tài khoản)")
    init.add_argument("--reset", action="store_true", help="XÓA SẠCH dữ liệu rồi tạo lại")
    init.add_argument("--yes", action="store_true", help="Bỏ qua bước xác nhận khi --reset")

    sub.add_parser("create-admin", help="Tạo tài khoản Admin đầu tiên")

    args = parser.parse_args()
    if args.command == "runserver":
        import uvicorn
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=not args.no_reload)
    elif args.command == "init-db":
        from scripts.init_db import run as init_run
        init_run(demo=args.demo, reset=args.reset, assume_yes=args.yes)
    elif args.command == "create-admin":
        from scripts.create_admin import run as admin_run
        admin_run()


if __name__ == "__main__":
    main()
