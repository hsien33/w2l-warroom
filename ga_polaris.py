# -*- coding: utf-8 -*-
# 北極星看板資料引擎：GA4 Data API(runReport) → polaris.json（戰情室「北極星看板」唯一數據來源）
# 跑在 GitHub Actions（ga-polaris.yml）。復用既有 secrets：GA4_SA_JSON / GA4_PROPERTY_ID / TG_BOT_TOKEN / TG_CHAT_ID。
# 設計原則：
#   1. 只用 GA4「標準維度」(date/hostName/eventName/sessionSource…) → 不依賴自訂維度註冊、零額外後台設定。
#      （拆站用 hostName：grow.walk2light.com vs www.walk2light.com，比未註冊的 site 自訂維度可靠且可回溯歷史＝優雅降級的實作。）
#   2. API 失敗絕不 crash：寫出 status:"error" 的 polaris.json ＋ Telegram 告警，看板顯示佔位卡。
#   3. 出國模式：名單斷流／網站掛 → 直接 Telegram 告警（Jeff 在挪威也看得到）。
#   4. console 輸出純 ASCII（Windows cp950 / CI 皆安全）。
import os, sys, json, datetime, traceback, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "polaris.json")

def env(k, d=""): return os.environ.get(k, d).strip()

GA_SA, GA_PROP = env("GA4_SA_JSON"), env("GA4_PROPERTY_ID")
TG_TOKEN, TG_CHAT = env("TG_BOT_TOKEN"), env("TG_CHAT_ID")
DRY = env("DRY_RUN") == "1"   # DRY_RUN=1 → 不發 Telegram（測試靜音鐵則）

now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)   # 台北時間（禁 TZ=Asia/Taipei，鐵則）
today = now.date()
ystr = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

SITES = {"grow.walk2light.com": "grow", "www.walk2light.com": "wealth", "walk2light.com": "wealth"}
KEY_EVENTS = ["email_signup", "cta_view", "magnet_delivered", "card_open", "outbound_placement",
              "tool_engaged", "tool_result", "purchase_intent", "cta_click", "result_share"]

def tg(text):
    if DRY or not TG_TOKEN:
        print("TG skipped (dry-run or no token)"); return
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=json.dumps({"chat_id": TG_CHAT, "text": text}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=20)
    except Exception as e:
        print("TG send failed:", type(e).__name__)

def write_json(obj):
    json.dump(obj, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ── GA4 認證＋runReport ─────────────────────────────────────────
def make_creds():
    from google.oauth2 import service_account
    import google.auth.transport.requests
    creds = service_account.Credentials.from_service_account_info(
        json.loads(GA_SA), scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds

def rows(rep):
    for r in rep.get("rows", []):
        yield ([d["value"] for d in r.get("dimensionValues", [])],
               [m["value"] for m in r.get("metricValues", [])])

def main():
    if not GA_SA or not GA_PROP:
        raise RuntimeError("missing env GA4_SA_JSON or GA4_PROPERTY_ID")
    creds = make_creds()

    def run_report(body):
        req = urllib.request.Request(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{GA_PROP}:runReport",
            data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())

    # ── Q1：近 30 天 每日×站 活躍/瀏覽 ───────────────────────────
    q1 = run_report({"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                     "dimensions": [{"name": "date"}, {"name": "hostName"}],
                     "metrics": [{"name": "activeUsers"}, {"name": "screenPageViews"}],
                     "limit": 100000})
    daily = {}   # date → site → {users, pv}
    for (dt, host), (au, pv) in rows(q1):
        site = SITES.get(host)
        if not site: continue
        d0 = daily.setdefault(f"{dt[:4]}-{dt[4:6]}-{dt[6:]}", {})
        s0 = d0.setdefault(site, {"users": 0, "pv": 0})
        s0["users"] += int(au); s0["pv"] += int(pv)

    # ── Q2：近 30 天 每日×站×事件 計數（只抓關鍵事件）────────────
    q2 = run_report({"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                     "dimensions": [{"name": "date"}, {"name": "hostName"}, {"name": "eventName"}],
                     "metrics": [{"name": "eventCount"}],
                     "dimensionFilter": {"filter": {"fieldName": "eventName",
                         "inListFilter": {"values": KEY_EVENTS}}},
                     "limit": 100000})
    ev = {}      # date → site → event → count
    for (dt, host, name), (cnt,) in rows(q2):
        site = SITES.get(host)
        if not site: continue
        key = f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"
        ev.setdefault(key, {}).setdefault(site, {})[name] = \
            ev.get(key, {}).get(site, {}).get(name, 0) + int(cnt)

    # ── Q3：UTM 排行（來源×媒介×活動 → 工作階段 + 名單）──────────
    q3 = run_report({"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                     "dimensions": [{"name": "sessionSource"}, {"name": "sessionMedium"},
                                    {"name": "sessionCampaignName"}],
                     "metrics": [{"name": "sessions"}, {"name": "activeUsers"}],
                     "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}], "limit": 12})
    q3b = run_report({"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                      "dimensions": [{"name": "sessionSource"}, {"name": "sessionMedium"},
                                     {"name": "sessionCampaignName"}],
                      "metrics": [{"name": "eventCount"}],
                      "dimensionFilter": {"filter": {"fieldName": "eventName",
                          "stringFilter": {"value": "email_signup"}}}, "limit": 100})
    signup_by_src = {tuple(dims): int(m[0]) for dims, m in rows(q3b)}
    utm = [{"source": d[0], "medium": d[1], "campaign": d[2],
            "sessions": int(m[0]), "users": int(m[1]),
            "signups": signup_by_src.get(tuple(d), 0)} for d, m in rows(q3)]

    # ── 彙總：昨日 / 7日 / 30日 ─────────────────────────────────
    def agg(days):
        lo = (today - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        out = {"users": 0, "pv": 0, "events": {}, "sites": {}}
        for dk in set(list(daily) + list(ev)):
            if not (lo <= dk < today.strftime("%Y-%m-%d")): continue   # 不含今天(不完整)
            for site in ("grow", "wealth"):
                s = out["sites"].setdefault(site, {"users": 0, "events": {}})
                dd = daily.get(dk, {}).get(site, {})
                s["users"] += dd.get("users", 0)
                out["users"] += dd.get("users", 0); out["pv"] += dd.get("pv", 0)
                for k, v in ev.get(dk, {}).get(site, {}).items():
                    s["events"][k] = s["events"].get(k, 0) + v
                    out["events"][k] = out["events"].get(k, 0) + v
        return out

    y1, d7, d30 = agg(1), agg(7), agg(30)

    # ── 漏斗四步（近7日）：到站 → 看到CTA → 訂閱 → 領到卡 ─────────
    def funnel(site):
        s7 = d7["sites"].get(site, {"users": 0, "events": {}})
        e = s7["events"]
        if site == "grow":
            steps = [("到站(活躍)", s7["users"]), ("看到CTA", e.get("cta_view", 0)),
                     ("Email訂閱", e.get("email_signup", 0)), ("領到對話卡", e.get("magnet_delivered", 0))]
        else:
            steps = [("到站(活躍)", s7["users"]), ("用了工具", e.get("tool_engaged", 0)),
                     ("Email訂閱", e.get("email_signup", 0)), ("購買意圖", e.get("purchase_intent", 0))]
        out = []
        for i, (label, n) in enumerate(steps):
            rate = round(n / steps[i-1][1] * 100, 1) if i and steps[i-1][1] else None
            out.append({"step": label, "count": n, "rate": rate})
        return out

    # ── 紅綠燈＋該做什麼 ───────────────────────────────────────
    def light(status, label, value, advice):
        return {"status": status, "label": label, "value": value, "advice": advice}

    lights = []
    sy = y1["events"].get("email_signup", 0)
    s7v = d7["events"].get("email_signup", 0)
    if sy > 0: lights.append(light("green", "昨日名單", f"+{sy}", "健康。維持現有導流即可。"))
    elif s7v > 0: lights.append(light("yellow", "昨日名單", "0", "昨天掛零但 7 日有進帳。看 UTM 排行：哪條導流斷了就補那條（IG bio／貼文首留）。"))
    else: lights.append(light("red", "昨日名單", "0", "7 天沒進任何名單＝漏斗斷了。先查兩站訂閱表單能不能送出，再查 IG 導流連結。"))

    rate7 = (s7v / d7["users"] * 100) if d7["users"] else 0
    if rate7 >= 2: lights.append(light("green", "7日訂閱率", f"{rate7:.1f}%", "高於 2% 基準，磁鐵有吸力。"))
    elif rate7 >= 0.5: lights.append(light("yellow", "7日訂閱率", f"{rate7:.1f}%", "偏低。CTA 往上移／首屏就給磁鐵入口。"))
    else: lights.append(light("red", "7日訂閱率", f"{rate7:.1f}%", "訂閱率<0.5%：磁鐵賣點或表單位置有問題，優先改首頁 CTA。"))

    fg = funnel("grow")
    weak = min((s for s in fg[1:] if s["rate"] is not None), key=lambda s: s["rate"], default=None)
    if weak:
        fix = {"看到CTA": "多數訪客沒滑到 CTA → 把訂閱區塊往上搬／文章內嵌表單。",
               "Email訂閱": "看到卻不填 → 換磁鐵標題與利益點文案。",
               "領到對話卡": "訂了卻沒到感謝頁 → 檢查 Kit 表單導向 /welcome 是否正常。"}.get(weak["step"], "")
        lights.append(light("yellow" if (weak["rate"] or 0) >= 10 else "red",
                            f"最弱一步：{weak['step']}", f"{weak['rate']}%", fix))

    # ── 出國模式告警：名單斷流＋網站掛掉 ─────────────────────────
    alerts = []
    if s7v >= 3 and sy == 0:
        alerts.append("名單斷流：過去 7 日平均有名單，但昨天掛零。")
    for url, name in [("https://grow.walk2light.com/", "光合作用 grow"),
                      ("https://www.walk2light.com/", "財富煉金術 www")]:
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                if r.status != 200: alerts.append(f"{name} 回應 {r.status}")
        except Exception as e:
            alerts.append(f"{name} 連不上（{type(e).__name__}）")
    if alerts:
        tg("🚨 北極星告警\n" + "\n".join("· " + a for a in alerts) +
           f"\n(台北 {now:%m/%d %H:%M}，看板 hsien33.github.io/w2l-warroom/北極星.html)")

    # ── 趨勢序列（近30天，給圖表）───────────────────────────────
    trend = []
    for i in range(30, 0, -1):
        dk = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        du = sum(daily.get(dk, {}).get(s, {}).get("users", 0) for s in ("grow", "wealth"))
        ds = sum(ev.get(dk, {}).get(s, {}).get("email_signup", 0) for s in ("grow", "wealth"))
        trend.append({"date": dk, "users": du, "signups": ds})

    write_json({"status": "ok", "generatedAt": now.strftime("%Y-%m-%d %H:%M"),
                "updated": now.strftime("%Y-%m-%d %H:%M 台北"), "yesterday_date": ystr,
                "yesterday": y1, "d7": d7, "d30": d30,
                "funnel": {"grow": fg, "wealth": funnel("wealth")},
                "utm": utm, "trend": trend, "lights": lights, "alerts": alerts})
    print("polaris.json updated: signup_y=%d signup_7d=%d rate7=%.2f%% alerts=%d"
          % (sy, s7v, rate7, len(alerts)))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # graceful：不 crash，寫出 status:error 讓看板顯示佔位卡；發 TG 告警
        msg = f"{type(e).__name__}: {e}"
        write_json({"status": "error", "error": msg,
                    "generatedAt": now.strftime("%Y-%m-%d %H:%M"),
                    "updated": now.strftime("%Y-%m-%d %H:%M 台北")})
        tg("⚠️ 北極星看板拉數失敗（ga_polaris.py）\n" + msg +
           "\n看板會顯示佔位卡，請看 Actions log。")
        print("ERROR (wrote status:error polaris.json):", msg.encode("ascii", "replace").decode())
        traceback.print_exc()
        sys.exit(0)   # 不讓 workflow fail — error 版 polaris.json 仍要 commit 上線
