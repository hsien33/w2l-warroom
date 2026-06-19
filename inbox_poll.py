# -*- coding: utf-8 -*-
# 收件夾輪詢官：每 15 分讀 ntfy 秘密頻道 → 有新裁決就存進 inbox/ + LINE 跟 Jeff 確認收到
# 讓「手機送出的裁決」變持久（存 repo），AI 回來就讀得到 inbox/。
import os, sys, json, time, datetime, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
def env(k,d=""): return os.environ.get(k,d).strip()
TOPIC=env("NTFY_TOPIC","w2l-jeff-verdict-9x7k2m4q")
LINE_TOKEN=env("LINE_CHANNEL_ACCESS_TOKEN"); LINE_USER=env("LINE_USER_ID")
DRY=env("DRY_RUN","0")=="1"
HERE=os.path.dirname(os.path.abspath(__file__)); INBOX=os.path.join(HERE,"inbox"); LAST=os.path.join(INBOX,".last")
os.makedirs(INBOX,exist_ok=True)
def line(t):
    if DRY: print("[DRY 不推 LINE]",t[:60]); return
    if not(LINE_TOKEN and LINE_USER): return
    try:
        req=urllib.request.Request("https://api.line.me/v2/bot/message/push",
          data=json.dumps({"to":LINE_USER,"messages":[{"type":"text","text":t}]}).encode(),
          headers={"Content-Type":"application/json","Authorization":f"Bearer {LINE_TOKEN}"},method="POST")
        urllib.request.urlopen(req,timeout=30)
    except Exception as e: print("LINE 失敗",e)

since = open(LAST).read().strip() if os.path.exists(LAST) else str(int(time.time())-900)
url=f"https://ntfy.sh/{TOPIC}/json?poll=1&since={since}"
newmax=int(since); cnt=0
try:
    raw=urllib.request.urlopen(url,timeout=40).read().decode()
    for ln in raw.splitlines():
        if not ln.strip(): continue
        o=json.loads(ln)
        if o.get("event")!="message": continue
        t=int(o.get("time",0))
        if t<=int(since): continue
        msg=o.get("message","").strip()
        # ntfy 把過長內容轉附件時，去抓附件文字
        if (not msg or msg.startswith("You received a file")) and o.get("attachment",{}).get("url"):
            try: msg=urllib.request.urlopen(o["attachment"]["url"],timeout=30).read().decode()
            except Exception: pass
        ts=datetime.datetime.fromtimestamp(t+8*3600).strftime("%Y%m%d_%H%M%S")
        fn=os.path.join(INBOX,f"裁決_{ts}.txt")
        open(fn,"w",encoding="utf-8").write(msg)
        print("存入",fn); cnt+=1; newmax=max(newmax,t)
        line(f"✅ 收到你的裁決（{datetime.datetime.fromtimestamp(t+8*3600).strftime('%m/%d %H:%M')}）已存檔，AI 會開始處理 🚀")
except Exception as e:
    print("輪詢失敗（保留 since）",e)
if cnt>0: open(LAST,"w").write(str(newmax))
print(f"處理 {cnt} 筆新裁決")
