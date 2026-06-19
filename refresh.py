# -*- coding: utf-8 -*-
# 更新 data.json 的「即時追蹤數＋D-day＋更新時間」（庫存 inventory 由人工維護、保留不動）
# 跑在 GitHub Actions：抓 IG Graph API followers_count → 寫回 data.json → 由 workflow commit
import os, sys, json, datetime, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
TOK=os.environ.get("IG_ACCESS_TOKEN","").strip()
VER=os.environ.get("GRAPH_API_VERSION","v22.0")
HERE=os.path.dirname(os.path.abspath(__file__))
P=os.path.join(HERE,"data.json")
d=json.load(open(P,encoding="utf-8"))
now=datetime.datetime.utcnow()+datetime.timedelta(hours=8)
try:
    u=f"https://graph.instagram.com/{VER}/me?fields=followers_count&access_token={TOK}"
    fc=json.load(urllib.request.urlopen(u,timeout=30))["followers_count"]
    d["followers"]=int(fc); print("followers =",fc)
except Exception as e:
    print("抓追蹤數失敗（保留舊值）:",e)
d["updated"]=now.strftime("%Y-%m-%d %H:%M 台北")
d["dday"]=(datetime.date(2026,7,10)-now.date()).days
d["day"]=(now.date()-datetime.date(2026,6,10)).days   # 主集集數＝戰況卡第N天（今天−6/10）
json.dump(d,open(P,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
print("data.json 已更新 · D-",d["dday"])
