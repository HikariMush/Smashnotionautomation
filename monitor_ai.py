import requests
import datetime
import time
import json
import os # ★追加: osライブラリをインポート
import google.generativeai as genai

# --- 設定値 (環境変数から読み込むように変更) ---
# os.environ.get()でGitHub Secretsから値を取得する
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
CONTROL_DB_ID = "2b71bc8521e380868094ec506b41f664"
INBOX_DB_ID = "2b71bc8521e38018a5c3c4b0c6b6627c"
MY_USER_ID = "3d243a83-646b-4bab-81f6-d0c578d5076c"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") # ★変更
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY") # ★変更

# ... (headers, Gemini初期化、各種関数は変更なし)
# ... (main関数も変更なし)

# (以下は前回のコードと同じ内容です)
headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# --- Gemini初期化 ---
if GOOGLE_API_KEY: # 存在チェックを簡略化
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash') 
else:
    model = None
    print("⚠️ 注意: GOOGLE_API_KEYが設定されていません。要約機能はスキップされます。")

# ... (以下、全ての関数とmain()のコードは前回のV3.0と同じ)
# ... (省略)