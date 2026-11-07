# 自用 GitHub 统计卡片

两张卡片由本仓库的 Python 脚本直接请求 `https://api.github.com/graphql` 生成。
脚本只使用 Python 标准库，不调用第三方卡片服务，不需要授权第三方 OAuth 应用。
工作流在自己的 GitHub Actions 中运行；访问 Token 保存在仓库 Secret 中，只传给生成步骤。

## 首次启用

1. 在 GitHub 的 **Settings → Developer settings → Personal access tokens → Tokens (classic)** 创建自己的 Token，按 GitHub Stats Extended 的私有统计建议选择 `repo` 和 `read:user`，并设置到期时间。这个 classic Token 的 `repo` 权限较广，请仅将它保存到自己的 Secret 中；脚本只发送查询请求。
2. 打开本仓库 **Settings → Secrets and variables → Actions → New repository secret**，名称填 `PROFILE_STATS_TOKEN`，值填 Token。不要把 Token 写入源码、README、图片地址或聊天。
3. 打开 **Actions → Update profile cards → Run workflow**，选择 `main`。
4. 首次成功运行会生成 `profile/stats.svg` 和 `profile/top-langs.svg`，并把 README 标记区域中的远程图片替换为仓库内图片。启用之前保留原来的公开卡片。

以后每天北京时间 08:00 左右自动刷新，也可以手动运行。GitHub 可能延迟定时任务；长期无活动的公开仓库可能暂停定时工作流。
Token 到期或被撤销后，需要更新同名 Secret。失败运行不会提交错误卡片。

## 统计口径

- 获得的 Star：本人拥有的非 fork 仓库的 Star 总数。
- Commit、PR、Issue、Review：过去 365 天 GitHub `contributionsCollection` 的贡献计数，遵循 GitHub 自身的贡献归属规则；不是扫描所有分支的 Git 提交总数。贡献可以来自本人或他人的仓库。
- 语言：本人拥有的非 fork 仓库，包含私有及归档仓库，按 GitHub 返回的语言代码字节数汇总；展示前六项，占比的分母包含所有语言。
- 本版不汇总组织或其他人拥有的仓库的语言和 Star；私有统计范围受 Token 权限及组织策略限制。脚本要求 Token 属于主页本人，分页读取所有本人仓库。
- 没有 Token 时会停止生成，不会把公开数据冒充完整的私有统计。

公开 SVG 只包含汇总数字及语言比例；私有仓库名称、地址、提交信息、源码不会被请求或写入卡片和日志。汇总数字和语言比例会公开显示在主页上。

## 自定义样式

修改 `scripts/profile_stats.py` 中的 `card()`、`stats_card()`、`languages_card()` 即可调整配色、尺寸和布局。
当前卡片采用蓝灰配色，支持系统浅色 / 深色偏好。

## 本地验证

```sh
python -m unittest discover -s tests -v
```

本地生成时，通过环境变量 `PROFILE_STATS_TOKEN` 传入 Token，然后运行：

```sh
python scripts/profile_stats.py --username freeloadsk
```

## 参考

- [GitHub GraphQL API](https://docs.github.com/en/graphql)
- [GitHub Stats Extended 自用部署与 Token 说明](https://github-stats-extended.vercel.app/frontend/docs/deploy/)
- [GitHub Actions Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
