# HXAudio Pro 云端预设

HXAudio Pro 的云端预设库。每个预设都是一份完整的音效配置（`.hx4`），包含前级与后级均衡、低频增强、增益、限幅器、虚拟环绕和响度补偿等设置。HXAudio Pro 的「云端」页面读取本仓库的数据，在 App 内浏览、应用和评分。

## 预设

<!-- presets:start -->
| 预设 | 适用设备 | 说明 | 文件 |
| --- | --- | --- | --- |
| 录音室参考 | 3.5mm 有线耳机、USB 耳机、蓝牙耳机 | 耳机通用 · 中性耐听 | [studio-reference.hx4](presets/studio-reference/studio-reference.hx4) |
| 人声清晰 | 手机外放 | 手机外放 · 对白与播客 | [vocal-clarity-speaker.hx4](presets/vocal-clarity-speaker/vocal-clarity-speaker.hx4) |
<!-- presets:end -->

## 使用

**在 App 中**：打开「云端」页面，选择预设后应用。预设只作用于当前正在播放的输出设备，其他设备已保存的调音不受影响。

**手动导入**：下载上表中的 `.hx4` 文件，在 App 首页的「配置文件」卡片中点「导入」，选择该文件。

预设按适用设备标注。扬声器与耳机的频响差异较大，为耳机调校的预设用在手机外放上，听感可能明显不同，反之亦然。

## 评分

每个预设可评 1–5 星。每位用户对同一预设只计一票，重复评分以最后一次为准，汇总结果通常在 1–2 分钟内更新。

- App 内评分开放后，可在「云端」页面直接评分
- 也可以在本仓库的 Issues 中使用「⭐ 给预设评分」模板提交（需要 GitHub 账号）

评分以匿名方式记录。仓库中只保存不可逆的散列标识，不包含账号、设备或其他个人信息。

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
