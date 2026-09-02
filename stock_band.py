import akshare as ak
import pandas as pd
import numpy as np
import requests
import json
import os
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

# ==================== 配置区（已填入你的BARK地址） ====================
BARK_URL = "https://api.day.app"
BARK_KEY = "ZBYeYosX5gDpZLnczrpoGT"
BARK_GROUP_SELECT = "波段选股"
BARK_GROUP_ALERT = "波段持仓监控"
BARK_WEBHOOK = "https://your-webhook-url.com/bark"  # Bark快捷按钮的Webhook地址（部署后替换）

# 止盈止损参数
TAKE_PROFIT_PCT = 0.08       # 止盈比例 8%
STOP_LOSS_PCT = -0.05        # 止损比例 -5%
TRAILING_START_PCT = 0.05    # 盈利超5%后启动移动止损
TRAILING_STOP_PCT = -0.03    # 移动止损回撤3%即卖出

POSITIONS_FILE = "positions.json"
# ===================================================================


def send_bark(title, content="", group=BARK_GROUP_SELECT, action_url=None):
    """推送消息到Bark"""
    url = f"{BARK_URL}/{BARK_KEY}/{title}/{content}"
    params = {"group": group, "badge": "1", "isArchive": "1"}
    if action_url:
        params["action"] = action_url
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            print(f"推送成功: {title}")
        else:
            print(f"推送失败: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"推送失败: {e}")


def load_positions():
    """加载持仓记录"""
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_positions(positions):
    """保存持仓记录"""
    with open(POSITIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=2)


def add_position_local(code, name, buy_price, buy_date):
    """本地添加持仓"""
    positions = load_positions()
    positions.append({
        "code": code,
        "name": name,
        "buy_price": float(buy_price),
        "buy_date": buy_date,
        "max_price": float(buy_price)
    })
    save_positions(positions)
    print(f"已添加持仓: {name}({code}) @ {buy_price}")


# ==================== 功能一：尾盘选股 ====================
def get_stock_list():
    """获取A股全部股票列表"""
    df = ak.stock_zh_a_spot_em()
    return df[['代码', '名称', '最新价', '成交额', '换手率', '量比', '流通市值']]


def get_history_data(code):
    """获取个股近期历史数据"""
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20260101", adjust="qfq")
        if df is None or len(df) < 20:
            return None
        df = df[['日期', '开盘', '最高', '最低', '收盘', '成交量', '成交额']]
        df.columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount']
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except:
        return None


def calc_indicators(df):
    """计算技术指标"""
    close = df['close'].values
    df['MA5'] = pd.Series(close).rolling(5).mean()
    df['MA10'] = pd.Series(close).rolling(10).mean()
    ema12 = pd.Series(close).ewm(span=12, adjust=False).mean()
    ema26 = pd.Series(close).ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD'] = (df['DIF'] - df['DEA']) * 2
    high_9 = pd.Series(close).rolling(9).max()
    low_9 = pd.Series(close).rolling(9).min()
    rsv = (close - low_9) / (high_9 - low_9) * 100
    df['K'] = pd.Series(rsv).ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    df['J'] = 3 * df['K'] - 2 * df['D']
    df['VOL_MA5'] = df['volume'].rolling(5).mean()
    return df


def check_buy_signal(df):
    """判断是否满足买入信号（波段起爆点）"""
    if len(df) < 15:
        return False, ""
    last = df.iloc[-1]
    prev = df.iloc[-2]
    reasons = []
    if last['MA5'] > last['MA10'] and prev['MA5'] <= prev['MA10']:
        reasons.append("MA5金叉MA10")
    if last['volume'] > last['VOL_MA5'] * 1.5:
        reasons.append("放量突破")
    if last['K'] > last['D'] and prev['K'] <= prev['D'] and prev['J'] < 50:
        reasons.append("KDJ低位金叉")
    if last['MACD'] > prev['MACD'] and last['MACD'] > 0:
        reasons.append("MACD走强")
    if len(reasons) >= 2:
        return True, " | ".join(reasons)
    return False, ""


def band_select():
    """波段选股主函数 - 每天14:30执行"""
    print(f"\n开始波段选股: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    try:
        df_spot = get_stock_list()
    except Exception as e:
        send_bark("选股失败", f"获取股票列表异常: {e}", BARK_GROUP_SELECT)
        return

    df_spot = df_spot[
        (df_spot['最新价'] < 20) &
        (df_spot['最新价'] > 3) &
        (df_spot['换手率'] > 3) &
        (df_spot['换手率'] < 15) &
        (df_spot['量比'] > 1.2) &
        (df_spot['流通市值'] < 300)
    ]

    results = []
    for _, row in df_spot.iterrows():
        code = row['代码']
        df_hist = get_history_data(code)
        if df_hist is None:
            continue
        df_hist = calc_indicators(df_hist)
        signal, reason = check_buy_signal(df_hist)
        if signal:
            results.append({
                'code': code,
                'name': row['名称'],
                'price': row['最新价'],
                'turnover': row['换手率'],
                'volume_ratio': row['量比'],
                'reason': reason
            })
            if len(results) >= 5:
                break

    if results:
        msg = ""
        for i, r in enumerate(results, 1):
            msg += f"\n{i}. {r['name']}({r['code']}) {r['price']}"
            msg += f"\n   换手{r['turnover']}% | 量比{r['volume_ratio']} | 信号:{r['reason']}"

        send_bark(
            f"波段选股 {datetime.now().strftime('%m.%d')}",
            msg.strip(),
            BARK_GROUP_SELECT,
            action_url=BARK_WEBHOOK
        )
        print(f"筛选出 {len(results)} 只候选股")
    else:
        send_bark("波段选股 无信号", "今日无符合条件的波段标的", BARK_GROUP_SELECT)
        print("无信号")


# ==================== 功能二：持仓监控 ====================
def get_realtime_price(code):
    """获取个股实时价格"""
    try:
        df = ak.stock_zh_a_spot_em()
        row = df[df['代码'] == code]
        if len(row) == 0:
            return None
        return {
            'name': row['名称'].values[0],
            'price': float(row['最新价'].values[0]),
            'change_pct': float(row['涨跌幅'].values[0]),
            'high': float(row['最高'].values[0]),
            'low': float(row['最低'].values[0])
        }
    except:
        return None


def band_monitor():
    """持仓监控主函数 - 早盘9:35-10:00每5分钟执行"""
    positions = load_positions()
    if not positions:
        print("无持仓，跳过监控")
        return

    print(f"持仓监控，共{len(positions)}只: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    today = datetime.now().strftime('%Y-%m-%d')
    alerts = []

    for pos in positions:
        code = pos['code']
        name = pos['name']
        buy_price = pos['buy_price']
        max_price = pos['max_price']

        realtime = get_realtime_price(code)
        if not realtime:
            continue

        current_price = realtime['price']
        change_pct = realtime['change_pct']

        if current_price > max_price:
            pos['max_price'] = current_price
            save_positions(positions)
            max_price = current_price

        profit_pct = (current_price - buy_price) / buy_price

        action = ""
        sell_reason = ""

        if profit_pct >= TAKE_PROFIT_PCT:
            action = "SELL"
            sell_reason = f"止盈 +{profit_pct*100:.2f}%"
        elif profit_pct <= STOP_LOSS_PCT:
            action = "SELL"
            sell_reason = f"止损 {profit_pct*100:.2f}%"
        elif profit_pct >= TRAILING_START_PCT:
            drawdown = (current_price - max_price) / max_price
            if drawdown <= TRAILING_STOP_PCT:
                action = "SELL"
                sell_reason = f"移动止损（最高点回撤{abs(drawdown)*100:.2f}%）"

        if action == "SELL":
            alerts.append(f"{name}({code})\n买入价:{buy_price} -> 现价:{current_price}({change_pct:+.2f}%)\n{sell_reason}")
            positions = [p for p in positions if p['code'] != code]
            save_positions(positions)
        else:
            hold_days = (datetime.strptime(today, '%Y-%m-%d') - datetime.strptime(pos['buy_date'], '%Y-%m-%d')).days
            alerts.append(f"{name}({code}) 持仓{hold_days}天 | 买入{buy_price} -> 现价{current_price}({profit_pct*100:+.2f}%)")

    if alerts:
        send_bark(
            f"波段持仓 {datetime.now().strftime('%H:%M')}",
            "\n\n".join(alerts),
            BARK_GROUP_ALERT
        )


# ==================== 功能三：从Bark快捷按钮添加持仓 ====================
def add_position_from_bark(code, name, price):
    """从Bark快捷按钮添加持仓"""
    add_position_local(code, name, price, datetime.now().strftime('%Y-%m-%d'))
    send_bark(
        "已登记持仓",
        f"{name}({code}) 买入价: {price}\n日期: {datetime.now().strftime('%Y-%m-%d')}\n将在次日早盘自动监控止盈止损",
        BARK_GROUP_ALERT
    )


# ==================== 入口 ====================
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "select":
            band_select()
        elif cmd == "monitor":
            band_monitor()
        elif cmd == "add":
            if len(sys.argv) >= 5:
                add_position_local(sys.argv[2], sys.argv[3], sys.argv[4], datetime.now().strftime('%Y-%m-%d'))
            else:
                print("用法: python stock_band.py add <代码> <名称> <买入价>")
        elif cmd == "list":
            for p in load_positions():
                print(f"{p['name']}({p['code']}) 买入价:{p['buy_price']} 日期:{p['buy_date']}")
        elif cmd == "webhook":
            from flask import Flask, request, jsonify
            import re

            app = Flask(__name__)

            @app.route('/bark', methods=['POST'])
            def bark_handler():
                data = request.json
                body = data.get('body', '') if data else ''
                title = data.get('title', '') if data else ''

                match = re.search(r'add:([0-9]{6}):([^:]+):([0-9.]+)', body)
                if match:
                    code = match.group(1)
                    name = match.group(2).strip()
                    price = match.group(3)
                    add_position_from_bark(code, name, price)
                    return jsonify({"status": "ok", "message": f"已添加: {name}({code})"})
                else:
                    match2 = re.search(r'([\u4e00-\u9fa5]+)\(([0-9]{6})\)\s*([0-9.]+)', body)
                    if match2:
                        name = match2.group(1)
                        code = match2.group(2)
                        price = match2.group(3)
                        add_position_from_bark(code, name, price)
                        return jsonify({"status": "ok", "message": f"已添加: {name}({code})"})
                    else:
                        return jsonify({"status": "error", "message": "无法解析股票信息"}), 400

            print("Bark Webhook 服务已启动，监听端口 5000")
            print("请将以下地址配置到 Bark 的 Webhook 设置中:")
            print("http://localhost:5000/bark")
            app.run(host='0.0.0.0', port=5000, debug=False)
        else:
            print("用法: python stock_band.py [select|monitor|add|list|webhook]")
    else:
        print("用法: python stock_band.py [select|monitor|add|list|webhook]")
