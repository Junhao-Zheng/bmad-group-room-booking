# 演示复现工具

这些工具读取最终审核后的场景JSON，运行隔离合成数据库；不读取用户浏览器、默认演示库或真实凭证。`record.py --preflight`快速核对实际动作，不录视频，也不算10分钟录屏。默认模式连续实际运行至少600秒，产生时间记录、12张截图和WebM，不能把快速预检拉长作为正式视频。

示例命令中的最终场景文件在交付录制时生成。主项目虚拟环境运行Python工具；Node须能解析Playwright 1.58.2（例如将NODE_PATH指向独立工具安装目录）。record.py默认使用项目内work/browser-tools/node_modules，并接受已安装浏览器的--browser-executable路径。

`render.py 场景.json 过程页面.html`生成本地演示页。`record.py --scenes 场景.json --viewer 过程页面.html --output 新输出目录 --browser-executable 浏览器路径 [--preflight]`运行。场景source_commit必须等于开始时Git HEAD，脚本再次核对应用源码未在录制中改变。

`narration.py 场景.json 新音频目录`需要macOS系统Tingting语音与imageio-ffmpeg 0.8.1（本次附带FFmpeg 9.0）；合成语音明确披露。`subtitles.py 场景.json 音频目录/narration.json 字幕.srt`按字数近似对齐，不能宣称人工听写。最终视频合成/解码/元数据核验命令由交付说明记录。应用本身不依赖这些录制工具。

正式录制可传`--ffmpeg-executable /实际/ffmpeg路径`。脚本只在独立临时缓存中提供指定编码器，保存其版本/SHA；不修改全局浏览器安装或系统安全设置。本次Playwright下载的FFmpeg未能成功启动（退出137），采用已实际运行通过的imageio-ffmpeg 0.8.1自带FFmpeg 9.0。实际录制与最终解码还须独立通过，预检不证明录像编码器工作。

当前Chrome 157的原生录像与模拟viewport曾出现底部裁切；录制脚本使用原生内容区域，按实测窗口边框尺寸调整至1280×800，再断言页面实际innerWidth/innerHeight并保存几何信息。编码器预检的实际解码帧已确认底部完整，最终视频仍逐章抽帧检查。

`finalize.py --recording 正式录制目录 --narration 旁白.wav --subtitles 字幕.srt --output 新视频.mp4 --evidence 新验证目录`只接受至少600秒的正式录屏PASS记录，输出600秒H.264/AAC字幕视频，做完整解码并抽取12帧。运行它需要imageio-ffmpeg 0.8.1；抽帧之后仍须逐帧人工视觉检查并更新验证记录，不能把脚本PASS当作已经完成视觉检查。
