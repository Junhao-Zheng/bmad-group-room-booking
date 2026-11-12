"""Approximate readable subtitles for the disclosed synthetic narration, not a speech transcript claim."""
import argparse,json,re
from pathlib import Path

def stamp(t):
 ms=round(t*1000);hours,ms=divmod(ms,3600000);minutes,ms=divmod(ms,60000);seconds,ms=divmod(ms,1000)
 return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'

def main():
 p=argparse.ArgumentParser();p.add_argument('scenes',type=Path);p.add_argument('narration',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 scenes=json.loads(a.scenes.read_text())['scenes'];audio=json.loads(a.narration.read_text())['parts'];assert len(scenes)==len(audio)==12
 cues=[]
 for i,(scene,part) in enumerate(zip(scenes,audio)):
  pieces=re.findall(r'[^。！？；，]+[。！？；，]?',scene['narration'])
  chunks=[]
  for piece in pieces:
   while len(piece)>34:chunks.append(piece[:34]);piece=piece[34:]
   if piece:chunks.append(piece)
  total=sum(len(s) for s in chunks);elapsed=0;duration=part['seconds']
  for text in chunks:
   start=50*i+duration*elapsed/total;elapsed+=len(text);end=50*i+duration*elapsed/total
   cues.append(f'{len(cues)+1}\n{stamp(start)} --> {stamp(end)}\n{text}\n')
 a.output.write_text('\n'.join(cues),encoding='utf-8');print(len(cues),'cues; synthetic narration with approximate timing')
if __name__=='__main__':main()
