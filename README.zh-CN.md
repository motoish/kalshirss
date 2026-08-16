# Kalshi RSS

[English](README.md)

把 Kalshi 上关注主题的开放 Event 转成 RSS 2.0 feed。

只使用 Kalshi 公开 API，不需要账号或 API Key。

线上地址：[rss.motoish.dev](https://rss.motoish.dev) · [feed.xml](https://rss.motoish.dev/feed.xml)

## 快速开始

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --group dev
```

编辑 `config.json`，然后生成 feed：

```bash
uv run python kalshi_rss.py
```

脚本会在项目根目录写出 `feed.xml`。

## 配置

`series_tickers` 优先级更高。只有当它为空或未填写时，才会使用 `keywords`。

```json
{
  "keywords": ["BOJ", "Bank of Japan", "JPY", "yen"],
  "series_tickers": ["KXBOJDECISION"]
}
```

**当 `series_tickers` 非空时（本仓库默认）：**

- 只按这些精确的 Series ticker 拉取开放 Event。
- **不会** 扫描 Kalshi 的全部 Series。
- 匹配阶段 **忽略** `keywords`。可把它当注释保留；若要按关键词扫描，请清空 `series_tickers`。

**当 `series_tickers` 为空或未填写时：**

- 分页遍历全部 Series，保留匹配 `keywords` 的项。
- 标题和 subtitle：不区分大小写的 **词边界** 匹配（`yen` 能匹配 "Japanese yen"，不会匹配 "yenendor"）。
- ticker / event ticker：全大写代码类关键词（如 `JPY`、`BOJ`）用 **子串** 匹配；其余关键词仍用词边界。

生产环境请用明确的 `series_tickers`。全量扫描又慢，也更容易触发限流。

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

```bash
uv sync --group dev
uv run python kalshi_rss.py
uv run pywrangler kv key put feed.xml --path=feed.xml --binding=RSS_KV
uv run pywrangler dev
```

打开 <http://localhost:8787/> 查看网页预览，打开 <http://localhost:8787/feed.xml> 查看原始 RSS。

不要用 `file://` 直接打开页面，浏览器无法读取 `/feed.xml`。

## 部署与自动刷新

仓库中的 `wrangler.jsonc` 指向本项目的 Cloudflare 账户。部署 Fork 前需要修改：

- `account_id` 和 `kv_namespaces[].id`
- `routes[].pattern`，或删除自定义域名配置

在本地完成 Wrangler 认证后部署 Worker：

```bash
uv run pywrangler deploy
```

GitHub Actions 部署和上传 Feed 需要仓库 Secret `CLOUDFLARE_API_TOKEN` 与 `CLOUDFLARE_ACCOUNT_ID`。推送到 `main` 会运行部署 workflow；刷新 workflow 由 GitHub Actions 在默认分支上定时运行。

Feed 每小时刷新两次：

```text
GitHub Actions Cron（UTC :07 / :37）
→ refresh-feed.yml 生成 feed.xml
→ 上传到 Cloudflare KV
```

Cloudflare Worker 只负责提供网页并从 KV 读取 Feed。为避免 Cloudflare 出口 IP 触发 Kalshi 限流，API 请求由 GitHub Actions 发起。也可以在 GitHub 上手动运行 `Refresh Feed` workflow，或在本机执行：

```bash
uv run python kalshi_rss.py
uv run pywrangler kv key put feed.xml --path=feed.xml --binding=RSS_KV --remote
```

## 测试

```bash
uv run pytest -q
```
