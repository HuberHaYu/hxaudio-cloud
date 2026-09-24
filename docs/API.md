# App 对接协议 · v1

仓库只提供数据：**读**全部是静态 GET，**写**（评分）走一个预留的 POST 接口。
所有 UI 都在 App 的「云端」页面实现，本文只定义数据格式和调用方式。

## 1. 基础地址

App 内置以下基础地址，按顺序尝试，记住上次成功的那个优先使用。数据里的所有 `path` 都相对于基础地址。

```
https://cdn.jsdelivr.net/gh/<用户名>/hxaudio-cloud@main/
https://fastly.jsdelivr.net/gh/<用户名>/hxaudio-cloud@main/
https://raw.githubusercontent.com/<用户名>/hxaudio-cloud/main/
```

- 国内网络下 `raw.githubusercontent.com` 经常不可达，所以 jsDelivr 排在前面。
- jsDelivr 对分支最多缓存 12 小时；仓库每次变更后 Actions 会主动刷新缓存，通常 1–2 分钟内可见。
- 以后如果接自有域名或反向代理，只需要在这个列表最前面加一项。

## 2. 调用流程

```
① GET api/v1/manifest.json                     ~1 KB，每次进入「云端」页刷新
     ├─ schema_version > 1        → 提示升级 App，不继续解析
     ├─ min_app_version_code > 本机 versionCode → 提示升级 App
     └─ index.sha256 与本地缓存相同 → 直接用缓存的 index，跳过 ②
② GET api/v1/index.json                        列表页需要的全部数据都在这里
     └─ 校验 sha256 == manifest.index.sha256；不一致说明 CDN 正处在更新间隙，
        换下一个镜像；都不一致就照常使用，但不写缓存
③ 用户点「应用」时 GET <preset.file.path>
     ├─ 校验 bytes 与 sha256，不一致就换镜像
     ├─ Hx4ProfileStore.decode(text, title)
     └─ AudioRouteMonitor.applyImported(context, loaded)
        （云端预设保证不含 devices，不要调用 DeviceProfileStore.merge）
④ 用户评分时 POST manifest.rating.submit_endpoint（为 null 时只展示评分、不开放提交）
```

`.hx4` 建议按 `(id, revision)` 缓存在本地：`revision` 变大就在列表上标记「有更新」。

所有响应都是 UTF-8 JSON。**新增字段随时可能出现，App 必须忽略不认识的字段**；只有破坏性变更才会提升 `schema_version`。

## 3. `api/v1/manifest.json`

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-23T15:21:26Z",
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
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `notice` | 维护者公告（`cloud.config.json` 里配置），非空时在「云端」页顶部显示 |
| `min_app_version_code` | 低于此 versionCode 的 App 不应使用本目录 |
| `hx4_versions` | 目录中可能出现的 .hx4 版本 |
| `index.sha256` | index.json 原始字节的 SHA-256，用于判断是否需要重新下载 |
| `rating.submit_endpoint` | 评分提交的完整 URL；`null` 表示暂未开放 App 内评分 |

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
