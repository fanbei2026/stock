# A股短线爆发力选股策略

## 项目简介

基于"板块、资金、技术、形态"四个维度综合筛选A股短线爆发潜力标的的Python量化选股工具。

**适用场景：**
- 工作日每天早上10点自动筛选潜力股
- 通过Bark推送通知到iPhone
- 支持GitHub Codespaces/浏览器环境运行

## 筛选维度

| 维度 | 筛选条件 | 逻辑说明 |
|------|----------|----------|
| 基本面 | 流通市值30-200亿、排除ST股 | 太小易成庄股，太大拉升困难 |
| 技术面 | 均线多头排列+RSI 60-80+MACD零轴上方 | 确认上升趋势，避免超买 |
| 资金面 | 换手率5%-15%+量比1.8-5 | 资金进出有序，有增量资金 |
| 形态 | 近20天有涨停基因 | 股性活跃，有主力运作 |
| 风控 | 严格避雷ST/减持/预亏 | 规避高风险标的 |

## 买卖点计算

- **买入点：** MA10与MA20的较高值（支撑位买入）
- **卖出点：** 近20日最高价 × 1.03（上方3%缓冲目标价）
- **止损点：** 买入价 × 0.95（下方5%止损）
- **风险收益比：** (卖出价-买入价)/(买入价-止损价)，≥3可轻仓，≥2中等仓位

## 环境准备

### 1. 安装Python依赖

```bash
pip install -r requirements.txt
```

### 2. 安装系统依赖（如需要）

```bash
# Ubuntu/Debian
sudo apt-get install python3-pip

# macOS
brew install python
```

### 3. 配置Bark推送

已在代码中配置好Bark地址，无需额外修改：
- Bark地址：`https://api.day.app/ZBYeYosX5gDpZLnczrpoGT`
- 确保iPhone已安装Bark App并激活推送服务

## 运行方式

### 方式一：直接运行

```bash
python stock_screening.py
```

### 方式二：GitHub Codespaces运行

1. 将代码推送到GitHub仓库
2. 在GitHub页面点击 "Code" > "Codespaces" > "New codespace"
3. 在终端中执行：
   ```bash
   pip install -r requirements.txt
   python stock_screening.py
   ```

### 方式三：定时任务（Linux/macOS）

使用crontab设置每工作日10点自动运行：

```bash
# 编辑crontab
crontab -e

# 添加以下行（周一至周五早上10点）
0 10 * * 1-5 cd /path/to/project && /usr/bin/python3 stock_screening.py >> /tmp/stock_screening.log 2>&1
```

### 方式四：GitHub Actions定时运行

创建 `.github/workflows/stock_screening.yml`：

```yaml
name: A股选股策略

on:
  schedule:
    # 周一至周五 北京时间10:00 (UTC 02:00)
    - cron: '0 2 * * 1-5'
  workflow_dispatch:  # 允许手动触发

jobs:
  stock-screening:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run stock screening
        run: python stock_screening.py
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `stock_screening.py` | 主策略脚本，包含完整筛选逻辑 |
| `requirements.txt` | Python依赖包清单 |
| `README.md` | 项目说明文档 |

## 参数调整

打开 `stock_screening.py` 文件，找到 `CONFIG` 字典可调整以下参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `min_market_cap` | 30 | 最小流通市值（亿） |
| `max_market_cap` | 200 | 最大流通市值（亿） |
| `rsi_low` | 60 | RSI下限 |
| `rsi_high` | 80 | RSI上限 |
| `min_turnover_rate` | 5.0 | 最小换手率（%） |
| `max_turnover_rate` | 15.0 | 最大换手率（%） |
| `min_volume_ratio` | 1.8 | 最小量比 |
| `max_volume_ratio` | 5.0 | 最大量比 |
| `limit_up_lookback` | 20 | 涨停基因回溯天数 |
| `max_retries` | 3 | 最大重试次数 |

## 免责声明

⚠️ **本工具仅供学习参考，不构成任何投资建议。股市有风险，投资需谨慎。使用前请充分了解相关风险。**

## 版本历史

- v1.0 (2026-09-09) - 初始版本，实现五维度综合筛选
