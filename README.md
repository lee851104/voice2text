# 會議摘要整理

把 NotebookLM 或其他工具產生的**文字摘要**，整理成固定格式的 **Word 會議紀錄**。

Windows 桌面程式，介面採繁體中文。一般整理、編輯與匯出都在本機完成，**不需要金鑰**；OpenAI 文字改寫是選用功能。

## 怎麼使用

1. **貼上摘要**：貼上完整文字，按「下一步」，全部段落會先放入右側文件。
2. **調整並匯出**：左側勾選要保留的項目，右側直接編輯內容，完成後按「匯出 Word」。

也可以：

- 拖曳整段文字，調整順序或移到其他標題下。
- 使用「全選／全不選」或中間的箭頭按鈕加入內容。
- 手動新增空白段落；左側「刪除」可移除手動新增的項目，未勾選也可刪除。
- 儲存 `.summary.json` 專案，下次繼續編輯。

會議時間、地點、主持人等基本資料預設留空，可自行填寫。本程式處理文字摘要，**不接收錄音檔**。

## 直接執行 Windows 版

若此儲存庫已發布 Windows 分享包，請到 **Releases（版本發布）**下載 `MeetingNotes-Windows-x64.zip`。

解壓整包後開啟 `MeetingNotes.exe`，並保留旁邊的 `_internal` 資料夾。**不必安裝 Python 或 Word 就能產生文件**；開啟與編輯輸出的文件需要相容文書軟體。

支援 Windows 10／11 64 位元。詳細操作見 [使用說明](使用說明.txt)。

## 從原始碼執行

先安裝 **Python 3.12（64 位元）**，在專案資料夾開啟 PowerShell，依序執行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## 選用 OpenAI 改寫

按左下方「OpenAI 金鑰設定（選用）」，輸入自己的應用程式介面金鑰（Application Programming Interface Key，API Key），再按「整理右側文字」。

- 預設模型：`gpt-6-luna`，可自行修改。
- 只有啟動此功能才會將已收錄的段落文字傳送至 OpenAI，費用由你的帳戶支付。
- 金鑰只保留在本次程式記憶體，不寫入專案檔。
- 自動改寫後仍應核對內容；程式無法驗證原始錄音或摘要是否正確。

## 檔案放在哪裡

| 路徑 | 用途 |
| --- | --- |
| `app.py` | 程式入口 |
| `meeting_notes/` | 程式功能與介面 |
| `assets/department-template.docx` | Word 固定格式範本 |
| `tests/` | 自動化測試 |
| `scripts/` | 打包工具 |
| `docs/` | 開發與上傳說明 |

[開發、測試與打包](docs/development.md) · [如何上傳 GitHub](docs/github-upload.md)

**請勿上傳金鑰、個人會議專案或匯出文件。** `.gitignore` 已排除這些常見檔案，以及虛擬環境、測試暫存與建置產物；手動拖曳上傳檔案時，仍應使用整理好的原始碼資料夾。

目前範本沿用指定公司的標頭與標誌，並非通用空白範本。公開發布前，請確認適合公開使用，或換成自己的範本。

程式碼採 [MIT 授權](LICENSE.txt)；第三方套件保留各自授權，範本中的標誌不屬於本專案的程式碼授權範圍。
