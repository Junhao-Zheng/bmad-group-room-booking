"""Generate disclosed synthetic narration from reviewed scene data; never stretch recorded video."""
import argparse,hashlib,json,subprocess,wave
from pathlib import Path
import imageio_ffmpeg

def run(args):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 if p.returncode:raise RuntimeError(p.stderr[-2000:])
 return p

def main():
 p=argparse.ArgumentParser();p.add_argument('scenes',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 data=json.loads(a.scenes.read_text());assert len(data['scenes'])==12
 a.output.mkdir(parents=True,exist_ok=True);parts=[]
 for i,s in enumerate(data['scenes']):
  text=s['narration'];assert text.strip() and '{{' not in text,'Resolve final facts before narration'
  source=a.output/f'narration-{i+1:02}.txt';source.write_text(text)
  audio=a.output/f'narration-{i+1:02}.wav'
  run(['/usr/bin/say','-v','Tingting','-r','190','--file-format=WAVE','--data-format=LEI16@24000','-f',str(source),'-o',str(audio)])
  with wave.open(str(audio)) as w:duration=w.getnframes()/w.getframerate()
  assert 0<duration<=47,(i+1,duration,'Edit narration to fit, do not speed or stretch evidence')
  parts.append({'scene':i+1,'seconds':duration,'text_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'audio_sha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'path':str(audio)})
 ff=imageio_ffmpeg.get_ffmpeg_exe();cmd=[ff,'-y','-hide_banner']
 for item in parts:cmd+=['-i',item['path']]
 filters=[f'[{i}:a]adelay={i*50000}:all=1[a{i}]' for i in range(12)]
 filters.append(''.join(f'[a{i}]' for i in range(12))+'amix=inputs=12:normalize=0,apad,atrim=duration=600[out]')
 cmd+=['-filter_complex',';'.join(filters),'-map','[out]','-ar','24000','-c:a','pcm_s16le',str(a.output/'narration-600s.wav')]
 run(cmd)
 with wave.open(str(a.output/'narration-600s.wav')) as w:assert w.getnframes()/w.getframerate()==600
 report={'synthetic_narration':True,'voice':'macOS Tingting','rate':190,'total_seconds':600,'parts':parts,'ffmpeg':run([ff,'-version']).stdout.splitlines()[0]}
 (a.output/'narration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'result':'PASS','scenes':12,'seconds':600,'synthetic_narration':True}))
if __name__=='__main__':main()
