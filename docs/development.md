# 開發與打包

目前版本為 2.2.4，主要開發及驗證環境是 Windows x64、Python 3.12。

## 安裝開發環境

在專案根目錄執行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe app.py
```

- `requirements.txt`：執行目前文字摘要介面所需的套件。
- `requirements-dev.txt`：另加測試、打包及舊版錄音回歸測試所需套件。
- `requirements-lock.txt`：已驗證環境的完整套件版本紀錄。

## 測試

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

測試使用本機資料及模擬回應，不需真實金鑰。它們檢查解析、勾選、拖放、編輯、刪除、存讀、Word 匯出及打包排除規則；不代表已驗證真實帳戶的模型權限。

也可輸出合成資料的畫面與 Word 檔：

```powershell
.\.venv\Scripts\python.exe app.py --diagnose "D:\meeting-notes-check"
```

請自行更換輸出位置。這些診斷產物不應加入儲存庫。

## 製作分享包

```powershell
.\.venv\Scripts\python.exe scripts\build_release.py
```

完成後會在 `release/` 產生：

| 檔案 | 用途 |
| --- | --- |
| `MeetingNotes-Windows-x64.zip` | 可直接執行的 Windows 分享包，含授權及原始碼 |
| `MeetingNotes-source.zip` | 原始碼、範本、文件與測試 |
| `SHA256SUMS.txt` | 檔案校驗碼，可用來確認下載完整性 |

只需原始碼時，加上 `--source-only`。打包工具以允許清單選取檔案，不納入錄音、個人專案、金鑰、輸出文件與本機封存資料。

## 程式結構

`app.py` 啟動 `summary_ui.py`，流程為「貼上文字 → 本機解析 → 勾選／拖放／編輯 → 匯出 Word」。OpenAI 改寫為選用步驟。

| 模組 | 職責 |
| --- | --- |
| `summary_models.py` | 段落解析、資料格式與專案存讀 |
| `summary_ui.py` | 兩步驟介面與使用者操作 |
| `summary_transfer.py` | 拖放、左側清單與段落把手 |
| `summary_document_editor.py` | 右側文件的行內編輯 |
| `summary_layout.py` | 預覽與匯出共用的章節和編號 |
| `summary_export.py` | 套用範本並匯出 Word |
| `summary_service.py` | 選用的 OpenAI 改寫與錯誤處理 |
| `summary_diagnostics.py` | 分享包離線診斷 |
| `language.py`、`theme.py` | 繁體中文轉換與介面樣式 |

`meeting_notes/` 仍保留 1.x 的錄音模組（例如 `audio.py`、`service.py`、`ui.py`）及相關回歸測試。目前入口不載入這些模組，Windows 分享版也不提供錄音轉錄功能。

## 資料與範本

- `.summary.json` 保存原文、收錄狀態、順序、編輯內容及基本資料，不保存金鑰；不會背景自動儲存。
- 取消勾選保留原文與修改；手動段落的「刪除」會移除該筆資料。
- Word 範本已清除舊會議內容，但保留原有公司標頭、標誌與版式。替換範本時須保留 `summary_layout.py` 與 `summary_export.py` 使用的標記及結構，並重新驗證匯出。
- 使用 `store=False` 不等同於停用服務端的所有資料保留政策。金鑰由使用者在介面自行輸入，開發時不要把真實金鑰寫入程式碼。
- 關閉、拖放及存檔修改完成後，請保留對應回歸測試，並以乾淨解壓的分享包再次驗證。
