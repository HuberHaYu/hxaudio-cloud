# 评分中转服务（第二阶段，现在不用部署）

```
App ──POST──▶ Worker（校验、限流、匿名化）──repository_dispatch──▶ Actions「评分（App 接口）」──▶ ratings/ + index.json
```

App 里不能放 GitHub 令牌（反编译即可拿到），所以令牌只存在这个 Worker 的 secret 里。
Worker 会先确认预设存在、分数合法，再把 `install_id` 用 HMAC 匿名化后转交 GitHub。

## 部署

1. **创建 GitHub 令牌**：GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token
   - Repository access：Only select repositories → `hxaudio-cloud`
   - Repository permissions → **Contents: Read and write**（repository_dispatch 需要这一项）
   - 有效期最长一年，到期前记得续期
2. **准备 Cloudflare**：注册账号后在本目录运行 `npx wrangler login`
3. 修改 `wrangler.toml` 里的 `GITHUB_REPO` 为 `<用户名>/hxaudio-cloud`
4. 写入两个 secret：
   ```bash
   npx wrangler secret put GITHUB_TOKEN     # 粘贴第 1 步的令牌
   npx wrangler secret put VOTER_SALT       # 粘贴一串随机字符，例如 openssl rand -base64 32 的输出
   ```
   `VOTER_SALT` 上线后**不要再改**，改了之后所有设备都会被当成新投票人。
5. （建议）开启限流：`npx wrangler kv namespace create RATING_KV`，把输出的 id 填进 `wrangler.toml` 并取消注释
6. 部署：`npx wrangler deploy`
7. **绑定自有域名**：`*.workers.dev` 在国内网络下很不稳定，在 Cloudflare 控制台 Workers → 本服务 → Settings → Domains & Routes 添加自定义域名
8. 测试：
   ```bash
   curl -X POST https://<你的域名>/v1/ratings -H 'Content-Type: application/json' \
     -d '{"preset_id":"studio-reference","score":5,"install_id":"test-install-000000000001","app_version":"test"}'
   ```
   返回 `202` 后到仓库 Actions 页应能看到一次「评分（App 接口）」运行
9. 在仓库的 `cloud.config.json` 里设置 `"submit_endpoint": "https://<你的域名>/v1/ratings"` 并推送，App 即开放评分

## 额度与限制

- Workers 免费版每天 10 万次请求；KV 免费版每天 1000 次写入，限流每次评分写 2 次，约够每天 500 次评分
- 公开仓库的 Actions 分钟数免费；每次评分对应一次约 20 秒的运行和一次提交
- 匿名评分无法彻底防止伪造 `install_id` 刷票，限流只是提高成本。量大后可以接入 Play Integrity，或改为 Worker 批量汇总后定时提交
