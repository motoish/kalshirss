# Kalshi RSS

把 Kalshi 当前开放 **Event** 转换成一个本地 RSS 2.0 文件。第一版只读取公开数据，不需要 Kalshi 账号或 API Key。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行

```bash
python kalshi_rss.py
```

成功后会在当前项目目录生成：

```text
feed.xml
```

仓库自带的 `feed.xml` 只是方便预览格式的示例数据。你第一次运行脚本后会直接覆盖成真实 Kalshi 数据。

可以直接用浏览器/XML 工具打开，也可以之后把它交给 RSS Reader 或部署成在线 feed。

想用网页预览当前 `feed.xml`，在项目目录启动一个本地静态服务：

```bash
python3 -m http.server 8000
```

然后打开 <http://localhost:8000/preview.html>。页面会读取同目录的 `feed.xml`；顶部搜索框可以即时过滤。不要用 `file://` 直接双击打开，浏览器会拦截本地 XML。

## 筛选规则

数据流：

```text
Series  --keyword-->  Event(status=open, nested markets)  --activity-->  RSS item
```

1. 拉取 Kalshi **series**，用关键词匹配系列  
2. 对每个命中系列调用 `/events?series_ticker=...&status=open&with_nested_markets=true`  
3. 嵌套 market 只保留有流动性的：`volume_24h > 0` 或 `yes_bid_size > 0` 或 `yes_ask_size > 0`  
4. **一条 RSS = 一个 Event**（标题用 Event title，如 “Bank of Japan rate decision in September”），下面的 Hold / Hike / 行权价档写在 description 里  

这样可避开：

- `/markets?status=open` 被 `KXMVE*` 体育组合盘淹没  
- 同一事件拆成几十条只差数字的 market 标题  
- 把尚未开盘的 `initialized` 市场写进 feed（改由 API `status=open` 过滤，对应 `active`）

字段匹配规则（针对 series）：

- `title` / `subtitle`：按词边界匹配  
- `ticker` / `event_ticker`：大写代码词（如 `JPY`、`BOJ`）允许子串匹配；普通词仍按词边界  

默认关键词在 `config.json`：

```json
[
  "BOJ",
  "Bank of Japan",
  "JPY",
  "yen"
]
```

直接修改 `keywords` 就能增删关注主题。

## config.json

| 字段 | 作用 |
|---|---|
| `api_url` | Kalshi Markets API（也会据此推导 `/series` 与 `/events`） |
| `keywords` | 用来匹配 series 的关键词 |
| `channel_title` | RSS 名称 |
| `output` | 输出文件名 |
| `timeout_seconds` | 单次 HTTP 请求超时 |
| `page_limit` | 每页条数；Markets/Series 最大 1000，Events 会自动压到 ≤200 |
| `max_pages` | 分页安全上限，避免异常 cursor 无限循环 |

## RSS 每条内容

每个命中 **Event** 会包含：

- Event 标题 / subtitle  
- series ticker / event ticker  
- 有流动性的嵌套 outcomes（YES bid / ask、24h volume、market ticker）  

`guid` 固定使用 Kalshi `event_ticker`，同一事件重复刷新不会产生新的 RSS ID。`link` 指向该 Event 的 Kalshi 页面：`https://kalshi.com/markets/{series}/{event}`。

## 测试

```bash
python -m pytest -q
```
