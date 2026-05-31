#!/usr/bin/env python3
"""智能充电站调度计费系统 - 管理员 CLI 工具"""
import sys
import json
import click
import requests

BASE_URL = "http://localhost:8000/api/v1"
TOKEN_FILE = ".cli_token"


def get_token():
    try:
        with open(TOKEN_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        f.write(token)


def api(method, path, **kwargs):
    token = get_token()
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{BASE_URL}{path}"
    resp = requests.request(method, url, headers=headers, **kwargs)
    if resp.status_code == 401:
        print("认证失败，请先登录")
        sys.exit(1)
    if not resp.ok:
        print(f"错误: {resp.json().get('detail', resp.text)}")
        sys.exit(1)
    return resp.json()


@click.group()
def cli():
    """智能充电站调度计费系统 CLI"""


@cli.command()
@click.option("--username", "-u", prompt=True, help="用户名")
@click.option("--password", "-p", prompt=True, hide_input=True, help="密码")
def login(username, password):
    """管理员登录"""
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", json={"username": username, "password": password})
        resp.raise_for_status()
        data = resp.json()
        save_token(data["access_token"])
        print(f"登录成功! Token 已保存")
        me = requests.get(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"}).json()
        print(f"用户: {me['username']} ({me['role']})")
    except Exception as e:
        print(f"登录失败: {e}")
        sys.exit(1)


@cli.command()
@click.option("--username", "-u", prompt=True, help="管理员用户名")
@click.option("--password", "-p", prompt=True, hide_input=True, confirmation_prompt=True, help="密码")
def create_admin(username, password):
    """创建管理员账号（直接操作数据库，无需登录）"""
    import hashlib
    import secrets
    import sqlite3

    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), 100000)
    password_hash = f"pbkdf2:sha256:100000${salt}${h.hex()}"

    try:
        conn = sqlite3.connect("charging_station.db")
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'admin', datetime('now'))",
            (username, password_hash)
        )
        conn.commit()
        conn.close()
        print(f"管理员 {username} 创建成功!")
        print(f"登录: python cli/main.py login -u {username}")
    except sqlite3.IntegrityError:
        print(f"错误: 用户名 {username} 已存在")
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


@cli.group()
def piles():
    """充电桩管理"""


@piles.command("list")
def pile_list():
    """查看所有充电桩"""
    data = api("GET", "/piles")
    print(f"{'ID':<4} {'编号':<8} {'模式':<6} {'功率':<10} {'状态':<12} {'充电次数':<8}")
    print("-" * 60)
    for p in data:
        print(f"{p['id']:<4} {p['pile_code']:<8} {'快充' if p['mode']=='F' else '慢充':<6} {p['power_rate']}度/h {'':<3} {p['status']:<12} {p['total_charge_count']:<8}")


@piles.command("start")
@click.argument("pile_id", type=int)
def pile_start(pile_id):
    """启动充电桩"""
    data = api("POST", f"/piles/{pile_id}/start")
    print(f"✓ {data['message']}")


@piles.command("stop")
@click.argument("pile_id", type=int)
def pile_stop(pile_id):
    """停止充电桩"""
    data = api("POST", f"/piles/{pile_id}/stop")
    print(f"✓ {data['message']}")


@cli.group()
def faults():
    """故障管理"""


@faults.command("report")
@click.argument("pile_id", type=int)
@click.option("--strategy", "-s", type=click.Choice(["PRIORITY", "TIME_ORDER"]), default="PRIORITY", help="调度策略")
def fault_report(pile_id, strategy):
    """上报故障"""
    data = api("POST", f"/faults/{pile_id}", json={"strategy": strategy})
    print(f"✓ {data['message']}")
    if data.get("detail"):
        print(f"  影响订单: {data['detail'].get('affected_count', 0)}")


@faults.command("recover")
@click.argument("pile_id", type=int)
def fault_recover(pile_id):
    """故障恢复"""
    data = api("POST", f"/faults/{pile_id}/recover")
    print(f"✓ {data['message']}")


@faults.command("list")
def fault_list():
    """查看故障记录"""
    data = api("GET", "/faults")
    if not data:
        print("(无故障记录)")
        return
    print(f"{'ID':<4} {'桩ID':<6} {'故障时间':<22} {'策略':<12} {'状态':<10}")
    print("-" * 60)
    for f in data:
        print(f"{f['id']:<4} {f['pile_id']:<6} {f['fault_time']:<22} {f['strategy_used'] or '-':<12} {f['status']:<10}")


@cli.group()
def reports():
    """报表管理"""


@reports.command("generate")
@click.argument("type", type=click.Choice(["DAILY", "WEEKLY", "MONTHLY"]))
def report_generate(type):
    """生成报表"""
    data = api("POST", "/reports", json={"report_type": type})
    print(f"✓ 报表已生成 (ID: {data['id']})")
    summary = data.get("report_data", {}).get("summary", {})
    print(f"  总充电次数: {summary.get('total_charges', 0)}")
    print(f"  总充电量: {summary.get('total_kwh', 0)} 度")
    print(f"  总费用: ¥{summary.get('total_fee', 0)}")


@reports.command("list")
def report_list():
    """查看报表列表"""
    data = api("GET", "/reports")
    if not data:
        print("(无报表)")
        return
    print(f"{'ID':<4} {'类型':<8} {'开始时间':<22} {'总费用':<10}")
    print("-" * 60)
    for r in data:
        total = r.get("report_data", {}).get("summary", {}).get("total_fee", 0)
        print(f"{r['id']:<4} {r['report_type']:<8} {r['period_start']:<22} ¥{total:<10}")


@cli.group()
def sim():
    """仿真控制"""


@sim.command("tick")
def sim_tick():
    """推进时间"""
    data = api("POST", "/sim/tick")
    print(f"✓ {data['message']}")
    detail = data.get("detail", {})
    print(f"  当前时间: {detail.get('current_time', '')}")
    for evt in detail.get("events", []):
        print(f"  → {evt}")


@sim.command("time")
def sim_time():
    """查看虚拟时间"""
    data = api("GET", "/sim/clock")
    print(f"当前虚拟时间: {data['current_time']}")
    print(f"每Tick: {data['tick_minutes']} 分钟")


@sim.command("fast")
@click.argument("hours", type=int)
def sim_fast(hours):
    """快速推进N小时"""
    for i in range(hours * 4):  # 4 ticks per hour (15 min each)
        data = api("POST", "/sim/tick")
    clock = api("GET", "/sim/clock")
    print(f"✓ 已推进 {hours} 小时，当前时间: {clock['current_time']}")


@cli.command()
def status():
    """查看系统状态"""
    piles_data = api("GET", "/piles")
    clock_data = api("GET", "/sim/clock")

    print(f"\n{'='*60}")
    print(f"  智能充电站调度计费系统 - 状态总览")
    print(f"  虚拟时间: {clock_data['current_time']}")
    print(f"{'='*60}\n")

    for p in piles_data:
        status_icon = {"IDLE": "⚪", "CHARGING": "🟢", "BROKEN": "🔴", "STOPPED": "⚫"}.get(p['status'], '?')
        mode_label = "快充" if p['mode'] == 'F' else "慢充"
        print(f"  {status_icon} {p['pile_code']} ({mode_label} {p['power_rate']}度/h)")
        print(f"    状态: {p['status']} | 累计: {p['total_charge_count']}次 | {p['total_charge_kwh']}度 | {p['total_charge_duration']}h")
    print()


if __name__ == "__main__":
    cli()
