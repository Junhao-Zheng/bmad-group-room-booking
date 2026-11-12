# 演示复现工具

这些工具读取最终审核后的场景JSON，运行隔离合成数据库；不读取用户浏览器、默认演示库或真实凭证。`record.py --preflight`快速核对实际动作，不录视频，也不算10分钟录屏。默认模式连续实际运行至少600秒，产生时间记录、12张截图和WebM，不能把快速预检拉长作为正式视频。

示例命令中的最终场景文件在交付录制时生成。主项目虚拟环境运行Python工具；Node须能解析Playwright 1.58.2（例如将NODE_PATH指向独立工具安装目录）。record.py默认使用项目内work/browser-tools/node_modules，并接受已安装浏览器的--browser-executable路径。

`render.py 场景.json 过程页面.html`生成本地演示页。`record.py --scenes 场景.json --viewer 过程页面.html --output 新输出目录 --browser-executable 浏览器路径 [--preflight]`运行。场景source_commit必须等于开始时Git HEAD，脚本再次核对应用源码未在录制中改变。

`narration.py 场景.json 新音频目录`需要macOS系统Tingting语音与imageio-ffmpeg 0.8.1（本次附带FFmpeg 9.0）；合成语音明确披露。`subtitles.py 场景.json 音频目录/narration.json 字幕.srt`按字数近似对齐，不能宣称人工听写。最终视频合成/解码/元数据核验命令由交付说明记录。应用本身不依赖这些录制工具。
