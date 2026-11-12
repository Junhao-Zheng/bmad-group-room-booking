"""Mux a genuine >=600s browser recording, disclosed narration and optional captions; verify decode."""
import argparse,hashlib,json,re,subprocess
from datetime import datetime,timezone
from pathlib import Path
import imageio_ffmpeg
p=argparse.ArgumentParser();p.add_argument('--recording',type=Path,required=True);p.add_argument('--narration',type=Path,required=True);p.add_argument('--subtitles',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);a=p.parse_args()
meta=json.loads((a.recording/'recording.json').read_text());runner=json.loads((a.recording/'runner.json').read_text())
assert meta['result']==runner['result']=='PASS' and meta['mode']=='recording' and meta['actual_recording_seconds']>=600
assert not a.output.exists() and not a.evidence.exists(), 'Do not overwrite recorded outputs'
a.evidence.mkdir(parents=True);a.output.parent.mkdir(parents=True,exist_ok=True);ff=imageio_ffmpeg.get_ffmpeg_exe()
def run(name,cmd):
 result=subprocess.run(cmd,capture_output=True,text=True)
 (a.evidence/(name+'.stdout.txt')).write_text(result.stdout);(a.evidence/(name+'.stderr.txt')).write_text(result.stderr)
 assert result.returncode==0,(name,result.returncode)
 return result
video=a.recording/'actual-browser.webm'
assert hashlib.sha256(video.read_bytes()).hexdigest()==runner['video_sha256']
cmd=[ff,'-hide_banner','-i',str(video),'-i',str(a.narration),'-i',str(a.subtitles),'-map','0:v:0','-map','1:a:0','-map','2:s:0','-c:v','libx264','-preset','medium','-crf','26','-pix_fmt','yuv420p','-r','25','-c:a','aac','-b:a','96k','-c:s','mov_text','-metadata:s:s:0','language=zho','-metadata','comment=AI automated demonstration; synthetic narration and data; actual browser recording','-t','600','-movflags','+faststart',str(a.output)]
run('encode',cmd)
decode=run('full-decode',[ff,'-hide_banner','-i',str(a.output),'-map','0:v:0','-map','0:a:0','-f','null','-'])
info=decode.stderr
assert re.search(r'Duration: 00:10:00\.0\d',info), 'Expected actual 600s MP4'
assert '1280x800' in info and 'Video: h264' in info and 'Audio: aac' in info and 'Subtitle: mov_text' in info
assert a.output.stat().st_size<100_000_000
for i in range(12):
 run(f'frame-{i+1:02}',[ff,'-hide_banner','-ss',str(i*50+35),'-i',str(a.output),'-frames:v','1',str(a.evidence/f'frame-{i+1:02}.png')])
report={'result':'PASS','verified_at_utc':datetime.now(timezone.utc).isoformat(),'actual_recording_seconds':meta['actual_recording_seconds'],'final_duration_seconds':600,'source_commit':meta['source_commit'],'resolution':[1280,800],'video_codec':'h264','audio_codec':'aac','caption_codec':'mov_text','full_decode_exit':0,'bytes':a.output.stat().st_size,'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'imageio_ffmpeg_version':imageio_ffmpeg.__version__,'ffmpeg_version':subprocess.check_output([ff,'-version'],text=True).splitlines()[0],'encode_command':cmd,'visual_qa':'PENDING: inspect all twelve extracted frames before delivery','narration':'macOS Tingting synthetic voice; captions approximately aligned by character length','input_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [video,a.narration,a.subtitles]}}
(a.evidence/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['encode_command','input_hashes']},ensure_ascii=False,indent=2))
