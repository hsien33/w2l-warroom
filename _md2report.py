# -*- coding: utf-8 -*-
# 把自走成果 .md 轉成戰情室報告 HTML（沿用夜間成果樣式＋品牌 favicon），並寫進存檔＋更新 reports.json。
import re, html, io, json, os, sys, datetime
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))

SRC  = sys.argv[1]
DATE = sys.argv[2]                       # 2026-06-22
TITLE= sys.argv[3]                       # 報告標題
SUMMARY = sys.argv[4] if len(sys.argv)>4 else ""

md = io.open(SRC, encoding="utf-8").read()

def inline(s):
    s = html.escape(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)
    return s

out, i, lines = [], 0, md.split("\n")
list_open = None  # 'ul' / 'ol'
def close_list():
    global list_open
    if list_open: out.append(f"</{list_open}>"); list_open=None

while i < len(lines):
    ln = lines[i].rstrip("\n")
    s = ln.strip()
    # 原生 HTML（details/summary）直接放行
    if re.match(r'</?(details|summary|div|br)', s):
        close_list(); out.append(ln); i+=1; continue
    if s.startswith("> "):                       # blockquote（可連續）
        close_list(); buf=[]
        while i < len(lines) and lines[i].strip().startswith(">"):
            buf.append(inline(lines[i].strip()[1:].strip())); i+=1
        out.append("<blockquote>"+"<br>".join(buf)+"</blockquote>"); continue
    if re.match(r'^#{1,3}\s', s):                 # 標題
        close_list(); lvl=len(s)-len(s.lstrip("#")); txt=inline(s[lvl:].strip())
        out.append(f"<h{lvl}>{txt}</h{lvl}>"); i+=1; continue
    if s.startswith("|") and i+1<len(lines) and re.match(r'^\|[\s:|-]+\|?$', lines[i+1].strip()):
        close_list()
        header=[c.strip() for c in s.strip("|").split("|")]
        out.append("<table><thead><tr>"+"".join(f"<th>{inline(c)}</th>" for c in header)+"</tr></thead><tbody>")
        i+=2
        while i<len(lines) and lines[i].strip().startswith("|"):
            cells=[c.strip() for c in lines[i].strip().strip("|").split("|")]
            out.append("<tr>"+"".join(f"<td>{inline(c)}</td>" for c in cells)+"</tr>"); i+=1
        out.append("</tbody></table>"); continue
    if s == "---":
        close_list(); out.append("<hr>"); i+=1; continue
    m=re.match(r'^(\d+)\.\s+(.*)', s)
    if m:                                         # 有序清單
        if list_open!='ol': close_list(); out.append("<ol>"); list_open='ol'
        out.append(f"<li>{inline(m.group(2))}</li>"); i+=1; continue
    if s.startswith("- "):                        # 無序清單
        if list_open!='ul': close_list(); out.append("<ul>"); list_open='ul'
        out.append(f"<li>{inline(s[2:])}</li>"); i+=1; continue
    if s == "":
        close_list(); i+=1; continue
    close_list(); out.append(f"<p>{inline(s)}</p>"); i+=1

close_list()
content = "\n".join(out)

FAVICON = ("<link rel=\"icon\" href=\"data:image/svg+xml,"
 "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 128 128'>"
 "<circle cx='64' cy='64' r='63' fill='%230f172a'/>"
 "<polygon points='64,20 96,68 79,68 79,106 49,106 49,68 32,68' fill='%23F4C430'/></svg>\">")

STYLE = (":root{--gold:#c9a44c;--ink:#2b2720;--mid:#55503f;--line:#e7dfd0}*{box-sizing:border-box}"
 "body{margin:0;background:#f3eee3;color:var(--ink);font-family:\"Noto Sans TC\",sans-serif;line-height:1.8;font-size:16px}"
 ".wrap{max-width:880px;margin:0 auto;padding:24px 18px 70px}"
 ".card{background:#fffdf8;border:1px solid var(--line);border-radius:18px;padding:30px clamp(16px,4vw,42px);box-shadow:0 2px 6px rgba(60,50,30,.05),0 24px 60px -32px rgba(70,55,30,.3)}"
 "h1{font-weight:900;font-size:24px;border-bottom:3px solid;border-image:linear-gradient(90deg,var(--gold),transparent)1;padding-bottom:.3em}"
 "h2{font-weight:900;font-size:19px;margin:1.5em 0 .5em;border-left:5px solid var(--gold);padding-left:12px}"
 "h3{font-size:16px;margin:1em 0 .3em}a{color:#b07d1a}"
 "table{border-collapse:collapse;width:100%;margin:.8em 0;font-size:14px;display:block;overflow-x:auto}"
 "th,td{border:1px solid var(--line);padding:8px 11px;text-align:left;vertical-align:top}th{background:#efe7d6;white-space:nowrap}tr:nth-child(even) td{background:#fbf7ee}"
 "code{background:#f1ebdd;padding:2px 6px;border-radius:5px;font-size:.88em}ul,ol{padding-left:1.4em}li{margin:.3em 0}"
 "blockquote{margin:.8em 0;padding:10px 16px;background:#faf5e9;border-left:4px solid var(--gold);border-radius:0 9px 9px 0;color:var(--mid)}"
 "details{margin:.6em 0;background:#faf5e9;border:1px solid var(--line);border-radius:10px;padding:8px 16px}"
 "summary{cursor:pointer;font-weight:800;padding:11px 14px;margin:-8px -16px;color:#3a3424;list-style:none;display:flex;align-items:center;gap:10px;border-radius:9px;background:#f3ead4;transition:background .15s}"
 "summary::-webkit-details-marker{display:none}summary::before{content:'\\25B6';color:#b07d1a;font-size:.78em;transition:transform .2s;flex:0 0 auto}"
 "details[open]>summary{margin-bottom:6px}details[open]>summary::before{transform:rotate(90deg)}summary:hover{background:#ecdcb9}"
 "p,li{color:var(--mid)}strong{color:var(--ink)}.back{display:inline-block;margin-bottom:14px;color:#b07d1a;text-decoration:none}hr{border:none;border-top:1px solid var(--line);margin:1.4em 0}")

PAGE = (f"<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
 f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">{FAVICON}"
 f"<title>{html.escape(TITLE)}</title><style>{STYLE}</style></head>"
 f"<body><div class=\"wrap\"><a class=\"back\" href=\"./\">← 回戰情室</a>"
 f"<div class=\"card\">{content}</div></div></body></html>")

# 1) 戰情室存檔頁
arc = os.path.join(HERE, "reports", f"{DATE}.html")
io.open(arc, "w", encoding="utf-8").write(PAGE)
# 2) 夜間成果.html（頂部橫幅 default 指向最新）
io.open(os.path.join(HERE, "夜間成果.html"), "w", encoding="utf-8").write(PAGE)
# 3) reports.json：prepend 今天（去重）
rp = os.path.join(HERE, "reports.json")
data = json.load(io.open(rp, encoding="utf-8")) if os.path.exists(rp) else []
data = [r for r in data if r.get("date") != DATE]
data.insert(0, {"date": DATE, "title": TITLE, "href": f"reports/{DATE}.html", "summary": SUMMARY})
io.open(rp, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=1))

# 4) 桌面成品 副本
DESK = r"D:\02. 系統資料夾\Desktop\桌面成品"
ts = datetime.datetime.utcnow()+datetime.timedelta(hours=8)
desk_name = f"{ts.strftime('%m%d_%H%M')}-自走成果0622.html"
io.open(os.path.join(DESK, desk_name), "w", encoding="utf-8").write(PAGE)

print("OK")
print("arc:", arc)
print("desk:", os.path.join(DESK, desk_name))
print("reports.json entries:", [r["date"] for r in data])
print("content_chars:", len(content))
