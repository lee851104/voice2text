# 上傳 GitHub

## 要上傳哪些檔案？

請使用整理好的 `MeetingNotes-source` 原始碼資料夾。裡面有 README、程式碼、範本、測試及打包工具。

**不要把整個開發工作目錄拖上去，也不要只上傳一個原始碼 ZIP。** 將原始碼 ZIP 解壓後，上傳資料夾裡面的檔案，讓 `README.md` 和 `app.py` 位於儲存庫最上層。

`.gitignore` 是提供給 Git 的排除規則，不能代替手動上傳前的檔案選擇。會議資料、`.env` 金鑰檔、`.venv`、`qa`、`outputs`、`build`、`dist` 與 `release` 都不應當作原始碼上傳。

## 使用 Git 上傳

先在 GitHub 建立空的儲存庫，再於原始碼資料夾執行下列指令。網址需換成自己的儲存庫網址。

```powershell
git init
git add .
git status
```

確認清單只有要公開的程式檔案後，再執行：

```powershell
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
git push -u origin main
```

這些步驟由你自行執行；專案整理不會自動建立遠端儲存庫或上傳內容。

## 讓其他人下載程式

原始碼放在儲存庫。可直接執行的 `MeetingNotes-Windows-x64.zip` 與 `SHA256SUMS.txt` 則放在 **GitHub Releases（版本發布）**。

若要同時提供原始碼分享包，也可附上 `MeetingNotes-source.zip`。一般使用者下載 Windows 分享包即可，不需自行安裝 Python。

目前 Word 範本含指定公司的標頭與標誌。公開儲存庫前，請確認適合公開使用；如需通用版，先更換範本並測試匯出。
