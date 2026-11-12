"""Render supplied, verified presentation facts as a local recording surface.
No course outcomes are inferred here; final content must be supplied after audit.
"""
from pathlib import Path
import argparse,html,json

def render(data):
    assert len(data['scenes'])==12
    sections=[]
    for i,s in enumerate(data['scenes']):
        esc=lambda x:html.escape(str(x))
        facts=''.join(f'<li>{esc(x)}</li>' for x in s['facts'])
        sources=''.join(f'<div>{esc(x)}</div>' for x in s.get('sources',[]))
        sections.append(f'''<section id="scene-{i}" hidden><div class="eyebrow">软件工程管理 · 过程证据 / {i+1:02d}</div>
<h1>{esc(s['title'])}</h1><p class="lead">{esc(s['lead'])}</p><ul>{facts}</ul>
<aside><strong>证据入口</strong>{sources}</aside></section>''')
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BMAD课程项目 · 过程演示</title><style>
*{box-sizing:border-box}body{margin:0;background:#eef4f5;color:#173440;font:22px/1.5 system-ui,-apple-system,"PingFang SC",sans-serif}
main{height:800px;width:1280px;padding:58px 74px 68px;position:relative;overflow:hidden}
section{height:100%}.eyebrow{color:#17786e;font-size:19px;letter-spacing:2px}h1{font-size:48px;line-height:1.18;margin:22px 0}
.lead{font-size:25px;color:#486471;max-width:1080px;margin:0 0 28px}ul{padding-left:28px;margin:0;max-width:1100px}li{margin-bottom:14px}
aside{position:absolute;bottom:78px;left:74px;right:74px;border-top:1px solid #b8cdce;padding-top:15px;color:#42606b;font-size:17px}
aside strong{display:block;margin-bottom:5px;color:#176f67}footer{position:absolute;left:74px;right:74px;bottom:24px;display:flex;justify-content:space-between;font-size:16px;color:#506c77}
</style></head><body><main>'''+''.join(sections)+'''
<footer><span>AI 自动操作与合成解说 · 合成演示数据 · 不冒充人工验收</span><span id="position"></span></footer></main>
<script>function show(){const n=Math.min(11,Math.max(0,Number(location.hash.slice(1))||0));document.querySelectorAll('section').forEach((s,i)=>s.hidden=i!==n);document.querySelector('#position').textContent=`${n+1} / 12`;}addEventListener('hashchange',show);show();</script></body></html>'''

def main():
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.write_text(render(json.loads(a.input.read_text())),encoding='utf-8')
if __name__=='__main__':main()
