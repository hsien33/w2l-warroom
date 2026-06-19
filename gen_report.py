# -*- coding: utf-8 -*-
# 每日晨間戰情報告：讀 data.json(+抓即時追蹤數) → 產漂亮 HTML(report.html) → LINE 推 Jeff(摘要+連結)
# 跑在 GitHub Actions 每早 5:00 台北；報告掛在 GitHub Pages。
import os, sys, json, html, datetime, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
def env(k,d=""): return os.environ.get(k,d).strip()
TOK=env("IG_ACCESS_TOKEN"); VER=env("GRAPH_API_VERSION","v22.0")
LINE_TOKEN=env("LINE_CHANNEL_ACCESS_TOKEN"); LINE_USER=env("LINE_USER_ID")
HERE=os.path.dirname(os.path.abspath(__file__))
URL="https://hsien33.github.io/w2l-warroom/report.html"
ROOM="https://hsien33.github.io/w2l-warroom/"

now=datetime.datetime.utcnow()+datetime.timedelta(hours=8)
d=json.load(open(os.path.join(HERE,"data.json"),encoding="utf-8"))
# 抓即時追蹤數（順手更新 data.json 也好）
try:
    fc=json.load(urllib.request.urlopen(f"https://graph.instagram.com/{VER}/me?fields=followers_count&access_token={TOK}",timeout=30))["followers_count"]
    d["followers"]=int(fc)
except Exception as e: print("追蹤數抓取失敗，用 data.json 舊值",e)
followers=d.get("followers","?"); goal=d.get("goal",1000)
day=(now.date()-datetime.date(2026,6,10)).days; dday=(datetime.date(2026,7,10)-now.date()).days
inv=d.get("inventory",[]); ep=d.get("episodes",{}); dec=d.get("decisions",[]); sess=d.get("sessions",[])

esc=html.escape
WK="一二三四五六日"[(now.weekday())]
def chip(t,c="#c9a44c"): return f'<span style="display:inline-block;background:{c}1a;color:{c};border:1px solid {c}55;border-radius:8px;padding:3px 10px;font-size:13px;margin:2px 4px 2px 0">{esc(t)}</span>'

# 庫存表
invrows="".join(f"<tr><td><b>{esc(i.get('name',''))}</b></td><td>{esc(str(i.get('stock','')))}</td><td>{esc(str(i.get('through','')))}</td><td>{esc(i.get('auto',''))}</td></tr>" for i in inv)
# 主集 Reel 集卡
ready=ep.get("ready","?"); half=ep.get("half","?"); blocked=ep.get("blocked","?")
eplist=ep.get("list",[])
def epcolor(s): return {"ready":"#239b73","half":"#cf8c24","blocked":"#db543b"}.get(s,"#888")
def eplabel(s): return {"ready":"可寫","half":"半成品","blocked":"卡·待補真話"}.get(s,s)
eprows="".join(f"<tr><td>Day{e.get('day','')}·{esc(e.get('date',''))}</td><td>{esc(e.get('name',''))}</td><td style='color:{epcolor(e.get('status'))};font-weight:700'>{eplabel(e.get('status'))}</td><td style='font-size:13px;color:#7a7258'>{esc(e.get('gap',''))}</td></tr>" for e in eplist)
# 待裁決
def pcolor(p): return {"P0":"#db543b","P1":"#cf8c24","P2":"#888"}.get(p,"#888")
decitems="".join(f"<li><span style='color:{pcolor(x.get('p'))};font-weight:800'>[{esc(x.get('p',''))}]</span> {esc(x.get('t',''))}</li>" for x in dec)
ndec=len(dec); nP0=sum(1 for x in dec if x.get('p')=='P0')

body=f"""
<h1>☀️ 早安 Jeff · 今日戰情</h1>
<p style="color:#857c69;margin-top:-.4em">{now.strftime('%Y-%m-%d')}（週{WK}）· 報告於 {now.strftime('%H:%M')} 自動產出</p>
<div style="display:flex;gap:12px;flex-wrap:wrap;margin:18px 0">
  <div style="flex:1;min-width:120px;background:#fffdf8;border:1px solid #e7dfd0;border-radius:14px;padding:14px 16px">
    <div style="font-size:13px;color:#857c69">IG 追蹤</div><div style="font-size:30px;font-weight:800;color:#615ae0">{followers}<span style="font-size:15px;color:#a89e88"> / {goal}</span></div></div>
  <div style="flex:1;min-width:120px;background:#fffdf8;border:1px solid #e7dfd0;border-radius:14px;padding:14px 16px">
    <div style="font-size:13px;color:#857c69">距終局 7/10</div><div style="font-size:30px;font-weight:800;color:#2b2720">D-{dday}</div></div>
  <div style="flex:1;min-width:120px;background:#fffdf8;border:1px solid #e7dfd0;border-radius:14px;padding:14px 16px">
    <div style="font-size:13px;color:#857c69">今天</div><div style="font-size:30px;font-weight:800;color:#2b2720">Day {day}</div></div>
</div>

<h2>今日自動排程</h2>
<p>{chip('08:00 戰況卡 第'+str(day)+'天 自動發','#239b73')}{chip('20:30 主集 Reel · Day'+str(day),'#615ae0' if (day in [e.get('day') for e in eplist] or True) else '#db543b')}{chip('戰情室每 30 分刷新','#3289cf')}</p>

<h2>各產線庫存</h2>
<table><thead><tr><th>產線</th><th>庫存</th><th>預排到</th><th>自動發</th></tr></thead><tbody>{invrows}</tbody></table>

<h2>主集 Reel · Day11–20 庫存（{ready} 可寫 · {half} 半成品 · {blocked} 待補真話）</h2>
<table><thead><tr><th>集</th><th>主題</th><th>狀態</th><th>缺什麼</th></tr></thead><tbody>{eprows}</tbody></table>

<h2>🔴 需你決定／補真話（{ndec} 件 · {nP0} 件 P0）</h2>
<ul>{decitems}</ul>

<hr>
<p>📊 完整戰情室（即時）：<a href="{ROOM}">{ROOM}</a></p>
"""

TPL="""<!doctype html><html lang="zh-Hant"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>財富煉金術 · 今日戰情 {date}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
 :root{{--gold:#c9a44c;--ink:#2b2720;--mid:#55503f;--line:#e7dfd0}}
 *{{box-sizing:border-box}} body{{margin:0;background:#f3eee3;color:var(--ink);font-family:"Noto Sans TC",sans-serif;line-height:1.7;font-size:16px}}
 .wrap{{max-width:840px;margin:0 auto;padding:30px 18px 70px}}
 .card{{background:#fffdf8;border:1px solid var(--line);border-radius:18px;padding:30px clamp(16px,4vw,40px);box-shadow:0 2px 6px rgba(60,50,30,.05),0 24px 60px -32px rgba(70,55,30,.3)}}
 h1{{font-weight:900;font-size:25px;margin:.1em 0 .3em}}
 h2{{font-weight:900;font-size:19px;margin:1.5em 0 .5em;border-left:5px solid var(--gold);padding-left:12px}}
 a{{color:#b07d1a}} table{{border-collapse:collapse;width:100%;margin:.6em 0;font-size:14.5px;display:block;overflow-x:auto}}
 th,td{{border:1px solid var(--line);padding:8px 11px;text-align:left;vertical-align:top}}
 th{{background:#efe7d6;font-weight:700;white-space:nowrap}} tr:nth-child(even) td{{background:#fbf7ee}}
 ul{{padding-left:1.3em}} li{{margin:.3em 0;color:var(--mid)}} hr{{border:none;border-top:1px solid var(--line);margin:1.6em 0}}
 .foot{{text-align:center;color:#a89e88;font-size:12px;margin-top:20px}}
</style></head><body><div class="wrap"><div class="card">{body}</div>
<div class="foot">財富煉金術 AI 大腦 · 每日 05:00 自動產出</div></div></body></html>"""

out=TPL.format(date=now.strftime('%m/%d'), body=body)
open(os.path.join(HERE,"report.html"),"w",encoding="utf-8").write(out)
json.dump(d,open(os.path.join(HERE,"data.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
print("report.html 產出 ·", now.strftime('%Y-%m-%d %H:%M'))

# LINE 推送（摘要＋連結）
summary=(f"☀️ 早安 Jeff！今日戰情 {now.strftime('%m/%d')}（週{WK}）\n"
         f"━━━━━━━━━━\n"
         f"📊 追蹤 {followers}/{goal} · D-{dday} · 今天 Day{day}\n"
         f"⚔️ 戰況卡 08:00｜🎬 主集 Reel 20:30 自動發\n"
         f"🔴 需你決定/補真話：{ndec} 件（{nP0} 件最急）\n"
         f"━━━━━━━━━━\n"
         f"📖 完整報告 👉 {URL}\n"
         f"📊 即時戰情室 👉 {ROOM}")
if LINE_TOKEN and LINE_USER:
    try:
        req=urllib.request.Request("https://api.line.me/v2/bot/message/push",
          data=json.dumps({"to":LINE_USER,"messages":[{"type":"text","text":summary}]}).encode(),
          headers={"Content-Type":"application/json","Authorization":f"Bearer {LINE_TOKEN}"},method="POST")
        urllib.request.urlopen(req,timeout=30); print("LINE 已推送")
    except Exception as e: print("LINE 推送失敗",e)
else: print("(無 LINE 設定，略過推送)")
