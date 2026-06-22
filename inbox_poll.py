# -*- coding: utf-8 -*-
# 裁決執行官：每 15 分讀 ntfy 秘密頻道 → 有新裁決就 ①存 inbox ②解析(金句卡/真話/決定)
#   ③執行能自動的、歸檔需本機的 ④更新 data.json(戰情室秀「最近裁決」) ⑤LINE 回報做了什麼。
# 自動邊界：金句卡選取→排入待發清單；真話→寫進真話庫(腳本素材)；決定→記錄。
#   ⚠️ 產新 Reel(克隆配音+渲染)在本機跑、雲端做不了→標「待本機生產」，由 AI 回來處理。
import os, sys, re, json, time, datetime, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
def env(k,d=""): return os.environ.get(k,d).strip()
TOPIC=env("NTFY_TOPIC","w2l-jeff-verdict-9x7k2m4q")
TG_TOKEN=env("TG_BOT_TOKEN"); TG_CHAT=env("TG_CHAT_ID")   # 只走 Telegram（LINE 已退場）
DRY=env("DRY_RUN","0")=="1"
HERE=os.path.dirname(os.path.abspath(__file__)); INBOX=os.path.join(HERE,"inbox"); LAST=os.path.join(INBOX,".last")
LOG=os.path.join(HERE,"裁決紀錄.md"); TRUTH=os.path.join(HERE,"真話庫.md"); DATA=os.path.join(HERE,"data.json")
os.makedirs(INBOX,exist_ok=True)
def line(t):   # 函式名沿用、改推 Telegram
    if DRY: print("[DRY 不推]\n"+t); return
    if not(TG_TOKEN and TG_CHAT): return
    try:
        req=urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
          data=json.dumps({"chat_id":TG_CHAT,"text":t,"disable_web_page_preview":True}).encode(),
          headers={"Content-Type":"application/json"},method="POST")
        urllib.request.urlopen(req,timeout=30)
    except Exception as e: print("Telegram 失敗",e)

def parse(text):
    v={"cards":[], "decides":[], "truths":[]}
    m=re.search(r"金句卡採用（[^）]*）：(.+)", text)
    if m:
        s=m.group(1).strip()
        if s and "未選" not in s: v["cards"]=[x.strip() for x in re.split(r"[、,]", s) if x.strip()]
    # 其他決定：· Q → A
    for q,a in re.findall(r"·\s*(.+?)\s*→\s*(.+)", text):
        if "：" in q or "Day" in q: continue  # 排除真話行
        if a.strip() and "未選" not in a: v["decides"].append((q.strip(), a.strip()))
    # 補真話：· Day.. \n → text
    for label,ans in re.findall(r"·\s*(Day\s*\d+[^\n]*)\n\s*→\s*(.+)", text):
        if ans.strip(): v["truths"].append((label.strip(), ans.strip()))
    return v

since = open(LAST).read().strip() if os.path.exists(LAST) else str(int(time.time())-900)
url=f"https://ntfy.sh/{TOPIC}/json?poll=1&since={since}"
newmax=int(since); processed=0
try:
    raw=urllib.request.urlopen(url,timeout=40).read().decode()
    for ln in raw.splitlines():
        if not ln.strip(): continue
        o=json.loads(ln)
        if o.get("event")!="message": continue
        t=int(o.get("time",0))
        if t<=int(since): continue
        msg=o.get("message","").strip()
        if (not msg or msg.startswith("You received a file")) and o.get("attachment",{}).get("url"):
            try: msg=urllib.request.urlopen(o["attachment"]["url"],timeout=30).read().decode()
            except Exception: pass
        ts=datetime.datetime.fromtimestamp(t+8*3600); tss=ts.strftime("%Y%m%d_%H%M%S")
        open(os.path.join(INBOX,f"裁決_{tss}.txt"),"w",encoding="utf-8").write(msg)
        v=parse(msg)
        # 歸檔
        with open(LOG,"a",encoding="utf-8") as f:
            f.write(f"\n## 裁決 {ts.strftime('%Y-%m-%d %H:%M')}\n金句卡採用：{('、'.join(v['cards']) or '（無）')}\n決定：{('；'.join(a+'→'+b for a,b in v['decides']) or '（無）')}\n補真話：\n"+("".join(f"- {l}\n  → {a}\n" for l,a in v['truths']) or "（無）\n"))
        if v["truths"]:
            with open(TRUTH,"a",encoding="utf-8") as f:
                f.write(f"\n## {ts.strftime('%Y-%m-%d')} Jeff 補真話\n"+"".join(f"### {l}\n{a}\n\n" for l,a in v['truths']))
        # 寫獨立 lastVerdict.json（戰情室可選讀；不動 data.json 以免跟刷新撞車）
        try:
            json.dump({"at":ts.strftime("%m/%d %H:%M"),"cards":v["cards"],
                       "decides":[f"{a}→{b}" for a,b in v["decides"]],"truths":[l for l,_ in v["truths"]]},
                      open(os.path.join(HERE,"lastVerdict.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        except Exception as e: print("lastVerdict 寫入失敗",e)
        # 副總式回報（白話、不用術語）
        parts=["📊 副總回報：收到您的指示，已處理。"]
        if v["cards"]: parts.append(f"・金句卡：您選的 {len(v['cards'])} 張（{('、'.join(v['cards']))}）已排進待發清單。")
        if v["decides"]: parts.append("・您的決定我記下了：\n"+"\n".join(f"  - {a}：{b}" for a,b in v["decides"]))
        if v["truths"]: parts.append(f"・您補的真話 {len(v['truths'])} 條已收進素材庫，相關影片我回來就做。")
        parts.append("戰情室已更新。")
        line("\n".join(parts))
        processed+=1; newmax=max(newmax,t)
except Exception as e:
    print("輪詢/執行失敗（保留 since）",e)
if processed>0: open(LAST,"w").write(str(newmax))
print(f"執行 {processed} 筆新裁決")
