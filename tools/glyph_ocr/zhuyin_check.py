import json,bisect
from pypinyin import pinyin,Style
C=json.load(open('combined.json')); final={int(k):v for k,v in C['final'].items()}
TONE={'˙':1,'ˊ':2,'ˇ':3,'ˋ':4}
def keys(ch):
    if not ch or len(ch)!=1: return []
    out=[]
    for r in pinyin(ch,style=Style.BOPOMOFO,heteronym=True)[0]:
        t=0;body=r
        if r and r[-1] in TONE: t=TONE[r[-1]]; body=r[:-1]
        if r and r[0]=='˙': t=1; body=r[1:]
        if not body or not all(0x3105<=ord(c)<=0x3129 for c in body): continue
        out.append((tuple(ord(c) for c in body),t))
    return out
ids=sorted(i for i in final if i>=97)
K={i:keys(final[i]) for i in ids}
# LIS over choices: greedy DP picking reading. Simple approach: DP O(n*k^2) over index with best chain length ending at each (i,reading)
best={}  # (i,ri)->(len,prev)
chain_tail=[]  # patience sorting not trivial with options; do O(n^2) limited window
import itertools
nodes=[(i,k) for i in ids for k in K[i]]
L={};P={}
for n,(i,k) in enumerate(nodes):
    L[n]=1;P[n]=None
    lo=max(0,n-400)
    for m in range(lo,n):
        j,kk=nodes[m]
        if j<i and kk<=k and L[m]+1>L[n]: L[n]=L[m]+1;P[n]=m
end=max(L,key=L.get); good={}
while end is not None: good[nodes[end][0]]=nodes[end][1]; end=P[end]
bad=[i for i in ids if i not in good]
print('in order',len(good),'out of order / unknown',len(bad))
json.dump({'good':sorted(good),'bad':bad},open('zhuyin.json','w'))
