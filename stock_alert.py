import akshare as ak
import pandas as pd
import requests
from datetime import datetime
import time
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

# ============ 2. Bark推送 ============
def push_bark(title, content):
    try:
        requests.get(f"{BARK_URL}/{title}/{content}", timeout=5)
    except:
        pass

# ============ 3. 获取行情数据（新浪主力 + 东财备用） ============
def get_market_data():
    # 第一选择：新浪接口（海外IP友好）
    for i in range(3):
        try:
            df = ak.stock_zh_a_spot()
            if df is not None and len(df) > 0:
                return df, "sina"
        except:
            time.sleep(2)

    # 第二选择：东方财富（国内数据最全）
    for i in range(3):
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and len(df) > 0:
                return df, "em"
        except:
            time.sleep(3)

    return None, "fail"

# ============ 4. 主程序 ============
def main():
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M")

    # 检查是否交易日（周一~周五）
    if datetime.now().weekday() >= 5:
        push_bark("选股跳过", f"今天是周末，A股休市。\n{today} {now}")
        return

    # 获取数据
    df, source = get_market_data()

    if df is None:
        push_bark(
            "选股失败",
            f"原因：新浪和东方财富接口均无法连接，可能是非交易时段或网络故障。\n{today} {now}"
        )
        return

    # ---- 根据数据源适配字段 ----
    if source == "sina":
        # 新浪接口字段映射
        try:
            df["成交额"] = pd.to_numeric(df.get("成交额", 0), errors="coerce")
            df["换手率"] = pd.to_numeric(df.get("换手率", 0), errors="coerce") if "换手率" in df.columns else None
            df["量比"] = pd.to_numeric(df.get("量比", 0), errors="coerce") if "量比" in df.columns else None
            df["市盈率"] = pd.to_numeric(df.get("市盈率", 0), errors="coerce") if "市盈率" in df.columns else None
            df["市净率"] = pd.to_numeric(df.get("市净率", 0), errors="coerce") if "市净率" in df.columns else None
            source_name = "新浪"
        except Exception as e:
            push_bark("选股失败", f"原因：新浪数据解析异常 - {str(e)[:50]}\n{today} {now}")
            return
    else:
        # 东方财富接口字段映射
        try:
            df["成交额"] = pd.to_numeric(df.get("成交额", 0), errors="coerce")
            df["换手率"] = pd.to_numeric(df.get("换手率", 0), errors="coerce")
            df["量比"] = pd.to_numeric(df.get("量比", 0), errors="coerce")
            df["市盈率"] = pd.to_numeric(df.get("市盈率-动态", 0), errors="coerce")
            df["市净率"] = pd.to_numeric(df.get("市净率", 0), errors="coerce")
            source_name = "东方财富"
        except Exception as e:
            push_bark("选股失败", f"原因：东财数据解析异常 - {str(e)[:50]}\n{today} {now}")
            return

    # ---- 筛选逻辑 ----
    try:
        # 成交额必须 >= 1亿
        result = df[df["成交额"] >= MIN_AMOUNT].copy()

        # 换手率筛选（如果数据源有该字段）
        if "换手率" in df.columns and result["换手率"].notna().any():
            result = result[(result["换手率"] >= MIN_TURNOVER) & (result["换手率"] <= MAX_TURNOVER)]

        # 量比筛选（如果数据源有该字段）
        if "量比" in df.columns and result["量比"].notna().any():
            result = result[result["量比"] >= MIN_VOL_RATIO]

        # PE筛选（如果数据源有该字段）
        if "市盈率" in df.columns and result["市盈率"].notna().any():
            result = result[(result["市盈率"] >= MIN_PE) & (result["市盈率"] <= MAX_PE)]

        # PB筛选（如果数据源有该字段）
        if "市净率" in df.columns and result["市净率"].notna().any():
            result = result[(result["市净率"] >= MIN_PB) & (result["市净率"] <= MAX_PB)]

    except Exception as e:
        push_bark("选股失败", f"原因：筛选过程出错 - {str(e)[:50]}\n{today} {now}")
        return

    # ---- 结果推送 ----
    if len(result) == 0:
        push_bark(
            "选股失败",
            f"原因：数据获取成功（来源：{source_name}），但当天没有符合所有条件的股票。\n{today} {now}"
        )
        return

    # 成功！推送结果
    result = result.sort_values("成交额", ascending=False).head(20)
    msg = f"数据源：{source_name}\n符合条件：{len(result)}只\n\n"

    for _, row in result.iterrows():
        name = row.get("名称", "N/A")
        code = row.get("代码", "N/A")
        price = row.get("最新价", 0)
        change = row.get("涨跌幅", 0)
        amount = row.get("成交额", 0) / 1e8
        msg += f"{name}({code})  {price}元  {change:+.2f}%  成交{amount:.1f}亿\n"

    msg += f"\n{today} {now}"
    push_bark("选股成功", msg)

if __name__ == "__main__":
    main()
