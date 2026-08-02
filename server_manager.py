#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""心履 服务器管理工具
功能：管理 Cloudflare Tunnel、检测公网域名状态、查看访问记录、管理 waitress 服务器。
用法：python server_manager.py
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
CLOUDFLARED = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
TUNNEL_TOKEN = r"C:\ProgramData\cloudflared\token"
DOMAIN = "https://xin-lv.com"
SERVICE_NAME = "cloudflared"
WAITRESS_PORT = 8000


def _run(cmd, capture=True, shell=False):
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            cmd if isinstance(cmd, list) else cmd,
            capture_output=capture, text=True, shell=shell, timeout=30)
        return r.returncode, r.stdout.strip() if r.stdout else "", r.stderr.strip() if r.stderr else ""
    except subprocess.TimeoutExpired:
        return -1, "", "超时"
    except FileNotFoundError:
        return -1, "", f"找不到命令：{cmd}"


# ==================== Cloudflare Tunnel ====================

def tunnel_status():
    """查看 Cloudflare Tunnel 服务状态"""
    code, out, err = _run(["sc", "query", SERVICE_NAME])
    if "RUNNING" in out:
        print("🌐 Cloudflare Tunnel：\033[32m运行中 ✅\033[0m")
        _, ready, _ = _run(["curl", "-s", "http://127.0.0.1:20241/ready"])
        if "200" in ready:
            print("               连接状态：\033[32m正常 ✅\033[0m")
        else:
            print("               连接状态：\033[33m异常 ⚠️\033[0m")
    elif "STOPPED" in out:
        print("🌐 Cloudflare Tunnel：\033[31m已停止 ❌\033[0m")
    else:
        print(f"🌐 Cloudflare Tunnel：\033[33m未知状态\033[0m")
        if err:
            print(f"   {err}")


def tunnel_start():
    """启动 Cloudflare Tunnel 服务"""
    print("正在启动 Cloudflare Tunnel...")
    code, out, err = _run(["sc", "start", SERVICE_NAME])
    if code == 0:
        print("\033[32m✅ 启动成功\033[0m")
        time.sleep(2)
        tunnel_status()
    else:
        print(f"\033[31m❌ 启动失败：{err or out}\033[0m")


def tunnel_stop():
    """停止 Cloudflare Tunnel 服务"""
    print("正在停止 Cloudflare Tunnel...")
    code, out, err = _run(["sc", "stop", SERVICE_NAME])
    if code == 0:
        print("\033[32m✅ 已停止\033[0m")
    else:
        print(f"\033[31m❌ 停止失败：{err or out}\033[0m")


def tunnel_restart():
    """重启 Cloudflare Tunnel 服务"""
    tunnel_stop()
    time.sleep(3)
    tunnel_start()


def tunnel_info():
    """显示 Cloudflare Tunnel 详细信息"""
    print("── Cloudflare Tunnel 信息 ──")
    code, out, _ = _run(["sc", "qc", SERVICE_NAME])
    if code == 0:
        for line in out.split("\n"):
            if "BINARY_PATH_NAME" in line:
                print(f"  启动命令：{line.split(':', 1)[1].strip()}")
            elif "START_TYPE" in line:
                t = "自动" if "AUTO" in line else "手动" if "DEMAND" in line else "禁用"
                print(f"  启动类型：{t}")
    print(f"  Metrics：http://127.0.0.1:20241/metrics")
    print(f"  健康检查：http://127.0.0.1:20241/ready")
    print(f"  令牌文件：{TUNNEL_TOKEN}")
    print(f"  公网域名：{DOMAIN}")


# ==================== 域名检测 ====================

def domain_check():
    """检测公网域名状态"""
    print(f"正在检测 {DOMAIN}...")
    code, out, err = _run(["curl", "-s", "-o", "nul", "-w", "%{http_code}",
                           "--connect-timeout", "10", DOMAIN])
    if code == 0:
        http_code = out.strip()
        if http_code == "200":
            print(f"\033[32m✅ {DOMAIN} 正常访问（HTTP {http_code}）\033[0m")
        elif http_code in ("301", "302", "307", "308"):
            print(f"\033[33m⚠️  {DOMAIN} 返回 {http_code} 重定向（可能正常）\033[0m")
            # 跟进重定向
            _run(["curl", "-s", "-L", "-o", "nul", "-w", "%{http_code}",
                  "--connect-timeout", "10", DOMAIN])
        elif http_code == "400":
            print(f"\033[31m❌ {DOMAIN} 返回 400 Bad Request（配置问题）\033[0m")
        elif http_code == "502":
            print(f"\033[31m❌ {DOMAIN} 返回 502 Bad Gateway（Django 没启动？）\033[0m")
        elif http_code == "503":
            print(f"\033[31m❌ {DOMAIN} 返回 503 Service Unavailable\033[0m")
        elif http_code == "000":
            print(f"\033[31m❌ {DOMAIN} 无法连接（DNS/网络问题）\033[0m")
        else:
            print(f"\033[33m⚠️  {DOMAIN} 返回 HTTP {http_code}\033[0m")
    else:
        print(f"\033[31m❌ 检测失败：{err}\033[0m")
        print("  可能原因：curl 不可用、网络不通、域名未解析")

    # DNS 解析检测
    print("\n  DNS 解析：")
    code, out, _ = _run(["nslookup", "xin-lv.com"])
    if code == 0:
        for line in out.split("\n"):
            if "Address" in line and ":" in line:
                addr = line.split(":", 1)[1].strip()
                if addr and addr != "127.0.0.1":
                    print(f"    → {addr}")
    else:
        print("    nslookup 不可用")


# ==================== 访问记录 ====================

def show_access_logs(lines=30):
    """查看最近访问记录"""
    log_file = LOG_DIR / "server.log"
    if not log_file.exists():
        print(f"\033[33m⚠️  日志文件不存在：{log_file}\033[0m")
        return

    print(f"── 最近 {lines} 行访问记录 ──")
    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    for line in all_lines[-lines:]:
        print(line, end="")


def show_error_logs(lines=20):
    """查看错误日志"""
    for name in ["site.log", "server_err.log", "waitress.err.log"]:
        log_file = LOG_DIR / name
        if not log_file.exists():
            continue
        size = log_file.stat().st_size
        if size == 0:
            continue
        print(f"── {name}（{size / 1024:.1f}KB）──")
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        for line in all_lines[-lines:]:
            print(line, end="")
        print()


def show_request_stats():
    """统计访问量（从 server.log 中提取）"""
    log_file = LOG_DIR / "server.log"
    if not log_file.exists():
        print("  无日志数据")
        return

    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    today = datetime.now().strftime("%Y-%m-%d")
    today_count = content.count(today)
    total_starts = content.count("Serving on http")
    print(f"  今日访问（含启动）：{today_count} 次")
    print(f"  历史启动次数：{total_starts} 次")


# ==================== Waitress 管理 ====================

def waitress_status():
    """查看 waitress 服务器状态"""
    code, out, _ = _run(["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"])
    if code != 0:
        print("  waitress：\033[33m无法查询\033[0m")
        return

    running = False
    for line in out.split("\n"):
        if "waitress" in line.lower() or "manage.py" in line.lower():
            running = True
            break

    if running:
        # 检查端口
        code2, out2, _ = _run(["netstat", "-ano", "|", "findstr", f":{WAITRESS_PORT}"], shell=True)
        if code2 == 0 and out2.strip():
            print(f"  waitress（端口 {WAITRESS_PORT}）：\033[32m运行中 ✅\033[0m")
            # 找 PID
            for line in out2.split("\n"):
                if "LISTENING" in line:
                    parts = line.strip().split()
                    if parts:
                        print(f"  PID：{parts[-1]}")
        else:
            print(f"  waitress：\033[33m进程存在但端口 {WAITRESS_PORT} 未监听\033[0m")
    else:
        print(f"  waitress（端口 {WAITRESS_PORT}）：\033[31m未运行 ❌\033[0m")


def waitress_start():
    """启动 waitress 服务器"""
    print("正在启动 waitress 服务器...")
    # 先确认当前目录
    os.chdir(BASE_DIR)
    # 启动 waitress（后台运行，日志输出到文件）
    cmd = (
        f'start /B cmd /c "call venv\\Scripts\\activate '
        f'&& python -m waitress --listen=127.0.0.1:{WAITRESS_PORT} '
        f'moodsite.wsgi:application >> logs\\waitress_out.log 2>> logs\\waitress_err.log"'
    )
    code, out, err = _run(cmd, shell=True, capture=False)
    time.sleep(3)
    waitress_status()
    # 检查是否真的启动了
    code2, out2, _ = _run(["curl", "-s", "-o", "nul", "-w", "%{http_code}",
                           "http://127.0.0.1:8000/"])
    if code2 == 0 and out2.strip() == "200":
        print("\033[32m✅ waitress 启动成功，本地访问正常\033[0m")
    else:
        print(f"\033[33m⚠️  waitress 可能未正常启动（HTTP {out2}）\033[0m")
        print("  请检查 logs/waitress_err.log")


def waitress_stop():
    """停止 waitress 服务器"""
    print("正在停止 waitress 服务器...")
    # 找到占用 8000 端口的进程
    code, out, _ = _run(
        ["netstat", "-ano", "|", "findstr", f":{WAITRESS_PORT}"], shell=True)
    killed = 0
    for line in out.split("\n"):
        if "LISTENING" in line:
            parts = line.strip().split()
            pid = parts[-1] if parts else ""
            if pid:
                _run(["taskkill", "/F", "/PID", pid])
                print(f"  已杀死 PID {pid}")
                killed += 1
    # 也杀其他 python 进程（包含 waitress 的）
    code2, out2, _ = _run(["tasklist", "/FI", "IMAGENAME eq python.exe",
                           "/FO", "CSV", "/NH"])
    for line in out2.split("\n"):
        if "python" in line.lower():
            parts = line.split(",")
            if len(parts) >= 2:
                pid = parts[1].strip().strip('"')
                if pid:
                    _run(["taskkill", "/F", "/PID", pid])
                    killed += 1

    if killed > 0:
        print(f"\033[32m✅ 已停止相关进程（{killed} 个）\033[0m")
    else:
        print("\033[33m⚠️  未找到正在运行的 waitress 进程\033[0m")


def waitress_restart():
    """重启 waitress"""
    waitress_stop()
    time.sleep(2)
    waitress_start()


# ==================== 全状态概览 ====================

def overview():
    """显示服务器全状态概览"""
    print("\n" + "=" * 50)
    print("      心履 · 服务器状态概览")
    print("=" * 50)
    print(f"  当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    tunnel_status()
    waitress_status()
    print()
    print("── 公网域名 ──")
    domain_check()
    print()
    print("── 访问统计 ──")
    show_request_stats()
    print()


# ==================== 主菜单 ====================

def menu():
    """交互式菜单"""
    while True:
        print("\n" + "=" * 50)
        print("      心履 · 服务器管理工具")
        print("=" * 50)
        print("  1. 🌐 查看服务器全状态")
        print("  2. 🔄 重启 Cloudflare Tunnel")
        print("  3. 🔄 重启 waitress 服务器")
        print("  4. 🌍 检测公网域名状态")
        print("  5. 📋 查看最近访问记录")
        print("  6. ❌ 查看错误日志")
        print("  7. ℹ️  Cloudflare Tunnel 详细信息")
        print("  ---------------------------------")
        print("  s. ⏹️  停止 Cloudflare Tunnel")
        print("  q. ⏹️  停止 waitress 服务器")
        print("  0. 🚪 退出")
        print("=" * 50)
        choice = input("请选择操作：").strip().lower()

        if choice == "1":
            overview()
        elif choice == "2":
            tunnel_restart()
        elif choice == "3":
            waitress_restart()
        elif choice == "4":
            domain_check()
        elif choice == "5":
            try:
                n = int(input("显示行数（默认30）：") or "30")
            except ValueError:
                n = 30
            show_access_logs(n)
        elif choice == "6":
            show_error_logs()
        elif choice == "7":
            tunnel_info()
        elif choice == "s":
            tunnel_stop()
        elif choice == "q":
            waitress_stop()
        elif choice == "0":
            print("👋 再见")
            break
        else:
            print("\033[33m无效选择，请重新输入\033[0m")

        if choice != "0":
            input("\n按回车继续...")


if __name__ == "__main__":
    # 带参数运行：直接执行对应操作
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            overview()
        elif cmd == "tunnel-restart":
            tunnel_restart()
        elif cmd == "waitress-restart":
            waitress_restart()
        elif cmd == "domain":
            domain_check()
        elif cmd == "logs":
            n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 30
            show_access_logs(n)
        elif cmd == "errors":
            show_error_logs()
        elif cmd == "tunnel-stop":
            tunnel_stop()
        elif cmd == "waitress-stop":
            waitress_stop()
        else:
            print(f"未知命令：{cmd}")
            print("可用命令：status, tunnel-restart, waitress-restart, domain, logs, errors, tunnel-stop, waitress-stop")
    else:
        try:
            menu()
        except KeyboardInterrupt:
            print("\n👋 再见")