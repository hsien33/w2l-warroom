# -*- coding: utf-8 -*-
# 裁定永久收集器：把戰情室「核可/不同意」按鈕送進 ntfy 的訊息，定時抓下來永久存進 repo。
# ntfy 免費頻道只留 ~12h，故每小時 poll 一次、去重(用 message id)、append 到 verdicts.jsonl。
# 副總任何 session 只要 git pull 讀 verdicts.jsonl 就拿得到 Jeff 全部裁示（不再受 12h 限制）。
import os, io, json, urllib.request

TOPIC = "w2l-jeff-verdict-9x7k2m4q"
HERE  = os.path.dirname(os.path.abspath(__file__))
JSONL = os.path.join(HERE, "verdicts.jsonl")

def fetch():
    url = f"https://ntfy.sh/{TOPIC}/json?poll=1&since=12h"
    req = urllib.request.Request(url, headers={"User-Agent": "w2l-verdict-collector"})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode("utf-8", "replace")
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except Exception:
            continue
        if m.get("event") == "message":
            out.append(m)
    return out

def load_seen():
    seen, rows = set(), []
    if os.path.exists(JSONL):
        for line in io.open(JSONL, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
                seen.add(rows[-1].get("id"))
            except Exception:
                pass
    return seen, rows

def main():
    seen, rows = load_seen()
    new = [m for m in fetch() if m.get("id") not in seen]
    if not new:
        print("[verdict] 沒有新裁示")
        return
    new.sort(key=lambda m: m.get("time", 0))
    with io.open(JSONL, "a", encoding="utf-8") as f:
        for m in new:
            rec = {"id": m.get("id"), "time": m.get("time"),
                   "title": m.get("title", ""), "message": m.get("message", "")}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[verdict] 收進 {len(new)} 條新裁示（累計 {len(rows)+len(new)} 條）")

if __name__ == "__main__":
    main()
