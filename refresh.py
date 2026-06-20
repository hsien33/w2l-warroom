# -*- coding: utf-8 -*-
# 更新 data.json：即時 IG 追蹤數 + D-day + 戰況/主集天數(兩套別混) + 各社群平台真實數字。
# 社群數字全 gated on 金鑰：沒給金鑰的平台保留舊值/標未接，給了就抓真的。跑在 GitHub Actions(每30分)。
import os, sys, json, datetime, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
def env(k, d=""): return os.environ.get(k, d).strip()
def getj(u):
    with urllib.request.urlopen(u, timeout=30) as r: return json.loads(r.read())

VER = env("GRAPH_API_VERSION", "v22.0")
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.join(HERE, "data.json")
d = json.load(open(P, encoding="utf-8"))
now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
stamp = now.strftime("%m/%d %H:%M")
ch = d.get("channels", {})

# ── IG 追蹤數（有 token）──
try:
    ig = int(getj(f"https://graph.instagram.com/{VER}/me?fields=followers_count&access_token={env('IG_ACCESS_TOKEN')}")["followers_count"])
    d["followers"] = ig
    ch["ig"] = {"followers": ig, "live": True, "updated": stamp}; print("IG", ig)
except Exception as e:
    print("IG 失敗:", e); ch.setdefault("ig", {})["live"] = False

# ── YouTube 訂閱/觀看（gated YT_API_KEY + YT_CHANNEL_ID）──
ytk, ytc = env("YT_API_KEY"), env("YT_CHANNEL_ID")
if ytk and ytc:
    try:
        s = getj(f"https://www.googleapis.com/youtube/v3/channels?part=statistics&id={ytc}&key={ytk}")["items"][0]["statistics"]
        ch["yt"] = {"subs": int(s.get("subscriberCount", 0)), "views": int(s.get("viewCount", 0)),
                    "videos": int(s.get("videoCount", 0)), "live": True, "updated": stamp}
        print("YT subs", s.get("subscriberCount"))
    except Exception as e: print("YT 失敗:", e); ch.setdefault("yt", {})["live"] = False
else:
    ch.setdefault("yt", {})["live"] = False

# ── FB 粉專 追蹤數 + 最新貼文（gated FB_PAGE_TOKEN + FB_PAGE_ID）──
fbt, fbp, fbv = env("FB_PAGE_TOKEN"), env("FB_PAGE_ID"), env("FB_API_VERSION", "v22.0")
if fbt and fbp:
    try:
        info = getj(f"https://graph.facebook.com/{fbv}/{fbp}?fields=followers_count,fan_count,name&access_token={fbt}")
        latest = getj(f"https://graph.facebook.com/{fbv}/{fbp}/posts?fields=message,created_time,permalink_url&limit=1&access_token={fbt}")
        lp = (latest.get("data") or [{}])[0]
        ch["fb"] = {"followers": info.get("followers_count") or info.get("fan_count"),
                    "last_msg": (lp.get("message", "") or "")[:34], "last_time": (lp.get("created_time", "") or "")[:10],
                    "last_url": lp.get("permalink_url", ""), "live": True, "updated": stamp}
        print("FB", ch["fb"])
    except Exception as e: print("FB 失敗:", e); ch.setdefault("fb", {})["live"] = False
else:
    ch.setdefault("fb", {})["live"] = False

# ── Threads 追蹤數（gated THREADS_ACCESS_TOKEN + THREADS_USER_ID）──
tht, thu, thv = env("THREADS_ACCESS_TOKEN"), env("THREADS_USER_ID"), env("THREADS_API_VERSION", "v1.0")
if tht and thu:
    try:
        ins = getj(f"https://graph.threads.net/{thv}/{thu}/threads_insights?metric=followers_count&access_token={tht}")
        val = ins["data"][0]["total_value"]["value"]
        ch["threads"] = {"followers": val, "live": True, "updated": stamp}; print("Threads", val)
    except Exception as e: print("Threads 失敗:", e); ch.setdefault("threads", {})["live"] = False
else:
    ch.setdefault("threads", {})["live"] = False

# ── 官網 GA4 近7天瀏覽數（gated GA4_SA_JSON 服務帳戶 + GA4_PROPERTY_ID）──
ga_json, ga_prop = env("GA4_SA_JSON"), env("GA4_PROPERTY_ID")
if ga_json and ga_prop:
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests
        creds = service_account.Credentials.from_service_account_info(
            json.loads(ga_json), scopes=["https://www.googleapis.com/auth/analytics.readonly"])
        creds.refresh(google.auth.transport.requests.Request())
        body = json.dumps({"dateRanges": [{"startDate": "7daysAgo", "endDate": "today"}],
                           "metrics": [{"name": "screenPageViews"}, {"name": "activeUsers"}]}).encode()
        req = urllib.request.Request(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{ga_prop}:runReport",
            data=body, method="POST",
            headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r: rep = json.loads(r.read())
        rows = rep.get("rows", [])
        pv = int(rows[0]["metricValues"][0]["value"]) if rows else 0
        au = int(rows[0]["metricValues"][1]["value"]) if rows else 0
        ch["site"] = {"pageviews": pv, "users": au, "live": True, "updated": stamp}; print("GA4 pv", pv)
    except Exception as e:
        print("GA4 失敗:", e); ch.setdefault("site", {})["live"] = False
else:
    ch.setdefault("site", {}).setdefault("live", False)

d["channels"] = ch
d["updated"] = now.strftime("%Y-%m-%d %H:%M 台北")
d["dday"] = (datetime.date(2026, 7, 10) - now.date()).days
d["day"] = (now.date() - datetime.date(2026, 6, 10)).days       # 主集 Reel 集數＝日期−10（6/20＝Day10）
d["warday"] = (now.date() - datetime.date(2026, 6, 11)).days    # 🔴 戰況卡天數＝日期−11（6/20＝第9天），兩套別混
json.dump(d, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"data.json 更新 · 戰況第{d['warday']}天 · 主集 Day{d['day']} · D-{d['dday']}")
