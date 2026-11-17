import json
from PIL import Image,ImageDraw,ImageFont
from pypinyin import pinyin,Style
a=open('soe.bin','rb').read(); FB=0x197336
C=json.load(open('combined.json')); final={int(k):v for k,v in C['final'].items()}
Z=json.load(open('zhuyin.json')); good=set(Z['good'])
flag={f[0] for f in C['flag']}
rev=sorted(set(Z['bad'])|{i for i in flag if i not in good and i>=97})
json.dump(rev,open('review_ids.json','w'))
print(len(rev))
font=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',18)
small=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',13)
def zy(ch):
    try: return pinyin(ch,style=Style.BOPOMOFO)[0][0]
    except: return '?'
def near(i,d):
    j=i+d
    while j in final and j not in good: j+=d
    return final.get(j) or '?'
per=40
for s in range(0,len(rev),per):
    ids=rev[s:s+per]
    im=Image.new('RGB',(8*150,5*90),'white'); dr=ImageDraw.Draw(im)
    for k,i in enumerate(ids):
        x0=(k%8)*150; y0=(k//8)*90
        bits=int.from_bytes(a[FB+i*18:FB+i*18+18],'big')
        for y in range(12):
            for x in range(12):
                if (bits>>(143-(y*12+x)))&1: dr.rectangle([x0+4+x*5,y0+18+y*5,x0+8+x*5,y0+22+y*5],fill='black')
        dr.text((x0+4,y0+2),str(i),fill='blue',font=small)
        g=final.get(i) or '∅'
        dr.text((x0+70,y0+20),g,fill='red',font=font)
        p,n=near(i,-1),near(i,1)
        dr.text((x0+70,y0+45),f'{p}{zy(p)}',fill='green',font=small)
        dr.text((x0+70,y0+62),f'{n}{zy(n)}',fill='green',font=small)
    im.save(f'ocr/review_{s//per}.png')
