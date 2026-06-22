# -*- coding: utf-8 -*-
# 戰情室版本戳：一鍵更新 version.json ＋ index.html 裡的 BUILD/BUILT 常數（兩者永不漂移）。
# 用法：python bump_version.py        → 版本號＝今天日期.序號（同日自動 +1）
#       改完 index.html 內容後跑這支，再 git commit/push。
import json, re, datetime, os

HERE = os.path.dirname(os.path.abspath(__file__))
VJSON = os.path.join(HERE, "version.json")
INDEX = os.path.join(HERE, "index.html")

now = datetime.datetime.now()
today = now.strftime("%Y-%m-%d")
built = now.strftime("%Y-%m-%d %H:%M")

# 算今天的序號：讀舊 version.json，同日 +1，跨日歸 1
serial = 1
if os.path.exists(VJSON):
    try:
        old = json.load(open(VJSON, encoding="utf-8"))
        ov = str(old.get("version", ""))
        if ov.startswith(today + "."):
            serial = int(ov.split(".")[-1]) + 1
    except Exception:
        pass
version = f"{today}.{serial}"

# 寫 version.json（純 ASCII，跨平台安全）
json.dump({"version": version, "built": built}, open(VJSON, "w", encoding="utf-8"),
          ensure_ascii=True, indent=2)

# 同步 index.html 的 BUILD/BUILT 常數（drift-proof）
html = open(INDEX, encoding="utf-8").read()
new_line = f'const BUILD="{version}", BUILT="{built}";'
html2, n = re.subn(r'const BUILD="[^"]*", BUILT="[^"]*";', new_line, html, count=1)
if n != 1:
    raise SystemExit("❌ 找不到 index.html 的 BUILD/BUILT 常數行，請確認那行存在且格式正確")
open(INDEX, "w", encoding="utf-8").write(html2)

print(f"OK  version={version}  built={built}")
print("   → version.json 與 index.html(BUILD/BUILT) 已同步。記得 git add index.html version.json 再 push。")
