# Voice Sprite 语音精灵

面向荣耀 V10 / Android 10 的儿童知识伙伴：手机录音 → 硅基流动 ASR → DeepSeek 对话 → 硅基流动 CosyVoice2 云端语音 → Android 媒体播放 / 蓝牙音箱。可切回 Android 系统 TTS。Python 仅使用标准库，无需 pip 安装依赖。

默认保留手动轮流对话；新增 `--auto` 自动监听、按静音断句、朗读后继续监听。支持独立人设文件和最近 6 轮上下文。自动模式使用 PulseAudio 连续采集和音量阈值检测，尚未实现名字唤醒、播放中打断或发音评分；需在手机实测兼容性。

## 1. 手机准备

1. 从 [F-Droid 安装 Termux](https://f-droid.org/packages/com.termux/)，并从同一来源安装 [Termux:API](https://f-droid.org/packages/com.termux.api/)。两者是不同的安卓应用，签名来源必须兼容。仅安装命令包不能代替 Termux:API 应用。
2. 打开 Termux 和 Termux:API；在系统应用权限设置中允许 Termux:API 使用麦克风（如 Termux 也请求权限，按需允许）。
3. 连接蓝牙音箱，启用“媒体音频”，调整媒体音量。
4. 在系统设置中搜索“文字转语音”或“TTS”，选择支持英语的引擎，并下载英语离线语音包。如果系统没有可用引擎，需要先安装兼容的 Android TTS 引擎。项目本身不附带语音包。
5. 在荣耀“应用启动管理”中，给 Termux 和 Termux:API 允许后台活动。初次测试保持 Termux 在前台、屏幕亮着；息屏稳定性需单独验证。

## 2. 将当前代码放进手机（无需 GitHub 推送）

在电脑的项目目录执行：

```bash
bash scripts/package.sh
```

得到 `dist/voice-sprite.tar.gz`。用 USB 文件传输等方式将它复制到手机内部存储的 `Download` 文件夹。

在手机 Termux 中执行：

```bash
termux-setup-storage
# 系统弹出存储访问请求时允许
mkdir -p ~/voice-sprite
cd ~/voice-sprite
tar -xzf ~/storage/downloads/voice-sprite.tar.gz
bash scripts/setup-termux.sh
```

代码应运行在 `~/voice-sprite`（Termux 私有目录）中，不要直接在共享存储中运行。安装脚本通过 pkg 安装 Python、termux-api 命令包、ffmpeg 和 pulseaudio，并创建 `.env` 与 `persona.txt`，不会覆盖已有配置或人设。

可选 Git 部署：只有在本次代码已提交并推送到仓库后，才可用以下方法获得它；本地初始化不会自动上传 GitHub。

```bash
pkg install git
git clone https://github.com/shengliang74/voice-sprite.git
cd voice-sprite
bash scripts/setup-termux.sh
```

若仓库私有，需自行配置 GitHub 访问凭据；初次部署建议使用上面的压缩包方式。

## 3. 配置两个云端服务

- ASR：在 [硅基流动控制台](https://cloud.siliconflow.cn/) 创建 API Key，并确认账户可以访问 `FunAudioLLM/SenseVoiceSmall`。
- 对话：在 [DeepSeek 开放平台](https://platform.deepseek.com/) 创建 API Key。聊天 App 账号/订阅不等于已配置 API 额度。
- 服务可能收费，实际额度、模型可用性和价格以各平台为准。

在手机中编辑配置：

```bash
pkg install nano
nano .env
```

填写以下两行，其余配置先保持默认：

```dotenv
ASR_API_KEY=你的硅基流动密钥
LLM_API_KEY=你的DeepSeek密钥
```

nano 中按 Ctrl+O、回车保存，Ctrl+X 退出（Termux 可使用扩展按键栏中的 Ctrl）。不要把真实密钥发到聊天或提交到 Git。`.env` 已被 Git 忽略，打包脚本也不会打包它；请勿用 shell `source .env`，程序会自行读取配置。环境变量优先于 `.env`。

默认模型按官方文档配置为 `FunAudioLLM/SenseVoiceSmall` 和 `deepseek-flash`。模型更名或账户不可用时，修改 `.env` 中的 `ASR_MODEL` / `LLM_MODEL`。BASE_URL 是基础地址，不能包含 `/audio/transcriptions` 或 `/chat/completions` 后缀，程序会追加。

## 4. 分步测试与运行

先检查安装和密钥（不发送网络请求）：

```bash
python voice_sprite.py --doctor
```

测试当前 TTS 和蓝牙音箱（默认调用硅基流动，会计费）：

```bash
python voice_sprite.py --tts-test
```

默认云端 TTS 需要联网，不使用系统 TTS 音色。如要测试离线朗读，先在 `.env` 设置 `TTS_PROVIDER=android`，再关闭 Wi-Fi 和移动数据、保留蓝牙测试；第三方系统引擎能否离线取决于其音色包。

恢复网络，先测试文字对话：

```bash
python voice_sprite.py --text
```

输入 `Let's practice ordering coffee.`，收到回答后输入 `/quit`。此模式只调用大模型，不录音、不朗读，也可在电脑上运行。

最后启动完整语音模式：

```bash
python voice_sprite.py
```

1. 按回车启动录音，**看到“正在录音”后再说话**。
2. 说完按回车，或等默认 30 秒自动结束。
3. 等待识别、回答和朗读；看到识别文字可检查是否听错。
4. 等音箱播放完全结束后再按回车，开始下一轮。

| 命令 | 功能 |
| --- | --- |
| `/quit` 或 Ctrl+C | 退出；正在录音时会尝试停止录音 |
| `/reset` | 清空本次对话历史 |
| `/repeat` | 重播上一条回答；文字模式只显示 |
| `/slow` | 降低后续朗读语速；结合 `/repeat` 使用 |

语音模式下命令在终端输入；录音内容本身不会作为本地命令执行。可在对话中要求更换话题或中文解释，默认云端音色支持中英文。Android 模式会按语音选择的语言切换 zh-CN / en-US，需要系统引擎提供对应语音包。修改 `.env` 后重启程序。

## 自动对话与独立人设

更新代码后，在手机项目目录执行安装脚本补齐依赖：

```bash
bash scripts/setup-termux.sh
nano persona.txt
python voice_sprite.py --auto
```

`persona.txt` 是 UTF-8 普通文本，可以写名字、英语水平、偏好话题、回答长度和纠错规则，例如：

```text
你叫小灵，是我的英语口语陪练。我的水平是 A2。
默认用简单英语，每次最多三句，并追问一个问题。
我说没听懂时先用中文解释，再用英语重复。
不要根据转写文字判断我的发音。
```

每次请求会重新读取人设；想清除旧对话影响，可以重启程序。文件缺失时默认读取 `persona.example.txt`；显式配置 `PERSONA_FILE` 时，文件不存在或为空会报错。相对路径以项目目录为基准。人设会作为系统提示词发送给大模型，聊天记录仍只保存在内存。`persona.txt` 被 Git 忽略，部署包只包含示例，不覆盖你的定制内容。

自动模式操作：

1. 确保 `--tts-test` 可正常完成，并允许 Termux / Termux:API 使用麦克风和后台运行。第一次保持手机 Termux 在前台，屏幕亮着。
2. 启动 `--auto`，看到“正在监听”后直接说话。默认停顿 1.8 秒后结束一句，从检测到声音起最多录 30 秒。
3. 识别、生成回答、朗读期间不采集下一轮音频；TTS 返回后等待 0.8 秒再监听。蓝牙有残余声音时可增加冷却时间。
4. 没有足够长的声音时不调用云端；每 30 秒重新开始等待。出现网络、录音或 TTS 错误时暂停，按回车才恢复，避免自动重试。
5. **Ctrl+C 退出**。自动模式正常监听时不读取 `/repeat` 等终端命令，支持下面列出的语言、名字和角色指令；其他语音不会作为 shell 命令执行。需要这些命令时使用默认手动模式。

现有手机 `.env` 可以追加以下配置（不追加也会使用这些默认值）：

```dotenv
SILENCE_SECONDS=1.8
VAD_THRESHOLD=600
MIN_SPEECH_SECONDS=0.3
LISTEN_TIMEOUT=30
PLAYBACK_COOLDOWN=0.8
```

- 还没说完就结束：把 `SILENCE_SECONDS` 调为 `2.5` 或 `3`。
- 小声说话不触发：适当降低 `VAD_THRESHOLD`，例如 `300`。
- 环境噪声误触发：适当提高阈值，例如 `1000`，并远离背景音乐。它是音量检测，不是能区分人声和音乐的神经网络 VAD。
- `module-sles-source` 加载失败、音频流无数据：检查麦克风权限和占用，保持前台。不同 Android / Termux 组合可能不支持这条采集路径；可先退回 `python voice_sprite.py` 手动模式。不要同时运行两个实例。

自动采集使用 Termux 的 [OpenSL ES 麦克风模块](https://github.com/termux/termux-packages/blob/master/packages/pulseaudio/module-sles-source.c)，选择麦克风源而不是音箱监听源。朗读等待依据 [Termux:API 的 TTS 完成回调](https://github.com/termux/termux-api/blob/master/app/src/main/java/com/termux/api/apis/TextToSpeechAPI.java)。若系统引擎静默失败，命令可能返回却没有声音，因此实机试听仍是必要步骤。

## 5. 常见问题

- **API 命令一直等待/超时**：检查是否安装了 Termux:API 安卓应用，而不只是 `pkg install termux-api`；检查两款应用来源、麦克风权限和后台权限。
- **录音失败**：关闭其他占用麦克风的应用；执行 `termux-microphone-record -i` 查看状态。若确认是之前中断残留的录音，可执行 `termux-microphone-record -q` 后重试。
- **没有声音/仍从手机出声**：检查蓝牙媒体音频开关、媒体音量、默认 TTS 引擎与英语语音包。可运行 `termux-tts-engines` 查看引擎，再将包名填入 `TTS_ENGINE`。
- **音频转换失败**：ffmpeg 错误常表示上一步录音没有成功，先检查权限和录音文件是否有效。不要同时启动多个语音精灵实例。
- **401/403/402**：检查对应服务 API Key、模型访问权限及账户余额。
- **404**：检查 `.env` 中基础 URL 和模型名称。**429**：限流或额度不足，稍后再试。
- **网络超时**：检查手机能否访问两个 API 服务；默认超时 90 秒，可在 `.env` 调整。失败不会自动反复请求，避免重复计费；失败轮次不写入对话历史。
- **英语被截断**：手动结束可以容忍长停顿，必要时将 `RECORD_SECONDS` 提高（上限 120 秒）。
- **息屏退出**：先取消两款应用电池优化。可尝试 `termux-wake-lock`，结束后执行 `termux-wake-unlock`；它不保证绕过厂商后台限制。当前版本不安装开机自启服务。

## 数据与当前限制

录音上传到 ASR 服务，识别文字、人设及最近对话上传到大模型服务；云端 TTS 还会上传待朗读文字。录音和生成的语音在处理结束或正常异常退出后删除，对话历史只保存在内存；强制杀进程可能留下系统临时文件。终端仍会显示转写和回答。云端保留策略以服务商条款为准。

自动模式支持基础音量/静音断句，但无回声消除或播放中打断；手动模式务必等播放结束再录音。手机端接口及真实云端请求需要你填写密钥后实测，自动化测试使用模拟响应，不能代替实机验收。

## 开发验证

Python 3.9+，无需 pip 依赖：

```bash
python3 -m unittest discover -s tests -v
python3 voice_sprite.py --help
bash scripts/package.sh
```

更新手机代码时先退出程序，再解压新部署包到原目录；包里没有 `.env` 和 `persona.txt`，已有配置与人设会保留。更新后运行 `--doctor`。

接口参考：[Termux:API](https://github.com/termux/termux-api)、[录音命令](https://github.com/termux/termux-api-package/blob/master/scripts/termux-microphone-record.in)、[硅基流动 ASR](https://docs.siliconflow.cn/docs/api/audio-transcriptions-post)、[DeepSeek API](https://api-docs.deepseek.com/guides/harness)。

## 语音切换语言、名字和角色

默认中文、名字“小灵”、角色“儿童知识伙伴”。下面每条单独说一句，等确认后再问问题：

| 说法示例 | 效果 |
| --- | --- |
| 请用英文回答 / 我们练英语 / Switch to English | 切换英语回答 |
| 切回中文 / 请用中文回答 / Switch to Chinese | 切换中文回答 |
| 以后你叫小星星 / 把你的名字改成小宇 / Your name is Nova | 修改 AI 名字 |
| 切换成太空探险家 / 请扮演恐龙老师 | 修改 AI 角色 |

语言切换支持称呼、礼貌前缀和语气词，例如“小灵，你能不能用英文跟我聊天呀”“接下来我们用英语聊吧”“换成中文说好吗”“Could you please answer in English?”。仍是本地规则识别，不是任意语义理解；请将切换要求单独说一句。不会仅因为提到英语、引用指令或说“不要用英文回答”就切换。改名和角色仍使用表中的明确句式；识别错字会影响命令。普通问题（例如“为什么这个星球叫火星”）不会触发改名。指令在 ASR 后本地处理，不调用大模型，但语音确认仍使用所选 TTS 并计费。名字不等于唤醒词。

设置保存到项目目录的 `conversation.json`，重启保留。每次修改清空当前聊天历史，让新角色立即生效；`/reset` 只清空聊天，不重置名字或语言。停止程序后删除该文件即可恢复默认。该文件不进 Git、不打包，更新不会覆盖。

## 硅基流动云端朗读

云端后端复用现有硅基流动 `ASR_API_KEY`；最新配置示例使用中英混合后端，见文末。可在手机 `.env` 显式添加：

```dotenv
TTS_PROVIDER=siliconflow
TTS_API_KEY=
TTS_BASE_URL=https://api.siliconflow.cn/v1
TTS_MODEL=FunAudioLLM/CosyVoice2-0.5B
TTS_VOICE=FunAudioLLM/CosyVoice2-0.5B:diana
CLOUD_TTS_SPEED=1.0
```

`TTS_API_KEY` 留空仅在上述官方地址时复用 ASR 密钥；自定义地址必须单独配置密钥。默认 `diana` 是欢快女声，`claire` 是温柔女声，`alex` 是沉稳男声。换名字/角色不会自动换音色。云端语速使用 `CLOUD_TTS_SPEED`；`TTS_RATE` 仅用于 Android 模式。`/slow` 调整当前后端语速。

音频整句生成后播放，目前不是流式播放。等待媒体播放器报告结束，才恢复录音；音频临时文件随后删除。错误会暂停自动模式，不自动重复计费请求。`/repeat` 会重新合成，产生新的 TTS 费用。蓝牙仍由 Android 媒体输出路由控制，云端 TTS 无法修复蓝牙配对问题。

更新已有手机时，解压新版并执行安装脚本。如果希望使用新的儿童人设，先备份再替换（否则旧的人设会被保留）：

```bash
cp persona.txt persona.backup.txt
cp persona.example.txt persona.txt
python voice_sprite.py --doctor
python voice_sprite.py --tts-test
python voice_sprite.py --auto
```

### 供应商调查（2026-10-03）

- DeepSeek：[模型接口](https://api-docs.deepseek.com/api/list-models/)列出的输出模态为 text，没有找到公开 TTS 接口；继续用于回答。
- 硅基流动：[CosyVoice2 接口](https://docs.siliconflow.cn/docs/api/audio-speech-post)和[预设音色文档](https://docs.siliconflow.cn/docs/userguide/capabilities/text-to-speech)适合当前中英单人对话，可复用账号，因此本项目接入它。没有进行供应商之间的盲听或延迟实测。
- 阿里云百炼：[官方价格页](https://help.aliyun.com/zh/model-studio/model-pricing)列出 cosyvoice-v3.5-flash 为 0.8 元/万字符、plus 为 1.5 元/万字符。按 50 个计费字符示例分别约 0.004 元和 0.0075 元；不是本项目已接入模型的报价。
- 硅基流动文档按 UTF-8 字节计费，通常一个汉字占 3 字节，不能直接把字节价当汉字价。[国内价格页](https://siliconflow.cn/pricing)抓取结果显示 0.05 元，但未完整显示单位，需在国内账号模型详情确认。[国际站](https://www.siliconflow.com/en/pricing)显示 CosyVoice2 为 7.15 美元/百万 UTF-8 字节；50 个常见汉字（约 150 字节）约 0.00107 美元，仅适用于该报价，不代表国内账号结算价。

语音识别、大模型和 TTS 分别计费，以实际账户模型详情和账单为准。新增功能经过模拟接口测试和本地音频管道测试；尚未在荣耀实机或真实付费 TTS 请求上验收。

## 中文小雅本地合成 + 英文云端 Diana

当前配置示例使用 `TTS_PROVIDER=hybrid`。按当前对话语言选择后端：中文使用指定的 Android 小雅引擎，英文使用硅基流动 Diana。不是逐句语言检测或中英混读自动分段；中文模式中大量英文可能读不好，可先说“请用英文回答”。

1. 从[小雅官方转换模型页面](https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese/vits-piper-zh_CN-xiao_ya-medium.html)展开 **Android APK**，安装适合手机架构的 **TTS Engine** 版本。此模型转换自用户指定的 rhasspy/piper-voices `zh_CN/xiao_ya/medium`。原始 ONNX 文件不能直接交给 `termux-tts-speak`。
2. 在系统文字转语音设置中试听新引擎，然后执行 `termux-tts-engines`，复制对应小雅引擎的 `name`。
3. 修改手机 `.env`（更新部署包不会覆盖它）：

```dotenv
TTS_PROVIDER=hybrid
TTS_ZH_ENGINE=填写实际安装的小雅引擎包名
TTS_RATE=1.0
TTS_VOICE=FunAudioLLM/CosyVoice2-0.5B:diana
```

引擎未配置时明确报错，不悄悄使用华为/讯飞引擎。若系统引擎自行静默失败，仍需在系统设置中检查。Python 程序不负责安装 APK，也不能确认引擎内部加载的模型，必须选择正确的小雅安装包。

分开试听（不会修改保存的对话语言）：

```bash
python voice_sprite.py --tts-test --tts-language zh
python voice_sprite.py --tts-test --tts-language en
python voice_sprite.py --auto
```

中文合成本地执行，英文合成联网计费；语音识别和大模型回答仍走云端。`/slow` 调整当前语言对应的后端语速。小雅在目标手机上的速度、离线可用性和实际音色尚需实测。

## 本地 TTS 超时

`.env` 可设置 `TTS_TIMEOUT=30`，范围 5～600 秒，默认 180 秒。
它限制本地 Android TTS 整次调用（包括合成和朗读），适用于 android 模式和 hybrid 中文模式。
设置过短可能让正常长回答也超时。此项不修改云端 HTTP_TIMEOUT 或媒体播放超时。
修改后重启 voice-sprite。超时只结束命令等待，不保证 Android 引擎服务已停止；卡住后可在系统应用设置中强行停止小雅引擎和 Termux:API，再试听。

直接在终端执行 `termux-tts-speak` 不读取项目 `.env`。临时短句测试可运行：

```bash
timeout 20s termux-tts-speak -e com.k2fsa.sherpa.onnx.tts.engine -s MUSIC -l zh -n CN "你好。"
```

该命令约 20 秒后终止等待，并不修复引擎。若当前命令卡住，先按 Ctrl+C。
