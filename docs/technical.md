# 技术说明与兼容范围

Windows 托盘工具：**优先直接显示网易云高清原封面**，获取不到时使用成熟的 **Real-ESRGAN NCNN/Vulkan** 超分系统缩略图，再通过 Windows 标准媒体会话交给 Wallpaper Engine。换壁纸无需重新适配，不读取、不解包、不修改任何壁纸文件。

高清原图不经过 AI 超分。只有回退处理低清封面且未命中缓存时才启动推理，完成后立即释放 GPU；无需 PyTorch、CUDA、本地网页服务、网易云账号或 cookie。

## 使用

需要 Windows 10/11 x64、可用的 Windows 媒体组件、Wallpaper Engine，以及支持 Vulkan 的显卡驱动。

1. 完整解压便携包，运行 `WallpaperCoverSR.exe`。
2. 正常应用壁纸并播放音乐，确认原壁纸能识别歌曲封面。
3. 开启 **启用封面增强**，默认勾选 **优先使用网易云高清原封面（联网）**。高清原图直接显示；下方 **2× / 3× / 4×** 仅在获取失败、回退超分时生效。不需要选择壁纸文件夹。
4. 按需勾选 **登录 Windows 时在后台启动**；Wallpaper Engine 的自启动在它自己的设置中开启。

关闭窗口会收起到托盘；双击托盘或再次运行程序可打开设置。取消增强开关、点击“恢复播放器封面”或退出程序后，恢复播放器提供的原封面。程序不会产生声音或启动静音音频播放。

从 0.1 / 0.2 升级：退出旧程序后用新包替换，直接应用创意工坊原壁纸即可；旧版生成的本地增强副本不再需要。设置和封面缓存继续保存在用户数据目录中。

## 高清原封面

0.3 默认开启联网高清模式，界面可关闭。已在网易云音乐 Windows 3.1.41.205529 验证：只读本地 `webdata/file/playingList`，按真实 SMTC 的歌名、歌手以及可用专辑信息筛选曲目，取得其中的官方 CDN 封面地址。不通过歌名在线搜索，不读取 cookie 或账户凭据。下载后还要与系统缩略图核对颜色和空间结构；无法可靠核对、多个版本不确定或近乎纯色的封面会回退。

本机三张135×135缩略图成功取得1500×1500、1832×1832、3508×3508原图。最长边超过1024像素时用 Lanczos 缩到1024后发布，保留真实画面，不进行 AI 超分或额外锐化。原图短边不足400像素不使用这条路径。缓存命中无需联网。

只允许 `p数字.music.126.net` 官方图片主机的 HTTPS 请求及同类重定向，限制文件/图像大小和读取时间。网络或队列失败时回退，约60秒后有条件重试；重试期间保留同一首歌已验证的封面。切歌后不会发布过期任务。

默认队列路径为 `%LOCALAPPDATA%\NetEase\CloudMusic\webdata\file\playingList`。客户端更新、商店版或其他播放器不保证使用这一格式；不支持时保留系统封面流程。自定义数据目录可退出程序后在 `config.json` 的 `netease_playlist` 填队列文件绝对路径，留空使用默认路径。

## 通用的范围

本工具接入 **Windows 系统媒体封面**，无需针对壁纸编号、包版本、封面图层、特效或显示器写适配器。已通过真实渲染验证：

- 创意工坊 `3571726810`：独立歌曲封面图层。
- 创意工坊 `3395777145`：通过特效采样当前/上一张封面的场景，包含过渡混合；原封面效果保留。

两张壁纸均直接使用原项目，原文件哈希保持不变。这里的“通用”指接入同一 Windows 媒体接口的壁纸，不代表所有创意工坊作品都兼容。作者直接从音乐网站请求图片、自带播放器或固定图片的壁纸不经过该接口，无法由本工具替换。网页壁纸尚未完成实机兼容验证，暂不列为已支持范围。

播放器也必须提供 Windows 媒体会话。已实测网易云音乐；其他标准媒体播放器按同一路径接入，但尚未逐一验证。若原壁纸没有歌曲信息，请先开启播放器的系统媒体集成。本工具不代替 InfLink 等媒体接入方案。

默认自动选择当前外部媒体源，排除自身以避免反复超分。多个应用同时播放时会跟随 Windows 当前外部会话；需要固定来源时，退出程序并在 `config.json` 的 `source_app` 填入播放器的 AppUserModelID，例如 `cloudmusic.exe`，留空为自动选择。

工具启用时，Windows 媒体面板会多一个 `WallpaperCoverSR` 会话，歌名/歌手、播放状态与时间线来自真实播放器。标准播放、暂停、停止、上一首、下一首和定位请求转发给原播放器。如果壁纸设有媒体应用白名单，需要允许 `WallpaperCoverSR` 或使用自动选择；强制只选 `cloudmusic.exe` 会继续显示其原始缩略图。其他使用“当前系统媒体”的软件也可能读到增强会话。

## 性能和效果

默认模型为官方 `realesrgan-x4plus`，原生推理 4×。2×/3×由 4×缓存用 Lanczos 缩小，**较低倍率不代表按比例降低首次推理负载**。支持在配置中使用 `realesrgan-x4plus-anime`，界面保持简洁。

封面长边达到 512 像素时直接使用原图，不再放大。小封面使用 128 像素分块，显存峰值取决于硬件与驱动。135×135 的真实缩略图在本机首次处理约 1.8–2.0 秒，4×输出为 540×540；缓存命中不再推理。这些不是其他机器的性能保证。

变化事件触发更新，30 秒低频检查封面作为兜底；每 8 秒同步播放状态和时间线。快速切歌、关闭开关、调整倍率会取消过时工作。处理期间使用真实播放器的封面，完成后再发布增强图。缓存预算约 128 MiB。

超分不能恢复已经丢失的真实信息，尤其可能错误重建小字。后台占用与实测范围见 [VALIDATION.md](../VALIDATION.md)。

## 实现

`真实播放器 SMTC → 网易云队列匹配 / 官方 CDN 高清原图 → 图像核对 / 缓存 → 内存 PNG → Windows SMTC 增强会话 → 原壁纸`

高清模式关闭或失败时：`系统缩略图 → 缓存 / Real-ESRGAN 子进程 → 同一媒体桥接`。

使用公开的 Windows MediaPlayer 手动媒体控件，不设置音频源。程序退出后会话由 Windows 撤销；壁纸继续使用真实播放器。不会修改系统组件、注入播放器或修补 Wallpaper Engine。部分壁纸可能需要等待自身下一次媒体刷新才回退。

接口依据：[微软手动 SMTC](https://learn.microsoft.com/windows/apps/develop/media-playback/system-media-transport-controls)、[Wallpaper Engine 场景专辑封面](https://docs.wallpaperengine.io/en/scene/audiovisualizer/albumcover.html)。

## 源码与构建

Python **3.13 x64**：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\download_backend.py
.\.venv\Scripts\python.exe run.py
```

构建便携包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

输出为 `release/WallpaperCoverSR-0.3.0-windows-x64.zip` 及源码 zip、SHA256 文件。使用 onedir，避免每次启动解压模型。GitHub Actions 会构建并上传 artifact；不自动公开发布 Release。上传源码包内容即可创建自己的仓库，不要上传 `.venv`、`vendor`、缓存或任何壁纸素材。

后端固定使用[官方 v0.2.5.0 的 20220424 Windows NCNN 压缩包](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0)，下载时校验 SHA256。只打包程序、正式 OpenMP 运行时及两种图像模型，不包含示例视频、调试 DLL。这里固定的是经过验证的版本，并非宣称上游最新版本。

单元测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

真实接口回归：退出本工具，保持 Wallpaper Engine 和提供 SMTC 的音乐播放器运行，执行 `scripts/verify_integration.py`。检查 2×/3×/4× 的实际系统媒体图片、元数据与关闭/退出回退。可重复传入 `--case PROJECT LEFT TOP RIGHT BOTTOM` 检查指定场景壁纸在 1280×720 原生预览窗口中的封面区域。测试临时发布绿色测试图并关闭预览，不改动项目文件。`--external-helper` 可检查已经运行的便携版，确认实际系统缩略图字节与输出文件一致；加 `--require-hd` 可要求输出为核对后的高清原封面。

## 数据与卸载

- 设置、状态、滚动日志和封面缓存：`%LOCALAPPDATA%\WallpaperCoverSR`。
- 开机启动：当前用户 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\WallpaperCoverSR`，无需管理员权限。
- 高清模式仅向网易云官方图片 CDN 请求封面，不上传缩略图、不发送歌名或账号信息，无遥测。关闭高清选项后为离线超分；构建时从上游下载依赖。
- 卸载前取消开机启动并从托盘退出，删除程序文件夹。用户数据目录可按需删除。0.2 及后续版本不生成或暂存任何文件到壁纸目录。

## 许可证

程序与界面采用 MIT；后端和依赖保留各自许可证，见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。专辑封面和壁纸属于原作者，不随项目分发。



返回 [项目首页](../README.md)。
