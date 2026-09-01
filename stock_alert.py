import akshare as ak
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import warnings
warnings.filterwarnings("ignore")

# ============ 配置区 ============
BARK_URL = "https://api.day.app/ZBYeYosX5gDpZLnczrpoGT"

# 筛选参数
MIN_AMOUNT = 1e8           # 日均成交额下限：1亿
MIN_TURNOVER = 5.0         # 换手率下限：5%（接口返回单位是%）
MAX_TURNOVER = 15.0        # 换手率上限：15%
MIN_VOL_RATIO = 1.5        # 量比下限（价量共振核心因子）
MIN_MARGIN_RATIO = 0.05    # 融资余额占流通市值比例下限：5%
MAX_MARGIN_RATIO = 0.10    # 融资余额占流通市值比例上限：10%
MIN_PE = 5                 # PE下限（排除亏损和极低估值陷阱）
MAX_PE = 60                # PE上限（排除高估值泡沫）
MIN_PB = 0.5               # PB下限
MAX_PB = 10                # PB上限
TOP_N = 3                  # 最终推送股票数量
MAX_CANDIDATES = 80        # 深度分析最大候选数

def push_bark(title, msg):
    """通过Bark推送消息到iPhone"""
    try:
        url = f"{BARK_URL}/{title}"
        requests.get(url, params={
            "body": msg,
            "group": "选股通知",
            "sound": "minuet.caf"
        }, timeout=10)
        print(f"✅ 推送成功")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

# ============ 第一步：批量获取融资融券数据 ============
def load_margin_data():
    """
    一次性批量获取沪深两市全部融资融券明细
    返回: dict，key=股票代码, value=融资余额(元)
    """
    margin_dict = {}
    today = datetime.now().strftime('%Y%m%d')
    
    # 尝试最近5个交易日（处理周末/节假日）
    for offset in range(5):
        date_str = (datetime.now() - timedelta(days=offset)).strftime('%Y%m%d')
        try:
            # 沪市
            sh_df = ak.stock_margin_detail_sse(date=date_str)
            if sh_df is not None and not sh_df.empty:
                for _, row in sh_df.iterrows():
                    code = str(row.get('证券代码', '')).strip()
                    balance = row.get('融资余额', 0)
                    if code and balance:
                        margin_dict[code] = float(balance)
                print(f"  沪市融资数据加载成功 ({date_str}): {len(sh_df)} 条")
                break
        except Exception as e:
            print(f"  沪市 {date_str} 数据获取失败: {e}")
            continue
    
    time.sleep(1)
    
    for offset in range(5):
        date_str = (datetime.now() - timedelta(days=offset)).strftime('%Y%m%d')
        try:
            # 深市
            sz_df = ak.stock_margin_detail_szse(date=date_str)
            if sz_df is not None and not sz_df.empty:
                for _, row in sz_df.iterrows():
                    code = str(row.get('证券代码', '')).strip()
                    balance = row.get('融资余额', 0)
                    if code and balance:
                        margin_dict[code] = float(balance)
                print(f"  深市融资数据加载成功 ({date_str}): {len(sz_df)} 条")
                break
        except Exception as e:
            print(f"  深市 {date_str} 数据获取失败: {e}")
            continue
    
    print(f"  融资余额数据总计: {len(margin_dict)} 只股票")
    return margin_dict

# ============ 第二步：获取市场整体PCR（辅助参考）============
def get_market_pcr():
    """
    获取50ETF期权PCR（市场整体情绪指标）
    PCR < 0.7: 市场偏乐观（看涨情绪强）
    PCR 0.7~1.2: 中性
    PCR > 1.2: 市场偏悲观（看跌情绪强）
    返回: PCR值，获取失败返回None
    """
    try:
        df = ak.option_finance_board(symbol="华夏上证50ETF期权")
        if df is None or df.empty:
            return None
        
        # 区分认购和认沽
        call_mask = df['合约类型'].str.contains('认购') if '合约类型' in df.columns else pd.Series([False]*len(df))
        put_mask = df['合约类型'].str.contains('认沽') if '合约类型' in df.columns else pd.Series([False]*len(df))
        
        if '成交量' in df.columns:
            call_vol = df.loc[call_mask, '成交量'].sum()
            put_vol = df.loc[put_mask, '成交量'].sum()
            if call_vol > 0:
                pcr = put_vol / call_vol
                print(f"  市场PCR(成交量): {pcr:.3f}")
                return pcr
    except Exception as e:
        print(f"  PCR数据获取失败（非关键，跳过）: {e}")
    
    return None

# ============ 第三步：粗筛（基于实时行情）============
def coarse_filter():
    """
    用实时行情接口做第一轮粗筛
    直接从 stock_zh_a_spot_em 获取 PE/PB/量比/换手率/成交额/流通市值
    """
    print("正在获取A股实时行情...")
    df = ak.stock_zh_a_spot_em()
    print(f"  全市场共 {len(df)} 只股票")
    
    # 排除ST、退市
    df = df[~df['名称'].str.contains('ST|退', na=False)]
    
    # 排除停牌（最新价为0或NaN）
    df['最新价'] = pd.to_numeric(df['最新价'], errors='coerce')
    df = df[df['最新价'] > 0]
    
    # 成交额 > 1亿
    df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce')
    df = df[df['成交额'] >= MIN_AMOUNT]
    
    # 换手率 5%~15%（接口返回单位已经是%）
    df['换手率'] = pd.to_numeric(df['换手率'], errors='coerce')
    df = df[(df['换手率'] >= MIN_TURNOVER) & (df['换手率'] <= MAX_TURNOVER)]
    
    # 量比 > 1.5（价量共振核心因子）
    df['量比'] = pd.to_numeric(df['量比'], errors='coerce')
    df = df[df['量比'] >= MIN_VOL_RATIO]
    
    # PE为正且在合理区间（核心基本面因子）
    df['市盈率-动态'] = pd.to_numeric(df['市盈率-动态'], errors='coerce')
    df = df[(df['市盈率-动态'] >= MIN_PE) & (df['市盈率-动态'] <= MAX_PE)]
    
    # PB在合理区间（核心基本面因子）
    df['市净率'] = pd.to_numeric(df['市净率'], errors='coerce')
    df = df[(df['市净率'] >= MIN_PB) & (df['市净率'] <= MAX_PB)]
    
    # 涨幅在1%~9%之间（排除涨停和微涨）
    df['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
    df = df[(df['涨跌幅'] >= 1.0) & (df['涨跌幅'] <= 9.0)]
    
    # 流通市值 > 0
    df['流通市值'] = pd.to_numeric(df['流通市值'], errors='coerce')
    df = df[df['流通市值'] > 0]
    
    print(f"  粗筛通过: {len(df)} 只")
    return df

# ============ 第四步：深度筛选 ============
def check_stock_detail(symbol, name, margin_dict, pcr_value):
    """
    对单只股票做深度技术面筛选 + 多因子打分
    """
    try:
        # ---- 获取日K数据 ----
        daily = ak.stock_zh_a_hist(
            symbol=symbol, period="daily",
            start_date=(datetime.now() - timedelta(days=120)).strftime('%Y%m%d'),
            adjust="qfq"
        )
        if daily is None or len(daily) < 30:
            return None
        
        daily = daily.tail(30).reset_index(drop=True)
        last = daily.iloc[-1]
        score = 0
        
        # ===== 条件3: 均线多头排列（5日 > 20日, 股价 > 5日）=====
        daily['ma5'] = daily['收盘'].rolling(5).mean()
        daily['ma20'] = daily['收盘'].rolling(20).mean()
        
        if pd.isna(last['ma5']) or pd.isna(last['ma20']):
            return None
        if not (last['收盘'] > last['ma5'] > last['ma20']):
            return None
        score += 15
        
        # ===== 条件4: 连续放量 =====
        vol_3days = daily['成交量'].tail(3).tolist()
        vol_ma5 = daily['成交量'].rolling(5).mean().iloc[-1]
        
        if len(vol_3days) == 3:
            # 逐日递增
            cond_a = vol_3days[0] < vol_3days[1] < vol_3days[2]
            # 或至少比5日均量高20%
            cond_b = all(v > vol_ma5 * 1.2 for v in vol_3days)
            if not (cond_a or cond_b):
                return None
        score += 15
        
        # ===== 条件6: 近20天阳线多于阴线 =====
        recent20 = daily.tail(20)
        yang = len(recent20[recent20['收盘'] > recent20['开盘']])
        yin = len(recent20[recent20['收盘'] < recent20['开盘']])
        if yang <= yin:
            return None
        score += 10
        
        # ===== 多因子打分 =====
        
        # --- 因子1: 量比（价量共振核心）---
        # 量比越大，资金关注度越高
        vol_ratio = last.get('量比', 1.5)
        if pd.isna(vol_ratio) or vol_ratio < MIN_VOL_RATIO:
            return None
        score += min((vol_ratio - 1.5) * 8, 20)  # 最高加20分
        
        # --- 因子2: 融资余额占流通市值比例 ---
        margin_balance = margin_dict.get(symbol, 0)
        if margin_balance > 0:
            # 流通市值从粗筛数据传入（这里用last的收盘价近似估算）
            # 实际流通市值在粗筛阶段已经验证过，这里用日K数据近似
            # 获取流通市值：从实时行情中传入
            pass  # 融资余额评分在粗筛后的check中统一处理
        
        # --- 因子3: PE/PB基本面评分 ---
        # PE在粗筛已过滤，这里做精细评分
        # PE 15~30 最优区间
        pe = last.get('市盈率-动态', 0)
        # 注意：日K数据中没有PE字段，PE从粗筛数据中获取
        # 这里通过量价关系间接评估
        
        # --- 因子4: PCR辅助加分 ---
        if pcr_value is not None:
            if 0.7 <= pcr_value <= 1.2:
                score += 5  # 市场情绪中性偏好
            elif pcr_value < 0.7:
                score += 3  # 市场偏乐观
        
        # --- 均线发散度（多头加速）---
        if len(daily) >= 25:
            spread_now = (last['ma5'] - last['ma20']) / last['ma20']
            spread_prev = (daily['ma5'].iloc[-5] - daily['ma20'].iloc[-5]) / daily['ma20'].iloc[-5]
            if spread_now > spread_prev:
                score += 10  # 多头在加速发散
        
        # --- 阳线强度 ---
        score += min((yang - 10) * 2, 10)
        
        return score
        
    except Exception as e:
        return None

# ============ 主流程 ============
def main():
    print("=" * 50)
    print(f"🚀 多因子选股系统启动: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)
    
    # 1. 批量加载融资融券数据
    print("\n📊 加载融资融券数据...")
    margin_dict = load_margin_data()
    
    # 2. 获取市场PCR（辅助参考）
    print("\n📊 获取市场PCR指标...")
    pcr_value = get_market_pcr()
    
    # 3. 粗筛
    print("\n📊 第一轮粗筛（量比+PE/PB+换手率+成交额）...")
    candidates_df = coarse_filter()
    if candidates_df.empty:
        push_bark("今日无推荐", "粗筛阶段无股票通过，耐心等待机会")
        return
    
    # 4. 融资余额二次过滤 + 深度筛选
    print(f"\n📊 第二轮精筛（融资余额+技术面+多因子打分）...")
    results = []
    analyzed = 0
    
    for _, row in candidates_df.iterrows():
        if analyzed >= MAX_CANDIDATES:
            break
        
        symbol = str(row['代码'])
        name = str(row['名称'])
        
        # 融资余额占比检查（核心因子）
        margin_balance = margin_dict.get(symbol, 0)
        circulating_mv = float(row.get('流通市值', 0))
        
        if margin_balance > 0 and circulating_mv > 0:
            margin_ratio = margin_balance / circulating_mv
            if not (MIN_MARGIN_RATIO <= margin_ratio <= MAX_MARGIN_RATIO):
                continue
        else:
            # 没有融资数据的股票，不强制排除，但不加分
            margin_ratio = 0
        
        analyzed += 1
        print(f"  [{analyzed}/{min(MAX_CANDIDATES, len(candidates_df))}] {name}({symbol})...", end=" ")
        
        # 深度筛选
        score = check_stock_detail(symbol, name, margin_dict, pcr_value)
        
        if score is not None and score > 0:
            # 融资余额加分
            if MIN_MARGIN_RATIO <= margin_ratio <= MAX_MARGIN_RATIO:
                score += 15
                # 靠近7%~8%最优区间额外加分
                if 0.07 <= margin_ratio <= 0.08:
                    score += 5
            
            # PE精细评分
            pe = float(row.get('市盈率-动态', 0))
            if 15 <= pe <= 30:
                score += 10  # PE最优区间
            elif 10 <= pe < 15 or 30 < pe <= 40:
                score += 5
            
            # PB精细评分
            pb = float(row.get('市净率', 0))
            if 1 <= pb <= 3:
                score += 10  # PB最优区间
            elif 3 < pb <= 5:
                score += 5
            
            results.append({
                '代码': symbol,
                '名称': name,
                '收盘价': round(float(row['最新价']), 2),
                '涨跌幅': f"{float(row['涨跌幅']):.2f}%",
                '量比': round(float(row['量比']), 2),
                '换手率': f"{float(row['换手率']):.2f}%",
                '成交额': f"{float(row['成交额'])/1e8:.1f}亿",
                'PE': round(pe, 1),
                'PB': round(pb, 2),
                '融资占比': f"{margin_ratio*100:.1f}%",
                '评分': round(score, 1)
            })
            print(f"✅ 通过! 评分: {score}")
        else:
            print("❌ 未通过")
        
        # 礼貌延迟，避免被封
        time.sleep(0.3)
    
    # 5. 排序取Top3
    results.sort(key=lambda x: x['评分'], reverse=True)
    top3 = results[:TOP_N]
    
    print(f"\n{'='*50}")
    print(f"✅ 最终通过: {len(results)} 只，推送TOP{TOP_N}")
    print(f"{'='*50}")
    
    if not top3:
        push_bark("今日无推荐", "暂无符合全部条件的股票，耐心等待机会 📌")
        return
    
    # 6. 推送
    msg_lines = []
    for i, s in enumerate(top3, 1):
        msg_lines.append(
            f"🏆 Top{i}: {s['名称']}({s['代码']})\n"
            f"收盘:{s['收盘价']}元 涨幅:{s['涨跌幅']}\n"
            f"量比:{s['量比']} 换手:{s['换手率']} 成交额:{s['成交额']}\n"
            f"PE:{s['PE']} PB:{s['PB']} 融资占比:{s['融资占比']}\n"
            f"综合评分:{s['评分']}"
        )
    
    push_msg = "\n\n".join(msg_lines)
    
    # 附加市场信息
    market_info = f"\n\n📊 市场参考:\n"
    if pcr_value is not None:
        market_info += f"PCR: {pcr_value:.2f} "
        if pcr_value < 0.7:
            market_info += "(偏乐观)"
        elif pcr_value > 1.2:
            market_info += "(偏悲观)"
        else:
            market_info += "(中性)"
    
    push_bark("🔥 今日精选3股", push_msg + market_info)
    print("\n✅ 推送完成！")

if __name__ == "__main__":
    main()
