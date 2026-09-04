import akshare as ak
import pandas as pd
import requests
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

# ============ 1. 个人配置区 ============
BARK_URL = "https://api.day.app/ZBYeYosX5gDpZLnczrpoGT"

# 筛选参数
MIN_AMOUNT = 1e8           # 成交额 >= 1亿
MIN_TURNOVER = 5.0         # 换手率 >= 5%
MAX_TURNOVER = 15.0        # 换手率 <= 15%
MIN_VOL_RATIO = 1.5        # 量比 >= 1.5
MIN_PE = 5                 # PE >= 5
MAX_PE = 60                # PE <= 60
MIN_PB = 0.5               # PB >= 0.5
MAX_PB = 10                # PB <= 10

# ============ 2. Bark推送函数 ============
def push_bark(title, content):
    try:
        requests.get(
            f"{BARK_URL}/{title}/{content}",
            timeout=5
        )
    except Exception as e:
        print(f"推送失败: {e}")

# ============ 3. 主程序 ============
def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"运行时间: {today}")

    # ---- 尝试获取东方财富A股实时行情 ----
    try:
        print("正在获取东方财富实时行情...")
        # 使用akshare的东方财富实时行情接口
        df = ak.stock_zh_a_spot_em()
    except requests.exceptions.Timeout:
        push_bark("选股失败", f"原因：网络超时，GitHub连不上东方财富服务器，请稍后手动重试。")
        return
    except requests.exceptions.ConnectionError:
        push_bark("选股失败", f"原因：网络连接被拒绝，可能是东方财富接口临时维护。")
        return
    except Exception as e:
        push_bark("选股失败", f"原因：数据获取异常 — {str(e)[:50]}")
        return

    # ---- 检查数据是否为空 ----
    if df is None or df.empty:
        push_bark("选股失败", "原因：拿到了空数据，东方财富接口可能正在维护中。")
        return

    print(f"成功获取 {len(df)} 只股票数据")

    # ---- 数据清洗：统一列名 ----
    try:
        # akshare东方财富接口返回的列名
        df.rename(columns={
            "最新价": "price",
            "涨跌幅": "pct_change",
            "涨跌额": "change",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "最高": "high",
            "最低": "low",
            "今开": "open",
            "昨收": "prev_close",
            "量比": "vol_ratio",
            "换手率": "turnover",
            "市盈率-动态": "pe",
            "市净率": "pb",
            "总市值": "total_mv",
            "流通市值": "circ_mv",
            "涨速": "speed",
            "60日涨跌幅": "pct_60d",
            "年初至今涨跌幅": "pct_ytd",
            "代码": "code",
            "名称": "name",
        }, inplace=True)
    except Exception:
        pass  # 列名映射失败不影响后续

    # ---- 确保数值列为数字类型 ----
    for col in ["amount", "turnover", "vol_ratio", "pe", "pb"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ---- 开始筛选 ----
    try:
        result = df.copy()

        # 去除停牌股票（最新价为0或NaN）
        result = result[result["price"] > 0]

        # 条件筛选
        if "amount" in result.columns:
            result = result[result["amount"] >= MIN_AMOUNT]
        if "turnover" in result.columns:
            result = result[result["turnover"] >= MIN_TURNOVER]
            result = result[result["turnover"] <= MAX_TURNOVER]
        if "vol_ratio" in result.columns:
            result = result[result["vol_ratio"] >= MIN_VOL_RATIO]
        if "pe" in result.columns:
            result = result[result["pe"] >= MIN_PE]
            result = result[result["pe"] <= MAX_PE]
        if "pb" in result.columns:
            result = result[result["pb"] >= MIN_PB]
            result = result[result["pb"] <= MAX_PB]
    except Exception as e:
        push_bark("选股失败", f"原因：数据格式解析错误 — {str(e)[:50]}")
        return

    # ---- 判断筛选结果 ----
    if len(result) == 0:
        push_bark(
            "选股失败",
            f"原因：获取了 {len(df)} 只股票，但没有一只满足你的筛选条件。\n"
            f"建议：适当放宽条件（如换手率下限、量比下限）。"
        )
        return

    # ---- 排序输出 ----
    # 按成交额降序排列
    result = result.sort_values(by="amount", ascending=False).head(20)

    # 构建推送内容
    msg = f"共选出 {len(result)} 只股票：\n\n"
    for i, row in result.iterrows():
        name = row.get("name", "未知")
        code = row.get("code", "未知")
        price = row.get("price", 0)
        pct = row.get("pct_change", 0)
        turnover = row.get("turnover", 0)
        vol_ratio = row.get("vol_ratio", 0)
        pe = row.get("pe", 0)
        pb = row.get("pb", 0)

        msg += f"🔔 {name}({code})\n"
        msg += f"  价格: {price}  涨跌: {pct}%\n"
        msg += f"  换手: {turnover}%  量比: {vol_ratio}\n"
        msg += f"  PE: {pe}  PB: {pb}\n\n"

    push_bark("选股结果", msg)
    print(f"成功推送 {len(result)} 只股票")

if __name__ == "__main__":
    main()
