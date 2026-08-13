# Kalshi RSS

把 Kalshi 上关注主题的开放 Event 转成 RSS 2.0 feed。

只使用 Kalshi 公开 API，不需要账号或 API Key。

## Quick start

需要 Python 3.12+。

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests
```

编辑 `config.json`，然后运行：

```bash
python kalshi_rss.py
```

脚本会在项目根目录生成 `feed.xml`。生成的文件可以直接交给 RSS Reader，或作为在线 feed 发布。

## 配置

最常修改的是 `config.json` 中的 `keywords` 和 `series_tickers`：

```json
{
  "keywords": ["BOJ", "Bank of Japan", "JPY", "yen"],
  "series_tickers": ["KXBOJDECISION"]
}
```

- `series_tickers`：指定要读取的 Series。填写后优先使用它，不再扫描全部 Series。
- `keywords`：当没有指定 `series_tickers` 时，按 Series 的标题、描述和 ticker 匹配关键词。

其他配置项：

| 字段 | 作用 |
| --- | --- |
| `api_url` | Kalshi Markets API 地址 |
| `channel_title` | RSS 名称 |
| `output` | 输出文件名，默认为 `feed.xml` |
| `timeout_seconds` | 单次请求超时时间 |
| `page_limit` | 每页请求数量，Events 会自动限制为不超过 200 |
| `max_pages` | 分页上限，避免异常 cursor 无限循环 |

## 筛选规则

```text
Series → open Event → active market → RSS item
```

- 只读取状态为 `open` 的 Event。
- 只保留有交易活动的 market：24 小时成交量、YES bid size 或 YES ask size 大于 0。
- 一个 Event 对应一条 RSS item，market 的价格、成交量和 ticker 写入 description。
- RSS 的 `guid` 使用 Event ticker，同一事件重复刷新不会产生新的 ID。

## 本地预览

在项目根目录启动静态服务：

```bash
python3 -m http.server 8000
```

打开 <http://localhost:8000/public/> 查看网页预览，打开 <http://localhost:8000/feed.xml> 查看原始 RSS。

不要直接用 `file://` 双击打开页面，浏览器会阻止页面读取本地 XML。

## 测试

```bash
pip install pytest
python -m pytest -q
```
