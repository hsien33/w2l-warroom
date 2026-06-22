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

# ── 共用：從一段文字取「內容預覽」（金句卡取『帶走一句』、其餘取首行；去空白、截斷）──
def preview_of(text, n=48):
    if not text: return ""
    for line in str(text).splitlines():
        s = line.strip()
        if s.startswith("帶走一句"):
            return s.replace("：", ":").split(":", 1)[-1].strip()
    first = (str(text).strip().splitlines() or [""])[0].strip()
    return first[:n] + ("…" if len(first) > n else "")

# ── 2. 主集 Reel 庫存＋每集文案預覽：reels/schedule.json 內「有登錄且 mp4 存在」的集數 ──
reels_inventory = []          # 仍給舊用途
reels_content = {}            # day -> 文案首行預覽
try:
    sched = read_json(os.path.join(WC, "reels", "schedule.json"))
    for k, v in sched.items():
        if not str(k).isdigit(): continue
        f = v.get("file") if isinstance(v, dict) else v
        if f and os.path.exists(os.path.join(WC, "reels", f)):
            reels_inventory.append(int(k))
            reels_content[str(int(k))] = preview_of(v.get("caption", "") if isinstance(v, dict) else "")
except Exception as e:
    print("讀 reels/schedule.json 失敗：", e)
reels_inventory.sort()

# ── 共用：某 workflow 的 schedule cron 是否「未被註解」＝該線 cron 真的開著 ──
def cron_active(yml_name):
    try:
        yml = io.open(os.path.join(WC, ".github", "workflows", yml_name), encoding="utf-8").read()
    except Exception as e:
        print(f"讀 {yml_name} 失敗：", e); return False
    in_sched = False
    for line in yml.splitlines():
        s = line.strip()
        if s.startswith("schedule:") and not s.startswith("#"): in_sched = True; continue
        if in_sched:
            if s.startswith("- cron:"): return True
            if s and not s.startswith("#") and not s.startswith("-"): in_sched = False
    return False

# ── 3. 各線 cron 是否真的開著（＝有沒有設時程）──
warcard_cron = cron_active("warcard.yml")
fbq_cron     = cron_active("fb_quote.yml")
thread_cron  = cron_active("thread_rewrite.yml")
shorts_cron  = cron_active("shorts.yml")

# ── 3b. Shorts「每日主題」＝shorts/schedule.json（對齊 SHORTS_START）＋ready 旗標＋導向長片那行 ──
shorts_start = grep_start(os.path.join(WC, "src", "post_shorts.py"), "SHORTS_START", "2026-06-10")
shorts_content = {}
try:
    sh = read_json(os.path.join(WC, "shorts", "schedule.json"))
    for k, v in sh.items():
        if not str(k).isdigit() or not isinstance(v, dict): continue
        lead = ""
        for ln in (v.get("description", "") or "").splitlines():
            s = ln.strip()
            if "👉" in s or "youtu" in s.lower():
                lead = s; break
        shorts_content[str(int(k))] = {"title": (v.get("title", "") or "").strip(),
                                       "ready": bool(v.get("ready")), "lead": lead}
except Exception as e:
    print("讀 shorts/schedule.json 失敗：", e)

# 既有 week.json 的「人工維護欄」要保留（不被自動重算洗掉）
prev = {}
try: prev = read_json(os.path.join(HERE, "week.json"))
except Exception: pass

# ── 共用：明日待發頁要的「附件圖」＝preview_media/ 下符合命名的檔（有就帶 web 相對路徑）──
def media_if_exists(fname):
    return ("preview_media/" + fname) if os.path.exists(os.path.join(HERE, "preview_media", fname)) else ""

# ── 4. FB 金句卡「真實待發隊列」＝schedule.json 裡 day > posted_through 的卡（你核可、還沒發）＋金句預覽 ──
#     full＝整段文案、img＝preview_media/fbquote_day{N}.png（明日待發頁點開看完整內文＋金句卡圖）
POSTED_THROUGH = prev.get("fbquote_posted_through", 12)   # 雲端 dry-run 真讀 FB 得知；發過更多就改這數
fbq_queue = []
try:
    cards = read_json(os.path.join(WC, "fb_quote", "schedule.json"))["cards"]
    for c in sorted(cards, key=lambda c: int(c["day"])):
        if int(c["day"]) > POSTED_THROUGH:
            day = int(c["day"])
            fbq_queue.append({"day": day, "topic": c.get("topic", ""),
                              "content": preview_of(c.get("caption", "")),
                              "full": (c.get("caption", "") or "").strip(),
                              "img": media_if_exists(f"fbquote_day{day}.png")})
except Exception as e:
    print("讀 fb_quote/schedule.json 失敗：", e)

# ── 5. Thread「真實待發隊列」＝thread_rewrite/schedule.json 裡的 posts（你核可、還沒發）＋正文預覽＋整段正文 ──
thread_queue = []
try:
    posts = read_json(os.path.join(WC, "thread_rewrite", "schedule.json"))["posts"]
    for p in sorted(posts, key=lambda p: int(p["day"])):
        thread_queue.append({"day": int(p["day"]), "topic": p.get("topic", ""),
                             "content": preview_of(p.get("body", "")),
                             "full": (p.get("body", "") or "").strip()})
except Exception as e:
    print("讀 thread_rewrite/schedule.json 失敗：", e)

# ── 庫存自動 derive（從真排程算，非手打；給戰情室「各產線庫存」直接顯示）──
def _last(seq): return max(seq) if seq else None
social_prep = prev.get("social_prepared", [])
inventory_derived = {
    "title": "各產線庫存（自動算 · 非手打）",
    "lines": [
        {"name": "IG 戰況卡", "stock": ("每日即時生成" if warcard_cron else "cron 關"),
         "through": "—", "auto": ("✅ 每日 08:1x 自動發" if warcard_cron else "🔴 未排程")},
        {"name": "IG 主集 Reel", "stock": f"{len(reels_inventory)} 集已備",
         "through": (f"Day{_last(reels_inventory)}" if reels_inventory else "見底"),
         "auto": "✅ 20:3x 自動發"},
        {"name": "FB 粉專金句卡", "stock": f"{len(fbq_queue)} 張待發",
         "through": (f"DAY{_last([c['day'] for c in fbq_queue])}" if fbq_queue else "發完"),
         "auto": ("✅ 20:0x 自動發" if fbq_cron else "🔴 cron 關")},
        {"name": "Thread 改寫", "stock": f"{len(thread_queue)} 篇待發",
         "through": (f"對應 Day{_last([c['day'] for c in thread_queue])}" if thread_queue else "發完"),
         "auto": ("✅ 21:0x 自動發" if thread_cron else "🔴 cron 關")},
        {"name": "FB 社團文", "stock": f"{len(social_prep)} 天已備",
         "through": (social_prep[-1] if social_prep else "未備"), "auto": "🟡 週二/五手貼（LINE 提醒）"},
        {"name": "YouTube Shorts", "stock": prev.get("shorts_status", "none"),
         "through": "—", "auto": ("✅ 自動" if shorts_cron else "⚪ 暫停")},
    ],
}

out = {
    "updated": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%MZ"),
    "inventory_derived": inventory_derived,
    "warcard_start": warcard_start,
    "reel_start": reel_start,
    "warcard_cron": warcard_cron,
    "thread_cron": thread_cron,
    "thread_queue": thread_queue,
    "fbquote_cron": fbq_cron,
    "fbquote_queue": fbq_queue,
    "fbquote_posted_through": POSTED_THROUGH,
    "reels_inventory": reels_inventory,
    "reels_content": reels_content,
    # 人工維護：本週已備好的社團文（日期→{title,preview}）、Shorts 線狀態（none/producing/live）
    "social_prepared": prev.get("social_prepared", []),
    "social_content": prev.get("social_content", {}),
    "shorts_cron": shorts_cron,
    "shorts_status": prev.get("shorts_status", "none"),
    "shorts_start": shorts_start,
    "shorts_content": shorts_content,
    # 人工維護：戰況卡範例圖＋當天 caption 模板（明日待發頁 08:00 戰況卡點開看樣子）、Reel 影片附件對映
    "warcard_sample_img": prev.get("warcard_sample_img", ""),
    "warcard_caption_tpl": prev.get("warcard_caption_tpl", ""),
    "reels_media": prev.get("reels_media", {}),
}

with io.open(os.path.join(HERE, "week.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("✅ week.json 已產出")
print(json.dumps(out, ensure_ascii=False, indent=2))
