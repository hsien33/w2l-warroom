# 財富煉金術 · 內容戰情室（GitHub Pages 版）

連上去就看最新：即時追蹤數、各產線庫存／預排到幾號、自動化流水線、社群版圖、顧問團。

- `index.html` — 戰情室（開頁讀 `data.json`）。
- `data.json` — 即時資料（追蹤數／D-day／各線庫存）。追蹤數＋D-day 由 GitHub Actions 每 3 小時自動更新；庫存（主集 Reel 排到第幾集等）人工維護（每週排內容時更新）。
- `.github/workflows/refresh.yml` — 每 3 小時抓 IG 即時追蹤數→更新 data.json→commit。
- Secret 需設：`IG_ACCESS_TOKEN`（與 warcard-auto 同一把）。

> 公開 repo（GitHub Pages 免費需公開）。內容僅追蹤數／庫存／產線狀態，無金鑰、無個資；網址不對外宣傳。
> 自動發文系統在另一個 private repo `warcard-auto`。
