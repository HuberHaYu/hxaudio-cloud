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
⓪ GET <代理>/https://github.com/HuberHaYu/hxaudio-cloud.git/info/refs?service=git-upload-pack
     └─ git 的分支信息，任何线路都不缓存；从中读出 main 当前的提交 SHA
        与本地缓存的提交相同 → 没有更新，结束
① GET api/v1/manifest.json + api/v1/manifest.sig（按上一步的提交 SHA 固定地址，同一条线路）
     ├─ 验签失败 / 比本地缓存旧   → 换线路
     ├─ schema_version > 1        → 提示升级 App
     ├─ min_app_version_code > 本机 versionCode → 提示升级 App
     └─ index.sha256 与本地缓存相同 → 直接用缓存的 index，跳过 ②
② GET api/v1/index.json（同一提交）
     └─ SHA-256 必须等于 manifest.index.sha256
③ 用户应用预设时 GET <preset.file.path>（同一提交）
     ├─ bytes 与 SHA-256 必须和 index 一致
     ├─ Hx4ProfileStore.decode(text, title)
     └─ AudioRouteMonitor.applyImported(context, loaded)
        （云端预设保证不含 devices，不调用 DeviceProfileStore.merge）
④ 用户评分：登录 GitHub 后以其账号提交评分 issue，见第 5 节
```

按分支读取的地址（`main`）会被 GitHub 原始文件 CDN 缓存 5 分钟（加查询参数也无效），部分 jsDelivr 镜像会缓存数小时；按提交 SHA 读取的地址每次提交都是新的，任何线路都拿不到旧内容。所有线路都查询不到提交时，才退回按分支读取，并优先使用 raw 线路。App 打开云端页时检查一次，停留期间每 45 秒检查一次。

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
    "github_client_id": null,
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
| `rating.github_client_id` | App 内 GitHub 登录所用 GitHub App 的 Client ID；`null` 表示暂未开放 App 内评分 |
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
| `device_kinds` | string[] | 取值与 `AudioOutputRoute.Kind` 同名：`SPEAKER` `WIRED_ANALOG` `WIRED_USB` `BLUETOOTH` `OTHER`；**空数组表示通用** |
| `target_devices` | object[] | 适配机型 `{kind, name, aliases}`。App 的「适合当前设备」只认型号匹配：外放比对手机市场名与型号代码，蓝牙 / USB 比对系统报告的产品名（忽略大小写、空格和符号；4 个字符以上的名称允许被包含）。3.5mm 耳机无法识别型号，不参与匹配 |
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

## 5. 评分提交

评分需要登录 GitHub，每个 GitHub 账号对同一预设只计一票，再次评分覆盖上一票。不需要任何自建服务器：

1. **登录**：GitHub 的设备授权流程（不需要 client secret）。App 请求 `POST https://github.com/login/device/code`（`client_id` 取自 `manifest.rating.github_client_id`），把验证码复制到剪贴板并拉起 `https://github.com/login/device`（有 GitHub App 时由其打开，否则用浏览器）；用户粘贴验证码授权后，App 轮询 `POST https://github.com/login/oauth/access_token` 取得令牌。
2. **权限**：令牌属于一个只有「Issues 读写」权限、且只安装在本仓库上的 GitHub App，因此只能在本仓库提交 issue，无法访问用户的其他仓库。令牌只发往 github.com 与 api.github.com，不经过任何第三方加速线路，在手机上用 Android Keystore 加密保存。
3. **提交**：`POST https://api.github.com/repos/HuberHaYu/hxaudio-cloud/issues`，格式与 Issue 表单相同：

```
title: [评分] <预设标题>
body:
### 预设

<预设 ID> · <预设标题>

### 评分

<1–5> ★★★★★
```

4. **记票**：仓库的「评分（Issue 表单）」工作流解析 issue、以 `gh:<用户 ID>` 记票、回复并关闭 issue，随后重建并签名目录。App 的定时检查会在约一分钟内拿到新的汇总。
