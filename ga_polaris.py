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

SITES = {"grow.walk2light.com": "grow", "www.walk2light.com": "wealth",
         "walk2light.com": "wealth", "new.walk2light.com": "wealth"}  # localhost/bak 等測試網域自動略過
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
    _UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    for url, name in [("https://grow.walk2light.com/", "光合作用 grow"),
                      ("https://www.walk2light.com/", "財富煉金術 www")]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            urllib.request.urlopen(req, timeout=20).close()
        except urllib.error.HTTPError:
            # 伺服器有回應（多半是 GitHub 機房 IP 被 CDN/防護當機器人擋的 4xx/5xx challenge）
            # ＝站是活的，不誤報。站真的掛掉會是連線層失敗（下面那個 except）；
            # 內容/追蹤問題另由「昨天 0 人造訪」的資料告警把關。
            pass
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

    # ══════════ v2：工具觀測（0703 圓桌規格）═══════════════════════
    # slug 正規化：/tools/xxx(.html)(/) → xxx；index/'' = 工具總覽不進榜
    def slugify(pp):
        s = pp.split("?")[0]
        if not s.startswith("/tools/"): return None
        s = s[len("/tools/"):].strip("/").lower()
        if s.endswith(".html"): s = s[:-5]
        if s in ("", "index"): return None
        return s

    def dstr(dt): return f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"
    tstr = today.strftime("%Y-%m-%d")
    def in_win(dk, days, end_excl=None):
        end = end_excl or tstr
        lo = (datetime.datetime.strptime(end, "%Y-%m-%d").date()
              - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        return lo <= dk < end

    # T1：每工具×每日 開頁人數/瀏覽（含今天，今天另存 today 標「累積中」）
    t1 = run_report({"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                     "dimensions": [{"name": "date"}, {"name": "hostName"}, {"name": "pagePath"}],
                     "metrics": [{"name": "totalUsers"}, {"name": "screenPageViews"}],
                     "dimensionFilter": {"filter": {"fieldName": "pagePath",
                         "stringFilter": {"matchType": "BEGINS_WITH", "value": "/tools/"}}},
                     "limit": 100000})
    tools = {}   # slug → 資料
    for (dt, host, pp), (tu, pv) in rows(t1):
        slug = slugify(pp)
        site = SITES.get(host)
        if not slug or not site: continue
        t = tools.setdefault(slug, {"slug": slug, "site": site, "daily": {},
                                    "today": 0, "d7": 0, "d30": 0, "d7_prev": 0, "pv30": 0,
                                    "ev7": {}, "ev30": {}, "outbound": [], "channels": []})
        dk = dstr(dt)
        t["daily"][dk] = t["daily"].get(dk, 0) + int(tu)
        t["pv30"] += int(pv)
        if dk == tstr: t["today"] += int(tu)
        else:
            if in_win(dk, 7):  t["d7"] += int(tu)
            if in_win(dk, 30): t["d30"] += int(tu)
            if in_win(dk, 7, end_excl=(today - datetime.timedelta(days=7)).strftime("%Y-%m-%d")):
                t["d7_prev"] += int(tu)

    # T2：每工具×事件（tool_engaged/tool_result/email_signup/outbound_click）7日/30日
    t2 = run_report({"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                     "dimensions": [{"name": "date"}, {"name": "hostName"},
                                    {"name": "pagePath"}, {"name": "eventName"}],
                     "metrics": [{"name": "totalUsers"}],
                     "dimensionFilter": {"andGroup": {"expressions": [
                         {"filter": {"fieldName": "pagePath",
                             "stringFilter": {"matchType": "BEGINS_WITH", "value": "/tools/"}}},
                         {"filter": {"fieldName": "eventName", "inListFilter": {"values":
                             ["tool_engaged", "tool_result", "email_signup", "outbound_click", "cta_click"]}}}]}},
                     "limit": 100000})
    for (dt, host, pp, name), (tu,) in rows(t2):
        slug = slugify(pp)
        if not slug or slug not in tools: continue
        dk = dstr(dt)
        if dk != tstr and in_win(dk, 7):
            tools[slug]["ev7"][name] = tools[slug]["ev7"].get(name, 0) + int(tu)
        if in_win(dk, 30) or dk == tstr:
            tools[slug]["ev30"][name] = tools[slug]["ev30"].get(name, 0) + int(tu)

    # T3：外連明細（需 GA4 註冊 event-scoped 自訂維度 domain/link；未註冊→優雅降級）
    outbound_status = "ok"
    outbound_top = []   # 全站外連 Top（domain 彙總）
    try:
        t3 = run_report({"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                         "dimensions": [{"name": "customEvent:domain"}, {"name": "pagePath"}],
                         "metrics": [{"name": "eventCount"}, {"name": "totalUsers"}],
                         "dimensionFilter": {"filter": {"fieldName": "eventName",
                             "stringFilter": {"value": "outbound_click"}}},
                         "orderBys": [{"metric": {"metricName": "eventCount"}, "desc": True}],
                         "limit": 2000})
        dom_agg = {}
        for (dom, pp), (cnt, tu) in rows(t3):
            if dom in ("", "(not set)"):
                continue
            a = dom_agg.setdefault(dom, {"domain": dom, "clicks": 0, "users": 0, "pages": {}})
            a["clicks"] += int(cnt); a["users"] += int(tu)
            a["pages"][pp] = a["pages"].get(pp, 0) + int(cnt)
            slug = slugify(pp)
            if slug and slug in tools:
                tools[slug]["outbound"].append({"domain": dom, "clicks": int(cnt)})
        outbound_top = sorted(dom_agg.values(), key=lambda x: -x["clicks"])[:10]
        for a in outbound_top:
            a["pages"] = sorted(a["pages"].items(), key=lambda kv: -kv[1])[:3]
        if not outbound_top:
            outbound_status = "empty"  # 事件才剛開始記或維度剛註冊
    except Exception as e3:
        outbound_status = "pending_dimension"   # domain 維度未註冊：GA4 後台 1 分鐘可補
        print("T3 outbound detail unavailable:", type(e3).__name__)

    # T4：每工具流量管道 Top（30日）
    try:
        t4 = run_report({"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                         "dimensions": [{"name": "pagePath"}, {"name": "sessionDefaultChannelGroup"}],
                         "metrics": [{"name": "totalUsers"}],
                         "dimensionFilter": {"filter": {"fieldName": "pagePath",
                             "stringFilter": {"matchType": "BEGINS_WITH", "value": "/tools/"}}},
                         "limit": 5000})
        for (pp, ch), (tu,) in rows(t4):
            slug = slugify(pp)
            if slug and slug in tools:
                tools[slug]["channels"].append({"ch": ch, "users": int(tu)})
        for t in tools.values():
            t["channels"] = sorted(t["channels"], key=lambda x: -x["users"])[:5]
    except Exception as e4:
        print("T4 channels unavailable:", type(e4).__name__)

    # 徽章引擎（圓桌定版：全部有絕對門檻，防小樣本假冠軍）
    tool_list = list(tools.values())
    d7_vals = sorted(t["d7"] for t in tool_list) or [0]
    d7_avg = (sum(d7_vals) / len(d7_vals)) if d7_vals else 0
    for t in tool_list:
        eng7 = t["ev7"].get("tool_engaged", 0); res7 = t["ev7"].get("tool_result", 0)
        t["engaged7"] = eng7; t["result7"] = res7
        t["emails30"] = t["ev30"].get("email_signup", 0)
        t["outbound30"] = t["ev30"].get("outbound_click", 0)
        t["engage_rate"] = round(eng7 / t["d7"] * 100) if t["d7"] else None       # 互動率=有玩÷點開
        t["finish_rate"] = round(res7 / eng7 * 100) if eng7 else None             # 完成率=出結果÷有玩
        badges = []
        if t["d7"] >= 20 and d7_avg and t["d7"] >= d7_avg * 2 and (t["finish_rate"] or 0) >= 40:
            badges.append("爆款")
        elif t["d7"] >= 20 and d7_avg and t["d7"] >= d7_avg * 2 and (t["finish_rate"] or 0) < 40:
            badges.append("虛胖")
        elif (t["finish_rate"] or 0) >= 60 and t["d7"] < max(10, d7_avg):
            badges.append("遺珠")
        if t["d7"] >= 10 and t["d7_prev"] and t["d7"] >= t["d7_prev"] * 1.5:
            badges.append("竄升")
        if t["d30"] < 5:
            badges.append("沉睡")
        if t["d30"] == 0 and t["pv30"] == 0:
            badges.append("無資料")
        t["badges"] = badges
        t["daily"] = [{"date": (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d"),
                       "users": t["daily"].get((today - datetime.timedelta(days=i)).strftime("%Y-%m-%d"), 0)}
                      for i in range(30, -1, -1)]
        del t["ev7"]; del t["ev30"]
    tool_list.sort(key=lambda t: (-(t["emails30"]), -(t["d7"]), -(t["d30"])))

    # 來源四分類（IG／Google 搜尋／直接輸入／其他）＋各自帶名單
    def src4(source, medium):
        s = (source or "").lower(); m = (medium or "").lower()
        if "instagram" in s or s == "ig" or "ig" == s: return "IG 帶來的"
        if "google" in s and ("organic" in m or m == "organic"): return "Google 搜來的"
        if s == "(direct)": return "直接輸入網址"
        return "其他"
    sources4 = {}
    for u in utm:
        k = src4(u["source"], u["medium"])
        g = sources4.setdefault(k, {"label": k, "users": 0, "signups": 0})
        g["users"] += u["users"]; g["signups"] += u["signups"]
    sources4 = sorted(sources4.values(), key=lambda x: -x["users"])
    ig_share = 0
    tot_u = sum(g["users"] for g in sources4) or 1
    for g in sources4:
        if g["label"] == "IG 帶來的": ig_share = round(g["users"] / tot_u * 100)

    # ══════════ v3 drill-down：各站流量管道 ＋ 各站最多人看的頁 ══════════
    CH_ZH = {"Organic Search": "自然搜尋(Google)", "Organic Social": "社群(IG/FB)",
             "Direct": "直接輸入網址", "Referral": "別的網站連來", "Paid Search": "付費搜尋",
             "Paid Social": "付費社群", "Email": "電子郵件", "Unassigned": "未分類",
             "Cross-network": "跨網路廣告", "Organic Video": "影音(YT)"}
    # Q5：各站×管道 → 使用者＋名單（自然流量 vs 社群 vs 直接一眼看出）
    q5 = run_report({"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                     "dimensions": [{"name": "hostName"}, {"name": "sessionDefaultChannelGroup"}],
                     "metrics": [{"name": "activeUsers"}, {"name": "sessions"}], "limit": 500})
    q5b = run_report({"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                      "dimensions": [{"name": "hostName"}, {"name": "sessionDefaultChannelGroup"}],
                      "metrics": [{"name": "eventCount"}],
                      "dimensionFilter": {"filter": {"fieldName": "eventName",
                          "stringFilter": {"value": "email_signup"}}}, "limit": 500})
    sg_ch = {}
    for (host, ch), (c,) in rows(q5b):
        s = SITES.get(host)
        if s: sg_ch[(s, ch)] = sg_ch.get((s, ch), 0) + int(c)
    channels = {"grow": {}, "wealth": {}}
    for (host, ch), (au, ss) in rows(q5):
        s = SITES.get(host)
        if not s: continue
        d0 = channels[s].setdefault(ch, {"ch": CH_ZH.get(ch, ch), "raw": ch, "users": 0, "signups": 0})
        d0["users"] += int(au); d0["signups"] += sg_ch.get((s, ch), 0) if d0["users"] == int(au) else 0
    # signups 只加一次（上面條件避免重複），改成事後補
    for s in ("grow", "wealth"):
        for ch, d0 in channels[s].items():
            d0["signups"] = sg_ch.get((s, ch), 0)
        channels[s] = sorted(channels[s].values(), key=lambda x: -x["users"])[:6]

    # Q6：各站最多人看的頁（排除工具頁，工具另有專榜）→ 瀏覽＋人數
    q6 = run_report({"dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                     "dimensions": [{"name": "hostName"}, {"name": "pagePath"}, {"name": "pageTitle"}],
                     "metrics": [{"name": "screenPageViews"}, {"name": "totalUsers"}],
                     "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
                     "limit": 300})
    tp_agg = {"grow": {}, "wealth": {}}                # 同標題不同網址(首頁/utm變體)合併，避免重複列
    for (host, pp, title), (pv, tu) in rows(q6):
        s = SITES.get(host)
        if not s: continue
        if pp.startswith("/tools/"): continue          # 工具走專榜
        nm = (title.split("｜")[0].split("|")[0]).strip() or pp
        nm = nm[:34]
        g = tp_agg[s].setdefault(nm, {"name": nm, "path": pp, "views": 0, "users": 0})
        g["views"] += int(pv); g["users"] += int(tu)
    top_pages = {s: sorted(tp_agg[s].values(), key=lambda x: -x["views"])[:8]
                 for s in ("grow", "wealth")}

    # 告警引擎 v2（三段式人話卡：發生什麼/可能原因/一個動作）
    cards = []
    def card(level, what, why, action, link=""):
        cards.append({"level": level, "what": what, "why": why, "action": action, "link": link})
    yg = y1["sites"].get("grow", {}).get("users", 0); yw = y1["sites"].get("wealth", {}).get("users", 0)
    if yg == 0 and d7["sites"].get("grow", {}).get("users", 0) > 5:
        card("red", "光合作用站昨天 0 人造訪（平常 7 天有 %d 人）" % d7["sites"]["grow"]["users"],
             "可能是追蹤器斷線或網站掛了", "開一次網站確認活著", "https://grow.walk2light.com/")
    if yw == 0 and d7["sites"].get("wealth", {}).get("users", 0) > 5:
        card("red", "財富站昨天 0 人造訪（平常 7 天有 %d 人）" % d7["sites"]["wealth"]["users"],
             "可能是追蹤器斷線或網站掛了", "開一次網站確認活著", "https://www.walk2light.com/")
    md7 = d7["events"].get("magnet_delivered", 0); su7 = d7["events"].get("email_signup", 0)
    if su7 >= 5 and md7 < su7 * 0.9:
        card("red", "7 天有 %d 人留 Email，但只有 %d 人領到贈品" % (su7, md7),
             "感謝頁或領卡連結可能壞了——讀者留了信箱在空等", "去訂閱一次走完整流程", "https://grow.walk2light.com/")
    if su7 == 0 and d7["users"] > 20:
        card("red", "這 7 天有 %d 個訪客，但 0 人留 Email" % d7["users"],
             "訂閱入口可能壞了，或磁鐵完全沒吸引力", "先測訂閱表單能不能送出", "https://grow.walk2light.com/")
    for t in tool_list:
        if t["engaged7"] >= 5 and t["result7"] == 0:
            card("yellow", "「%s」7 天有 %d 人動手用、但 0 人用到出結果" % (t["slug"], t["engaged7"]),
                 "工具中途可能卡住或壞了", "親自玩一次到最後", "")
    prev7 = agg(14)["events"].get("email_signup", 0) - su7
    if prev7 >= 5 and su7 < prev7 * 0.7:
        card("yellow", "本週新名單 %d，比上週（%d）掉了三成以上" % (su7, prev7),
             "本週內容可能都沒導向訂閱", "下一篇內容加訂閱鉤子", "")
    if ig_share > 70:
        card("yellow", "流量 %d%% 都靠 IG（雞蛋都在一個籃子）" % ig_share,
             "IG 一限流名單就斷", "回國後補 1-2 篇 SEO 文", "")

    # 今日一句話（規則模板，不用 AI）
    if any(c["level"] == "red" for c in cards):
        summary = "有 %d 件事需要你看一下（見下方紅卡）" % sum(1 for c in cards if c["level"] == "red")
    elif sy > 0:
        summary = "今天正常：昨天新增 %d 位名單%s" % (sy, "、工具有 %d 人在用" % sum(t["today"] for t in tool_list) if tool_list else "")
    elif su7 > 0:
        summary = "今天平靜：昨天沒有新名單，但 7 天累計 %d 位、一切正常" % su7
    else:
        summary = "資料剛開始累積——新追蹤今天才上線，給它 1-2 天長數字"

    # 各站近30天趨勢（給切換到單站時的圖）
    trend_site = {"grow": [], "wealth": []}
    for s in ("grow", "wealth"):
        for i in range(30, 0, -1):
            dk = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            trend_site[s].append({"date": dk,
                "users": daily.get(dk, {}).get(s, {}).get("users", 0),
                "signups": ev.get(dk, {}).get(s, {}).get("email_signup", 0)})

    # 各站 30 天北極星摘要（給第一屏兩站對照帶）
    def site_summary(s):
        s30 = d30["sites"].get(s, {"users": 0, "events": {}})
        s7 = d7["sites"].get(s, {"users": 0, "events": {}})
        sig30 = s30["events"].get("email_signup", 0)
        sig7 = s7["events"].get("email_signup", 0)
        sigY = y1["sites"].get(s, {}).get("events", {}).get("email_signup", 0)
        rate = round(sig7 / s7["users"] * 100, 1) if s7["users"] else None
        return {"signups30": sig30, "signups7": sig7, "signupsY": sigY,
                "users30": s30["users"], "users7": s7["users"], "rate7": rate}

    write_json({"status": "ok", "generatedAt": now.strftime("%Y-%m-%d %H:%M"),
                "updated": now.strftime("%Y-%m-%d %H:%M 台北"), "yesterday_date": ystr,
                "yesterday": y1, "d7": d7, "d30": d30,
                "funnel": {"grow": fg, "wealth": funnel("wealth")},
                "utm": utm, "trend": trend, "lights": lights, "alerts": alerts,
                "v2": {"tools": tool_list, "outbound_top": outbound_top,
                        "outbound_status": outbound_status, "sources4": sources4,
                        "ig_share": ig_share, "cards": cards, "summary": summary,
                        "signup_total_30d": d30["events"].get("email_signup", 0)},
                "v3": {"channels": channels, "top_pages": top_pages,
                        "trend_site": trend_site,
                        "site_sum": {"grow": site_summary("grow"), "wealth": site_summary("wealth")}}})
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
