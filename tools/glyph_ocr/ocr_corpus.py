import json,subprocess,collections
from PIL import Image
a=open('soe.bin','rb').read()
FB=0x197336
def glyph(i):
    bits=int.from_bytes(a[FB+i*18:FB+i*18+18],'big')
    return [[(bits>>(143-(y*12+x)))&1 for x in range(12)] for y in range(12)]
GC={}
def G(i):
    if i not in GC: GC[i]=glyph(i)
    return GC[i]
m=json.load(open('msgs.json'))
runs=set()
for x in m:
    for l in x['lines']:
        cur=[]
        for tp,v in l+[('B',0)]:
            i=127*((v>>8)-0x80)+((v&0xff)-0x80) if tp=='W' else -1
            if tp=='W' and i>=96 and i<2200: cur.append(i)
            else:
                if len(cur)>=3: runs.add(tuple(cur))
                cur=[]
runs=sorted(runs); print(len(runs),'runs')
import os
OCR=os.environ.get('OCR_VISION', 'ocr_vision')  # macOS Vision OCR helper binary
s=3; rh=20*s; per=10
votes=collections.defaultdict(collections.Counter)
paths=[];meta=[]
for b in range(0,len(runs),per):
    rs=runs[b:b+per]; W=(max(len(r) for r in rs)+2)*14*s; H=(len(rs)+2)*rh
    im=Image.new('L',(W,H),255); pix=im.load()
    for k,r in enumerate(rs):
        for c,g in enumerate(r):
            gl=G(g)
            for y in range(12):
                for xx in range(12):
                    if gl[y][xx]:
                        for dy in range(s):
                            for dx in range(s): pix[(c+1)*14*s+xx*s+dx,(k+1)*rh+y*s+dy]=0
    p=f'ocr/c_{b}.png'; im.save(p); paths.append(p); meta.append((p,rs,H))
byf=collections.defaultdict(list)
for i in range(0,len(paths),200):
    out=subprocess.check_output([OCR]+paths[i:i+200]).decode()
    for line in out.splitlines():
        d=json.loads(line); byf[d['file']].append(d)
ok=0
for p,rs,H in meta:
    for d in byf[p]:
        yc=1.0-(d['y']+d['h']/2); r=round((yc*H-6*s)/rh)-1
        if not 0<=r<len(rs): continue
        txt=d['cands'][0]['text'].replace(' ','')
        if len(txt)==len(rs[r]):
            ok+=1
            for g,ch in zip(rs[r],txt): votes[g][ch]+=1
print('aligned rows',ok)
json.dump({g:dict(c) for g,c in votes.items()},open('votes_corpus.json','w'),ensure_ascii=False)
