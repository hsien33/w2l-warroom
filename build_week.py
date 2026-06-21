# -*- coding: utf-8 -*-
# 產出 week.json＝「未來一周排程板」的真實排程設定（從 warcard-auto 真實源頭推導，不手寫造假）。
# 戰情室前端用 new Date() 即時算日期/星期/今天，再套這份設定決定每格紅綠＋摘要。
# 排程狀態改變時（補 Reel 庫存、FB金句卡上線、排新一週）重跑本檔即可。
# 用法：python build_week.py   （需與 ../戰況卡自動發 並存於 Claude/ 下）
import os, io, json, re, sys, datetime
sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
WC   = os.path.normpath(os.path.join(HERE, "..", "戰況卡自動發"))   # warcard-auto 本機路徑

def read_json(p):
    with io.open(p, encoding="utf-8") as f: return json.load(f)

def grep_start(path, key, default):
    """從 .py 抓 env('KEY','YYYY-MM-DD') 的預設值。"""
    try:
        txt = io.open(path, encoding="utf-8").read()
        m = re.search(rf'env\(\s*["\']{key}["\']\s*,\s*["\'](\d{{4}}-\d{{2}}-\d{{2}})["\']', txt)
        if m: return m.group(1)
    except Exception: pass
    return default

# ── 1. 天數起算（從真實腳本抓，抓不到用已知預設）──
reel_start    = grep_start(os.path.join(WC, "src", "post_reel.py"), "REEL_START",    "2026-06-10")
warcard_start = grep_start(os.path.join(WC, "src", "daily.py"),     "WARCARD_START", "2026-06-11")

# ── 2. 主集 Reel 庫存：reels/schedule.json 內「有登錄且 mp4 存在」的集數 ──
reels_inventory = []
try:
    sched = read_json(os.path.join(WC, "reels", "schedule.json"))
    for k, v in sched.items():
        if not str(k).isdigit(): continue
        f = v.get("file") if isinstance(v, dict) else v
        if f and os.path.exists(os.path.join(WC, "reels", f)):
            reels_inventory.append(int(k))
except Exception as e:
    print("讀 reels/schedule.json 失敗：", e)
reels_inventory.sort()

# ── 3. FB 粉專金句卡：是否上線（fb_quote.yml 的 schedule cron 有沒有被註解）＋待發隊列 ──
fbq_live = False
try:
    yml = io.open(os.path.join(WC, ".github", "workflows", "fb_quote.yml"), encoding="utf-8").read()
    # 找 schedule: 區塊下是否有「未被註解」的 - cron
    in_sched = False
    for line in yml.splitlines():
        s = line.strip()
        if s.startswith("schedule:") and not s.startswith("#"): in_sched = True; continue
        if in_sched:
            if s.startswith("- cron:"): fbq_live = True; break
            if s and not s.startswith("#") and not s.startswith("-"): in_sched = False  # 離開 schedule 區塊
except Exception as e:
    print("讀 fb_quote.yml 失敗：", e)

# 金句卡 schedule（day→topic）；posted_through＝已驗證在 FB 上發到第幾天（雲端 dry-run 真讀 FB 得知）
fbq_topics = {}
fbq_last = 0
try:
    fq = read_json(os.path.join(WC, "fb_quote", "schedule.json"))["cards"]
    for c in fq:
        fbq_topics[int(c["day"])] = c.get("topic", "")
        fbq_last = max(fbq_last, int(c["day"]))
except Exception as e:
    print("讀 fb_quote/schedule.json 失敗：", e)
POSTED_THROUGH = 12        # 2026-06-21 雲端 dry-run 真讀 FB 粉專確認 DAY004–012 已發；重跑前若再發過請更新
fbq_next = POSTED_THROUGH + 1

out = {
    "updated": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%MZ"),
    "reel_start": reel_start,
    "warcard_start": warcard_start,
    "reels_inventory": reels_inventory,
    "fbquote": {
        "live": fbq_live,
        "next_day": fbq_next,
        "last_day": fbq_last,
        "topics": {str(k): v for k, v in fbq_topics.items()},
    },
    # 以下三線目前無自動化（社團轉傳手動／Shorts 未建 poster／Thread 手動）＝板上恆紅，靠這份標記
    "manual_lines": {"club": True, "shorts": True, "thread": True},
}

with io.open(os.path.join(HERE, "week.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("✅ week.json 已產出")
print(json.dumps(out, ensure_ascii=False, indent=2))
