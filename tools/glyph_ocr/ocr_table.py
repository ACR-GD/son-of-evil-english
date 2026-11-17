import json,re,subprocess,collections
from PIL import Image
a=open('soe.bin','rb').read()
N=2200; FB=0x197336
def glyph(i):
    bits=int.from_bytes(a[FB+i*18:FB+i*18+18],'big')
    return [[(bits>>(143-(y*12+x)))&1 for x in range(12)] for y in range(12)]
G=[glyph(i) for i in range(N)]
def draw(pix,gx,gy,i,s,t):
    for y in range(12):
        for x in range(12):
            if G[i][y][x]:
                for dy in range(s+t):
                    for dx in range(s+t): pix[gx+x*s+dx,gy+y*s+dy]=0
import os
OCR=os.environ.get('OCR_VISION', 'ocr_vision')  # macOS Vision OCR helper binary
def run(pre,suf,s,t,tag):
    res={}; rh=20*s; batch=10; paths=[];meta=[]
    for st in range(96,N,batch):
        ids=list(range(st,min(N,st+batch)))
        seq_len=len(pre)+1+len(suf)
        W=(seq_len+2)*14*s; H=(len(ids)+2)*rh
        im=Image.new('L',(W,H),255); pix=im.load()
        for k,g in enumerate(ids):
            for c,cid in enumerate(pre+[g]+suf): draw(pix,(c+1)*14*s,(k+1)*rh,cid,s,t)
        p=f'ocr/{tag}_{st}.png'; im.save(p); paths.append(p); meta.append((p,ids,H,rh))
    out=subprocess.check_output([OCR]+paths).decode()
    byf=collections.defaultdict(list)
    for line in out.splitlines():
        d=json.loads(line); byf[d['file']].append(d)
    for p,ids,H,rh in meta:
        for d in byf[p]:
            yc=1.0-(d['y']+d['h']/2); r=round((yc*H-6*s)/rh)-1
            if 0<=r<len(ids):
                for c in d['cands']:
                    m=re.search(r'[「『\[](.)[」』\]]',c['text'])
                    if m: res.setdefault(ids[r],[]).append(m.group(1)); break
    return res
r1=run([12],[13],4,1,'a'); print(len(r1))
r2=run([12],[13],3,0,'b'); print(len(r2))
json.dump({'r1':r1,'r2':r2},open('votes_carrier.json','w'),ensure_ascii=False)
tab={}
for i in range(96,N):
    v=r1.get(i,[])+r2.get(i,[])
    tab[i]=collections.Counter(v).most_common(1)[0][0] if v else None
json.dump(tab,open('glyphs_ocr.json','w'),ensure_ascii=False)
print('found',sum(1 for v in tab.values() if v),'of',N-96, 'agree',sum(1 for i in tab if r1.get(i) and r2.get(i) and r1[i][0]==r2[i][0]))
