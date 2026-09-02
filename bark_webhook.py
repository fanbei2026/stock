#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bark Webhook 接收服务
用于接收 Bark 快捷按钮的 POST 请求，自动添加持仓记录

部署方式（任选一种）:
  1. PythonAnywhere (免费): https://www.pythonanywhere.com/
  2. Render (免费): https://render.com/
  3. Railway (免费): https://railway.app/
  4. 本地运行: python bark_webhook.py

环境变量配置:
  GITHUB_TOKEN:  GitHub Personal Access Token (repo 权限)
  GITHUB_REPO:   仓库名，格式 owner/repo
  GITHUB_BRANCH: 分支名，默认 main
  BARK_KEY:      Bark推送密钥（用于发送确认通知）
"""
import os
import json
import re
import base64
import requests
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# 环境变量配置
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO = os.environ.get('GITHUB_REPO', '')
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')
BARK_KEY = os.environ.get('BARK_KEY', 'ZBYeYosX5gDpZLnczrpoGT')
BARK_URL = "https://api.day.app"

GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}"


def send_bark(title, content):
    """发送Bark通知"""
    url = f"{BARK_URL}/{BARK_KEY}/{title}/{content}"
    try:
        requests.get(url, timeout=10)
    except:
        pass


def get_positions_file():
    """从GitHub获取positions.json文件"""
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    url = f"{GITHUB_API}/contents/positions.json"
    params = {'ref': GITHUB_BRANCH}
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    data = resp.json()
    content = data['content']
    decoded = base64.b64decode(content).decode('utf-8')
    positions = json.loads(decoded) if decoded.strip() else []
    return positions, data['sha'], data.get('download_url', '')


def update_positions_file(positions, sha):
    """更新GitHub上的positions.json文件"""
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    url = f"{GITHUB_API}/contents/positions.json"
    params = {'ref': GITHUB_BRANCH}
    body = {
        'message': f"添加持仓: {positions[-1]['code']}",
        'content': base64.b64encode(
            json.dumps(positions, ensure_ascii=False, indent=2).encode('utf-8')
        ).decode('utf-8'),
        'sha': sha
    }
    resp = requests.put(url, headers=headers, params=params, json=body)
    resp.raise_for_status()
    return resp.json()


@app.route('/bark', methods=['POST'])
def bark_handler():
    """处理Bark快捷按钮的POST请求"""
    data = request.json if request.is_json else {}
    body = data.get('body', '') if data else ''
    title = data.get('title', '') if data else ''

    print(f"\n收到Bark请求:")
    print(f"   Title: {title}")
    print(f"   Body: {body}")

    # 解析股票信息
    match = re.search(r'add:([0-9]{6}):([^:]+):([0-9.]+)', body)
    if match:
        code = match.group(1)
        name = match.group(2).strip()
        price = match.group(3)
    else:
        match2 = re.search(r'([\u4e00-\u9fa5]+)\(([0-9]{6})\)\s*([0-9.]+)', body)
        if match2:
            name = match2.group(1)
            code = match2.group(2)
            price = match2.group(3)
        else:
            return jsonify({
                "status": "error",
                "message": "无法解析股票信息，请确保格式正确"
            }), 400

    # 添加持仓到GitHub
    try:
        positions, sha, _ = get_positions_file()
        positions.append({
            "code": code,
            "name": name,
            "buy_price": float(price),
            "buy_date": datetime.now().strftime('%Y-%m-%d'),
            "max_price": float(price)
        })
        update_positions_file(positions, sha)

        # 发送Bark确认通知
        send_bark(
            "已登记持仓",
            f"{name}({code}) 买入价: {price}\n日期: {datetime.now().strftime('%Y-%m-%d')}\n将在次日早盘自动监控止盈止损"
        )

        return jsonify({
            "status": "ok",
            "message": f"已添加持仓: {name}({code}) @ {price}"
        })
    except Exception as e:
        print(f"处理失败: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "message": "Bark Webhook 服务运行中",
        "timestamp": datetime.now().isoformat()
    })


if __name__ == '__main__':
    print("=" * 50)
    print("Bark Webhook 接收服务")
    print("=" * 50)
    print(f"监听地址: http://0.0.0.0:5000")
    print(f"Webhook路径: /bark")
    print(f"GitHub仓库: {GITHUB_REPO}")
    print(f"BARK_KEY: {BARK_KEY[:8]}...")
    print("=" * 50)
    print("请将以下地址配置到 Bark App 的 Webhook 设置中:")
    print("http://localhost:5000/bark")
    print("（部署后替换为你的服务器地址）")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
