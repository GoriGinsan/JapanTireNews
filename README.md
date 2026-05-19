# JapanTireNews

タイヤメーカー向けのマーケティングニュース監視ツールです。競合メーカーのプレスリリースとニュースRSSを収集し、乗用車・SUV・トラック/バス用タイヤ、新車装着、価格改定、新型車などの関連ニュースだけをMicrosoft Teamsへ通知します。

## 初期セットアップ

```powershell
cd C:\path\to\JapanTireNews
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` を開き、`TEAMS_WEBHOOK_URL` にPower Automate / TeamsのWebhook URLを設定してください。`.env` はGit管理から除外されています。

## 手動実行

通知せずに収集結果だけ確認します。

```powershell
.\.venv\Scripts\python.exe -m japan_tire_news --dry-run --force
```

Teamsへ投稿します。9:00-18:00以外は何もしません。

```powershell
.\.venv\Scripts\python.exe -m japan_tire_news
```

## Windowsタスク登録

9:00から18:00まで1時間おきに実行します。18:00も含みます。土日祝日はPython側で実行を停止します。

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install_windows_task.ps1
```

## サブPCで動かす場合

サブPCでは以下の流れでセットアップしてください。

```powershell
git clone https://github.com/GoriGinsan/JapanTireNews.git
cd JapanTireNews
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` にTeams Webhook URLを設定したあと、以下で動作確認します。

```powershell
.\.venv\Scripts\python.exe -m japan_tire_news --dry-run --force
```

問題なければWindowsタスクを登録します。

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install_windows_task.ps1
```

メインPCとサブPCの両方でタスクを有効にすると二重通知になる可能性があります。サブPCだけで運用する場合は、メインPC側の `JapanTireNewsHourly` タスクを無効化してください。

## 通知ルール

- 該当ニュースがない場合は通知しません。
- 一度通知したURLはSQLiteに保存し、再通知しません。
- SQLiteの保存期間は180日です。
- 通知に至らなかった候補は `logs/rejected_news.csv` に残します。

## 重要度

- A: 競合新製品、価格改定、新車装着、トラック/バス用タイヤなど、すぐ見るべき情報
- B: 新型車、技術紹介、季節商材など、市場理解に有用な情報
- C: 展示会、軽いキャンペーン、地域限定など、参考情報

## 監視対象

公式プレスリリース:

- ブリヂストン
- ミシュラン
- グッドイヤー
- TOYO TIRE
- DUNLOP
- コンチネンタル
- ピレリ
- 横浜タイヤ

ニュースRSS:

- Google News タイヤ
- Google News 新型車
- PR TIMES タイヤ
- PR TIMES 新型車

InstagramとXは、認証や動的描画の影響で安定取得が難しいためMVPでは無効化しています。必要な場合は公式APIまたは専用の監視サービス連携を追加してください。
