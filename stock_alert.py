import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import warnings
warnings.filterwarnings("ignore")

# ============ 1. 个人配置区 ============
BARK_URL = "https://api.day.app/ZBYeYosX5gDpZLnczrpoGT"

# 筛选参数（可根据需要调整）
MIN_AMOUNT = 1e8           # 成交额下限：1亿
MIN_TURNOVER = 5.0         # 换手率下限：5%
MAX_TURNOVER = 15.0        # 换手率上限：15%
MIN_VOL_RATIO = 1.5        # 量比下限
MIN_PE = 5                 # PE下限
MAX_PE = 60                # PE上限
MIN_PB = 0.5               # PB下限
MAX_PB = 10                # PB上限

# ============ 2. 核心工具 ============
def push_bark(title, msg):
    """推送消息到iPhone"""
    try:
        requests.get(f"{BARK_URL}/{title}", params={
            "body": msg, "group": "选股通知", "sound": "minuet.caf"
        }, timeout=10)
        print(f"✅ 推送成功")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

def safe_request(func, **kwargs):
    """带超时控制的请求包装，防止GitHub卡死"""
    try:
        # 设置15秒超时，拿不到数据直接报错返回None
        return func(**kwargs)
    except Exception:
        return None

# ============ 3. 选股逻辑 ============
def run_stock_filter():
    print(f"🚀 选股系统启动: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # 第一步：获取实时行情
    print("正在获取A股实时行情...")
    df = safe_request(ak.stock_zh_a_spot_em)
    if df is None or df.empty:
        push_bark("选股失败", "实时行情获取失败，请检查网络")
        return

    # 排除ST、停牌和退市
    df = df[~df['名称'].str.contains('ST|退|停牌', na=False)]
    df['最新价'] = pd.to_numeric(df['最新价'], errors='coerce')
    df = df[df['最新价'] > 0]

    # 第二步：硬性条件筛选
    df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce')
    df = df[df['成交额'] >= MIN_AMOUNT]  # 成交额 > 1亿

    df['换手率'] = pd.to_numeric(df['换手率'], errors='coerce')
    df = df[(df['换手率'] >= MIN_TURNOVER) & (df['换手率'] <= MAX_TURNOVER)]

    df['量比'] = pd.to_numeric(df['量比'], errors='coerce')
    df = df[df['量比'] >= MIN_VOL_RATIO] # 量比 > 1.5

    df['市盈率-动态'] = pd.to_numeric(df['市盈率-动态'], errors='coerce')
    df = df[(df['市盈率-动态'] >= MIN_PE) & (df['市盈率-动态'] <= MAX_PE)]

    df['市净率'] = pd.to_numeric(df['市净率'], errors='coerce')
    df = df[(df['市净率'] >= MIN_PB) & (df['市净率'] <= MAX_PB)]

    # 涨幅限制在 1% ~ 9%（排除涨停，寻找刚启动的）
    df['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
    df = df[(df['涨跌幅'] >= 1.0) & (df['涨跌幅'] <= 9.0)]

    if df.empty:
        push_bark("今日无推荐", "粗筛无符合条件的股票")
        return

    print(f"粗筛通过: {len(df)} 只")

    # 第三步：对粗筛通过的股票进行技术面精筛
    final_results = []
    for _, row in df.head(30).iterrows(): # 只精筛粗筛的前30只，节省时间
        code = str(row['代码'])
        name = row['名称']
        
        # 获取近60天历史数据
        hist = safe_request(
            ak.stock_zh_a_hist, symbol=code, 
            period="daily", start_date=(datetime.now() - timedelta(days=60)).strftime('%Y%m%d'), adjust="qfq"
        )
        
        if hist is None or len(hist) < 30:
            continue
            
        # 均线多头判断 (5日线 > 20日线)
        hist['收盘'] = pd.to_numeric(hist['收盘'])
        ma5 = hist['收盘'].tail(5).mean()
        ma20 = hist['收盘'].tail(20).mean()
        
        if ma5 > ma20 and row['最新价'] > ma5:
            final_results.append(f"【{name}】{code} | 涨幅:{row['涨跌幅']}% | 换手率:{row['换手率']}% | 量比:{row['量比']}")
            if len(final_results) >= 3: # 最多推送3只
                break

    # 第四步：推送结果
    if final_results:
        msg = "\n".join(final_results)
        push_bark("🎯 今日精选好股", msg)
        print("✅ 筛选并推送完成")
    else:
        push_bark("今日无推荐", "精筛阶段无符合条件的股票")

if __name__ == "__main__":
    run_stock_filter()
