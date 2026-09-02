# -*- coding: utf-8 -*-
"""
波段选股脚本
数据源：AKShare（东方财富）
推送渠道：Bark
"""

import os
import sys
import akshare as ak
import requests
from datetime import datetime

# ============ 配置区 ============
# Bark 推送地址（从 GitHub Secrets 读取）
BARK_URL = os.environ.get("BARK_URL", "")
BARK_KEY = os.environ.get("BARK_KEY", "")  # Bark的密钥

# 选股条件（可根据自己策略调整）
MIN_CHANGE_PCT = 3.0    # 最小涨幅 %
MAX_CHANGE_PCT = 9.5    # 最大涨幅 %（排除涨停）
MIN_TURNOVER = 2.0      # 最小换手率 %
MIN_VOLUME_RATIO = 1.5  # 最小量比
MAX_PRICE = 100.0       # 最高股价（排除高价股）
MIN_PRICE = 3.0         # 最低股价（排除低价垃圾股）
# ================================


def fetch_stock_data():
    """获取A股实时行情数据（带重试）"""
    print("正在获取A股实时行情...")
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            df = ak.stock_zh_a_spot_em()
            print(f"✅ 成功获取 {len(df)} 只股票数据")
            return df
        except Exception as e:
            print(f"⚠️ 第 {attempt} 次尝试失败: {e}")
            if attempt < max_retries:
                import time
                time.sleep(2)
    print("❌ 获取股票数据失败，已重试3次")
    return None


def filter_stocks(df):
    """根据波段选股条件筛选股票"""
    if df is None or df.empty:
        return []

    selected = []

    for _, row in df.iterrows():
        try:
            # 获取字段值（不同接口可能字段名略有不同）
            code = str(row.get("代码", ""))
            name = str(row.get("名称", ""))
            price = float(row.get("最新价", 0))
            change_pct = float(row.get("涨跌幅", 0))
            turnover = float(row.get("换手率", 0))
            volume_ratio = float(row.get("量比", 1.0))

            # 排除ST股、退市股
            if "ST" in name or "退" in name:
                continue

            # 排除新股（代码以301/688开头且价格异常）
            if code.startswith("301") or code.startswith("688"):
                if price > 200:
                    continue

            # 波段选股条件
            if MIN_CHANGE_PCT <= change_pct <= MAX_CHANGE_PCT:
                if turnover >= MIN_TURNOVER:
                    if volume_ratio >= MIN_VOLUME_RATIO:
                        if MIN_PRICE <= price <= MAX_PRICE:
                            selected.append({
                                "code": code,
                                "name": name,
                                "price": price,
                                "change_pct": change_pct,
                                "turnover": turnover,
                                "volume_ratio": volume_ratio,
                            })
        except (ValueError, TypeError):
            # 数据异常的单只股票，跳过
            continue

    # 按涨幅排序
    selected.sort(key=lambda x: x["change_pct"], reverse=True)
    return selected


def send_bark(title, body, is_url=False):
    """推送消息到 Bark"""
    if not BARK_URL or not BARK_KEY:
        print("⚠️ 未配置 BARK_URL 或 BARK_KEY，跳过推送")
        return

    url = f"{BARK_URL.rstrip('/')}/{BARK_KEY}"
    payload = {
        "title": title,
        "body": body,
        "badge": 1,
        "group": "波段选股",
        "sound": "minuet.caf",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ 推送成功")
        else:
            print(f"❌ 推送失败: {response.text}")
    except Exception as e:
        print(f"❌ 推送异常: {e}")


def format_message(selected):
    """格式化选股结果消息"""
    if not selected:
        return "📊 今日暂无符合波段条件的标的\n\n条件：涨幅3%~9.5%、换手率≥2%、量比≥1.5"

    lines = []
    for i, s in enumerate(selected[:15], 1):  # 最多推送15只
        lines.append(
            f"{i}. {s['name']}（{s['code']}） "
            f"涨幅{s['change_pct']:+.2f}% "
            f"换手{s['turnover']:.1f}% "
            f"量比{s['volume_ratio']:.1f}"
        )

    msg = f"🎯 共筛选出 {len(selected)} 只标的\n\n" + "\n".join(lines)
    if len(selected) > 15:
        msg += f"\n\n（还有 {len(selected) - 15} 只，请在GitHub查看完整列表）"

    msg += f"\n\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    return msg


def main():
    print("=" * 50)
    print(f"波段选股启动 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 1. 获取数据
    df = fetch_stock_data()
    if df is None:
        send_bark("选股失败 ❌", "获取股票数据失败，请检查网络或稍后重试。")
        sys.exit(1)

    # 2. 筛选
    selected = filter_stocks(df)
    print(f"筛选出 {len(selected)} 只符合条件的股票")

    # 3. 推送
    title = f"波段选股 {'✅' if selected else '⚪'}"
    body = format_message(selected)
    send_bark(title, body)

    # 4. 输出完整列表（供GitHub Actions日志查看）
    print("\n" + "=" * 50)
    print("完整选股结果：")
    print("=" * 50)
    for s in selected:
        print(f"  {s['code']} {s['name']} 涨{s['change_pct']:+.2f}% "
              f"换手{s['turnover']:.1f}% 量比{s['volume_ratio']:.1f}")


if __name__ == "__main__":
    main()
