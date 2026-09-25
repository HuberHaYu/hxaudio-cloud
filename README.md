# HXAudio Pro 云端预设

HXAudio Pro 的云端预设库。每个预设都是一份完整的音效配置（`.hx4`），包含前级与后级均衡、低频增强、增益、限幅器、虚拟环绕和响度补偿等设置。HXAudio Pro 的「云端」页面读取本仓库的数据，在 App 内浏览、应用和评分。

## 预设

<!-- presets:start -->
| 预设 | 适用设备 | 说明 | 文件 |
| --- | --- | --- | --- |
| 小米14 - HX官方曲线优化 | 手机外放（Xiaomi 14、Xiaomi 14 Pro） | 特调曲线，由 HXAudio 实验室严格提供，针对 HiRes 调音方向 | [xiaomi14-spk-huberlab-hires.hx4](presets/xiaomi14-spk-huberlab-hires/xiaomi14-spk-huberlab-hires.hx4) |
| 小米 15 Pro 浑厚人声 | 手机外放（Xiaomi 15 Pro） | 由 hxj 投稿，适用于小米15 Pro外放，人声 | [xiaomi15pro-spk-hxj.hx4](presets/xiaomi15pro-spk-hxj/xiaomi15pro-spk-hxj.hx4) |
| Redmi K60 Pro 流行音乐 | 手机外放（Redmi K60 Pro） | 适用于Redmi K60 Pro外放，流行音乐 | [k60pro-spk-papershort.hx4](presets/k60pro-spk-papershort/k60pro-spk-papershort.hx4) |
| Redmi K90 Pro Max | 手机外放（Redmi K90 Pro Max） | 由 chaoer2330 投稿，适用于K90 Pro Max的外放 | [k90promax-spk-chaoer2330.hx4](presets/k90promax-spk-chaoer2330/k90promax-spk-chaoer2330.hx4) |
| 小米 10 Ultra - 外放特调 | 手机外放（Mi 10 Ultra） | 针对小米 10 Ultra的外放特调，修复中高频发糊、低频不浑厚的问题 | [mi10ultra-spk-huber.hx4](presets/mi10ultra-spk-huber/mi10ultra-spk-huber.hx4) |
| Redmi Buds6 Pro | 蓝牙耳机 | Redmi Buds6 Pro耳机高频细节调教 | [redmi-buds6-pro.hx4](presets/redmi-buds6-pro/redmi-buds6-pro.hx4) |
| 小米14（Xiaomi 14） | 手机外放（Xiaomi 14） | 小米14外放配置 | [xiaomi-14-spk.hx4](presets/xiaomi-14-spk/xiaomi-14-spk.hx4) |
| 小米随身音箱 | 其他设备 | 小米随身音箱，低频优化 | [xiaomi-bt-pocket-spk.hx4](presets/xiaomi-bt-pocket-spk/xiaomi-bt-pocket-spk.hx4) |
| 小米15/15Pro | 手机外放（Xiaomi 15、Xiaomi 15 Pro） | 小米15/15Pro，全频段优化 | [xiaomi15-se-spk.hx4](presets/xiaomi15-se-spk/xiaomi15-se-spk.hx4) |
| 小米 15 Pro杜比全景哈曼卡顿音效 | 手机外放（Xiaomi 15 Pro） | 由 ttzkyz 上传，适用于小米 15 Pro外放，饱满低频，全频段优化提升 | [xiaomi15pro-ttzkyz.hx4](presets/xiaomi15pro-ttzkyz/xiaomi15pro-ttzkyz.hx4) |
<!-- presets:end -->

## 使用

**在 App 中**：打开「云端」页面，可以按名称、标签或耳机型号搜索，「适合当前设备」只列出为你当前的手机或耳机型号调校的预设。选择预设后可以先试听，再应用到当前正在播放的输出设备，其他设备已保存的调音不受影响。

**手动导入**：下载上表中的 `.hx4` 文件，在 App 首页的「配置文件」卡片中点「导入」，选择该文件。

预设按适用设备标注。扬声器与耳机的频响差异较大，为耳机调校的预设用在手机外放上，听感可能明显不同，反之亦然。

## 评分

每个预设可评 1–5 星。每位用户对同一预设只计一票，重复评分以最后一次为准，汇总结果通常在 1–2 分钟内更新。

- 在 App「云端」页面登录 GitHub 后，于预设详情中评分
- 也可以在本仓库的 Issues 中使用「⭐ 给预设评分」模板提交

评分需要 GitHub 账号。App 只获得在本仓库提交评分的权限，无法访问你的代码或其他仓库。

仓库中的投票记录只保存账号的不可逆散列标识。

## 数据接口

预设目录与评分以静态 JSON 提供，可通过 HTTPS 直接读取：

| 内容 | 地址 |
| --- | --- |
| 目录信息 | `https://cdn.jsdelivr.net/gh/HuberHaYu/hxaudio-cloud@main/api/v1/manifest.json` |
| 预设列表与评分 | `https://cdn.jsdelivr.net/gh/HuberHaYu/hxaudio-cloud@main/api/v1/index.json` |
| 备用地址 | 将前缀替换为 `https://raw.githubusercontent.com/HuberHaYu/hxaudio-cloud/main/` |

字段定义与评分提交接口见 [docs/API.md](docs/API.md)。

## 校验

每次更新都会自动校验全部预设：所有参数必须在 App 允许的范围内，文件不含设备专属数据。目录中为每个文件记录了 SHA-256 摘要，可用于校验下载内容。

## 维护

预设由 HXAudio Pro 维护者整理发布，维护流程见 [docs/MAINTAINING.md](docs/MAINTAINING.md)。
