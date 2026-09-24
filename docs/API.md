# App 对接协议 · v1

仓库只提供数据：**读**全部是静态 GET，**写**（评分）走一个预留的 POST 接口。
所有 UI 都在 App 的「云端」页面实现，本文只定义数据格式和调用方式。

## 1. 线路

仓库通过多条线路对外提供，线路列表写在 `cloud.config.json` 的 `mirrors` 里，随签名后的 manifest 下发；App 内置同一份列表作为首次启动和兜底用。每条线路是一个 URL 模板：

```json
{ "id": "gh-proxy", "kind": "raw", "url": "https://gh-proxy.com/https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}" }
```

- `{owner}` `{repo}` `{branch}` 固定为 `HuberHaYu` `hxaudio-cloud` `main`，`{path}` 为文件在仓库中的路径
- `kind: raw` 直连 GitHub 原始文件，内容最新；`kind: cdn` 带缓存，可能滞后，但更快
- `enabled: false` 表示停用 App 内置的同名线路
- 初始顺序依据 ITDOG 全国 261 个节点（三大运营商及家庭宽带）的实测成功率。App 按每台设备的实际成功率与耗时动态调整，并在上一条线路迟迟没有响应时并行尝试下一条

2026-09 实测结果（成功节点 / 261）：gh-proxy.com 255、cdn.jsdmirror.com 259、ghproxy.net 249、jsd.onmicrosoft.cn 261、fastly.jsdelivr.net 238、ghfast.top 175、cdn.jsdelivr.net 189、raw.githubusercontent.com 154、gcore.jsdelivr.net 135、testingcf.jsdelivr.net 123。

## 2. 签名与完整性

第三方线路可以改写内容，因此 App 只信任验签通过的数据：

- `api/v1/manifest.sig` 是 `api/v1/manifest.json` 原始字节的 ECDSA P-256 / SHA-256 签名（Base64 编码的 DER）
- 公钥：`keys/manifest-signing-public.pem`，同时内置在 App 中
- manifest 记录 index.json 的 SHA-256，index.json 记录每个 .hx4 的 SHA-256，一个签名覆盖整个目录
- manifest 与签名必须来自同一条线路；验签失败即视为该线路不可用，换下一条
- `generated_at` 早于本地已缓存版本的 manifest 一律拒绝，防止旧数据回放

签名由 GitHub Actions 在每次生成 manifest 后自动完成，私钥只保存在仓库 Secret `HXCLOUD_SIGNING_KEY` 中。

## 3. 调用流程

```
① GET api/v1/manifest.json + api/v1/manifest.sig（同一条线路，优先 raw 线路）
     ├─ 验签失败 / 比本地缓存旧   → 换线路
     ├─ schema_version > 1        → 提示升级 App
     ├─ min_app_version_code > 本机 versionCode → 提示升级 App
     └─ index.sha256 与本地缓存相同 → 直接用缓存的 index，跳过 ②
② GET api/v1/index.json
     └─ SHA-256 必须等于 manifest.index.sha256，不一致（CDN 缓存滞后）就换线路
③ 用户应用预设时 GET <preset.file.path>
     ├─ bytes 与 SHA-256 必须和 index 一致，不一致就换线路
     ├─ Hx4ProfileStore.decode(text, title)
     └─ AudioRouteMonitor.applyImported(context, loaded)
        （云端预设保证不含 devices，不调用 DeviceProfileStore.merge）
④ 用户评分时 POST manifest.rating.submit_endpoint（为 null 时只展示评分、不开放提交）
```

所有响应都是 UTF-8 JSON。**新增字段随时可能出现，App 必须忽略不认识的字段**；只有破坏性变更才会提升 `schema_version`。

## 3.1 `api/v1/manifest.json`

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-24T02:53:23Z",
  "name": "HXAudio Pro 云端预设",
  "notice": "",
  "min_app_version_code": 400000001,
  "hx4_versions": [1, 2],
  "index": { "path": "api/v1/index.json", "sha256": "…", "preset_count": 3 },
  "rating": {
    "min": 1, "max": 5,
    "total_votes": 18, "global_mean": 4.278, "prior_weight": 5,
    "submit_endpoint": null,
    "issue_template": "rating.yml"
  },
  "mirrors": [ { "id": "gh-proxy", "kind": "raw", "url": "…", "enabled": true } ]
}
```

| 字段 | 说明 |
| --- | --- |
| `notice` | 维护者公告（`cloud.config.json` 里配置），非空时在「云端」页顶部显示 |
| `min_app_version_code` | 低于此 versionCode 的 App 不应使用本目录 |
| `hx4_versions` | 目录中可能出现的 .hx4 版本 |
| `index.sha256` | index.json 原始字节的 SHA-256 |
| `rating.submit_endpoint` | 评分提交的完整 URL；`null` 表示暂未开放 App 内评分 |
| `mirrors` | 下载线路，见第 1 节 |

## 4. `api/v1/index.json`

```json
{
  "schema_version": 1,
  "generated_at": "…",
  "frequencies": { "pre_eq_hz": [31, 65, …, 20000], "post_eq_hz": [20.0, 25.2, …, 20000.0] },
  "presets": [ { …见下表… } ]
}
```

每个预设：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 永久不变的主键，`[a-z0-9-]`，3–48 位 |
| `title` / `subtitle` / `description` / `author` | string | 展示文本，`subtitle`、`description` 可能为空串 |
| `tags` | string[] | 0–8 个 |
| `device_kinds` | string[] | 取值与 `AudioOutputRoute.Kind` 同名：`SPEAKER` `WIRED_ANALOG` `WIRED_USB` `BLUETOOTH` `OTHER`；**空数组表示通用**。可用当前输出设备的 Kind 做推荐或筛选 |
| `featured` | bool | 维护者精选 |
| `revision` | int | 从 1 开始，.hx4 内容每变一次 +1 |
| `created` / `updated` | `YYYY-MM-DD` | 首次上架 / 最近一次内容变化（UTC） |
| `file.path` | string | .hx4 相对路径 |
| `file.sha256` / `file.bytes` | string / int | 下载校验用 |
| `file.hx4_version` | int | 1 或 2 |
| `features.post_eq_points` | int | PostEQ 控制点数 |
| `features.bass_boost_db` | number \| null | 低频增强开启时的增益，关闭为 null |
| `features.input_gain_db` | number | 总增益 |
| `features.limiter` | bool | 是否开启主限幅器 |
| `features.virtual_surround_percent` | int \| null | 虚拟环绕宽度，关闭为 null |
| `features.volume_compensation` | bool | 响度补偿是否实际生效 |
| `features.eq_pulse` | bool | 是否带 EQ Pulse 冲激曲线 |
| `preview.pre_eq_db` | number[12] | 对应 `frequencies.pre_eq_hz` |
| `preview.post_eq_db` | number[31] | 对应 `frequencies.post_eq_hz`，与 `PostEqDefinition.sample(points)` 一致（误差 ≤ 0.005 dB） |
| `rating.count` | int | 票数 |
| `rating.average` | number \| null | 算术平均，两位小数；0 票时为 null |
| `rating.weighted` | number | 贝叶斯平均 `(C·m + Σ分数) / (C + n)`，C = `prior_weight`，m = `global_mean`，**排序请用它** |
| `rating.histogram` | int[5] | 依次为 1★…5★ 的票数 |

`preview` 让列表页不用下载 .hx4 就能画缩略曲线；它只含两段 EQ，不含低频增强、响度补偿和虚拟环绕。
建议排序：`featured` 优先，其次 `rating.weighted` 降序。

## 5. 评分提交（预留接口）

`manifest.rating.submit_endpoint` 非空时启用，由 `relay/cloudflare-worker` 实现。

```
POST <submit_endpoint>
Content-Type: application/json

{
  "preset_id": "studio-reference",
  "score": 5,
  "install_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_version": "4-Kuber"
}
```

| 字段 | 说明 |
| --- | --- |
| `score` | 整数 1–5 |
| `install_id` | 首次评分时生成一个随机 UUID 并永久保存在本机（SharedPreferences），`[A-Za-z0-9_-]{16,128}`。中转服务会用 HMAC 匿名化，公开仓库里无法反推设备 |
| `app_version` | versionName，最多 32 字符，仅用于排查问题 |

| 状态码 | body | App 处理 |
| --- | --- | --- |
| 202 | `{"ok":true,"status":"queued"}` | 已受理，约 1–2 分钟后反映到 index.json |
| 400 | `bad_json` / `invalid_preset` / `invalid_score` / `invalid_install_id` | 客户端 bug，不重试 |
| 404 | `unknown_preset` | 预设已下架，刷新目录 |
| 429 | `rate_limited`，附 `retry_after` 秒 | 同一设备 60 秒内重复评同一预设，或同一 IP 每小时超过 30 次 |
| 5xx | `upstream_failed` / `catalog_unavailable` / `relay_misconfigured` | 稍后重试 |

语义：同一 `install_id` 对同一预设只计一票，再次提交覆盖上一次。评分是异步生效的，App 应在本地记住「我的评分」并立即显示，不必等 index 刷新。
