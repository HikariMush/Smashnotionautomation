import requests
import datetime
import time
import json
import os # 環境変数用
import google.generativeai as genai
import sys # ★追加: 出力バッファリング対策用

# --- 設定値 (全て特定済み) ---
NOTION_TOKEN = "ntn_Z74578088671uw1FdW8Xrm770Cvp93rGRwdUjIgJQF1cgx"
CONTROL_DB_ID = "2b71bc8521e380868094ec506b41f664"
INBOX_DB_ID = "2b71bc8521e38018a5c3c4b0c6b6627c"
MY_USER_ID = "3d243a83-646b-4bab-81f6-d0c578d5076c"
# ★Discord WebHook URL (シークレットから読み込む)
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") 
# ★Gemini APIキー (シークレットから読み込む)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY") 

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# --- Gemini初期化 ---
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash') 
else:
    model = None

# === 共通関数 ===
def get_control_list():
    url = f"https://api.notion.com/v1/databases/{CONTROL_DB_ID}/query"
    res = requests.post(url, headers=headers)
    return res.json().get("results", []) if res.status_code == 200 else []

def send_discord_notification(student_name, content_title, summary, page_url):
    """Discord通知 (AI要約付き)"""
    if not DISCORD_WEBHOOK_URL or "discord.com" not in DISCORD_WEBHOOK_URL:
        return 
        
    embed = {
        "title": f"🔔 {student_name} さんが更新しました",
        "description": summary,
        "url": page_url,
        "color": 16750080,
        "fields": [
            {"name": "記事タイトル", "value": content_title, "inline": True},
            {"name": "アクション", "value": "Inboxを確認してください", "inline": True}
        ]
    }
    
    data = {
        "content": f"**新着報告:** {student_name}さんの日報が更新されました。",
        "embeds": [embed]
    }
    requests.post(DISCORD_WEBHOOK_URL, headers={"Content-Type": "application/json"}, data=json.dumps(data))

# === AI要約機能 ===
def get_page_text_content(page_id):
    """ページ内のテキストブロックを取得して結合する"""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    res = requests.get(url, headers=headers)
    if res.status_code != 200: return ""
    
    blocks = res.json().get("results", [])
    full_text = ""
    
    for block in blocks:
        b_type = block["type"]
        text_source = block.get(b_type, {})
        
        if "rich_text" in text_source:
            text_obj = text_source["rich_text"]
        else:
            continue
            
        if text_obj:
            combined_text = "".join([t.get("plain_text", "") for t in text_obj])
            full_text += combined_text + "\n"
                
    return full_text

def summarize_content(text):
    """Geminiを使って要約と感情分析を行う"""
    if not model or not text or len(text) < 10: return "AI要約機能がオフか、テキストが短すぎます。"
    
    prompt = f"""
    以下の生徒のコーチング日報/記録を、コーチが瞬時に把握できるよう処理してください。
    
    【出力フォーマット】
    [感情アイコン] 感情を一言で (例: 🔥やる気、😱SOS、😌順調、🌀悩み)
    ・要約ポイント1
    ・要約ポイント2
    ・要約ポイント3
    
    【対象テキスト】
    {text[:2000]}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"   ⚠️ Gemini Error: {e}")
        return "Gemini APIで要約エラーが発生しました。"

# === 1. 監視＆Inbox追加パート ===
def add_to_inbox(student_name, content_title, content_url, edited_time, page_id):
    # 重複チェック
    check_url = f"https://api.notion.com/v1/databases/{INBOX_DB_ID}/query"
    check_payload = {
        "filter": {
            "and": [
                {"property": "URL", "url": {"equals": content_url}},
                {"property": "Done", "checkbox": {"equals": False}}
            ]
        }
    }
    check_res = requests.post(check_url, headers=headers, json=check_payload)
    if check_res.status_code == 200 and len(check_res.json().get("results", [])) > 0:
        return 

    # --- AI要約の生成 ---
    page_text = get_page_text_content(page_id)
    ai_summary = summarize_content(page_text)
    
    # 新規追加
    url = "https://api.notion.com/v1/pages"
    summary_to_notion = ai_summary if ai_summary else "❌ AI要約エラー：テキスト抽出失敗かAPIエラー"
    
    payload = {
        "parent": { "database_id": INBOX_DB_ID },
        "properties": {
            "名前": { "title": [{"text": {"content": f"{content_title}"}}] },
            "生徒名": { "rich_text": [{"text": {"content": student_name}}] },
            "URL": { "url": content_url },
            "発生日時": { "date": {"start": edited_time} },
            "Done": { "checkbox": False },
            "AI要約": { "rich_text": [{"text": {"content": summary_to_notion[:2000]}}] }
        }
    }
    
    res = requests.post(url, headers=headers, json=payload)
    
    if res.status_code == 200:
        print(f"   📮 Inboxに追加成功: {content_title}")
        send_discord_notification(student_name, content_title, ai_summary, content_url)
    else:
        print(f"   ❌ Inbox追加エラー (Status: {res.status_code})")
        print(f"   詳細: {res.text}")

def uncheck_hikari_confirm(page_id):
    """生徒ページのチェックを外す（未読に戻す）"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    requests.patch(url, headers=headers, json={"properties": {"Hikari確認": { "checkbox": False }}})
    print("   🔄 更新ありのためチェックを外しました")

def check_updates_for_student(student_name, target_db_id, last_check_iso):
    url = f"https://api.notion.com/v1/databases/{target_db_id}/query"
    payload = { "page_size": 5, "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}] }
    
    if last_check_iso:
        payload["filter"] = { "timestamp": "last_edited_time", "last_edited_time": { "after": last_check_iso } }

    try:
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code != 200: return False

        results = res.json().get("results", [])
        found = False
        for page in results:
            if page["last_edited_by"]["id"] == MY_USER_ID: continue
            
            props = page.get("properties", {})
            is_checked = props.get("Hikari確認", {}).get("checkbox", False)
            
            title = "No Title"
            for key, val in props.items():
                if val["type"] == "title" and val["title"]:
                    title = val["title"][0]["plain_text"]
                    break
            
            if is_checked:
                uncheck_hikari_confirm(page["id"])
            
            add_to_inbox(student_name, title, page["url"], page["last_edited_time"], page["id"])
            found = True
            
        return found
    except Exception as e:
        print(f"Error checking {student_name}: {e}")
        return False

def update_last_check(ctrl_page_id):
    url = f"https://api.notion.com/v1/pages/{ctrl_page_id}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    requests.patch(url, headers=headers, json={"properties": { "LastCheck": { "date": { "start": now_iso } } }})

# === 2. Inbox -> 生徒ページへの反映 ===
def process_inbox_done():
    print("\n💌 Inboxの完了分を反映中...")
    url = f"https://api.notion.com/v1/databases/{INBOX_DB_ID}/query"
    payload = { "filter": { "property": "Done", "checkbox": {"equals": True} } }
    
    res = requests.post(url, headers=headers, json=payload)
    done_tasks = res.json().get("results", []) if res.status_code == 200 else []

    for task in done_tasks:
        try:
            inbox_page_id = task["id"]
            target_url = task["properties"].get("URL", {}).get("url")
            task_name = task["properties"].get("名前", {}).get("title", [])[0]["plain_text"]
            
            if target_url:
                page_id_raw = target_url.split("notion.so/")[-1].split("?")[0][-32:]
                target_page_url = f"https://api.notion.com/v1/pages/{page_id_raw}"
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                
                requests.patch(target_page_url, headers=headers, json={
                    "properties": {
                        "Hikari確認": { "checkbox": True },
                        "CheckDate": { "date": {"start": now_iso} }
                    }
                })
                print(f"   ✅ 生徒側もチェックON: {task_name}")

            requests.patch(f"https://api.notion.com/v1/pages/{inbox_page_id}", headers=headers, json={"archived": True})
            
        except: continue

# === 3. 生徒ページ -> Inboxへの反映 ===
def sync_manual_checks_from_students():
    print("\n👀 生徒側で直接チェックされたものを確認中...")
    
    url = f"https://api.notion.com/v1/databases/{INBOX_DB_ID}/query"
    payload = { "filter": { "property": "Done", "checkbox": {"equals": False} } }
    
    res = requests.post(url, headers=headers, json=payload)
    pending_tasks = res.json().get("results", []) if res.status_code == 200 else []
    
    for task in pending_tasks:
        try:
            inbox_page_id = task["id"]
            target_url = task["properties"].get("URL", {}).get("url")
            task_name = task["properties"].get("名前", {}).get("title", [])[0]["plain_text"]
            
            if not target_url: continue
            
            page_id_raw = target_url.split("notion.so/")[-1].split("?")[0][-32:]
            page_url = f"https://api.notion.com/v1/pages/{page_id_raw}"
            
            page_res = requests.get(page_url, headers=headers)
            if page_res.status_code != 200: continue
            
            is_checked = page_res.json().get("properties", {}).get("Hikari確認", {}).get("checkbox", False)
            
            if is_checked:
                print(f"   🗑️ 手動確認を検知 -> Inboxから削除: {task_name}")
                requests.patch(f"https://api.notion.com/v1/pages/{inbox_page_id}", headers=headers, json={"archived": True})
                
        except: continue

def main():
    print(f"=== AI搭載監視システム (完全版): {datetime.datetime.now().strftime('%H:%M:%S')} ===")
    
    students = get_control_list()
    for student in students:
        try:
            ctrl_id = student["id"]
            name = student["properties"]["Name"]["title"][0]["plain_text"]
            target_ids = student["properties"]["TargetID"]["rich_text"]
            if not target_ids: continue
            target_db_id = target_ids[0]["plain_text"]
            
            last_check = student["properties"].get("LastCheck", {}).get("date")
            last_check_iso = last_check["start"] if last_check else None
            
            print(f"Checking {name}...", end=" ")
            if check_updates_for_student(name, target_db_id, last_check_iso):
                print("✨ 新着(AI解析実行)")
            else:
                print("なし")
            
            update_last_check(ctrl_id)
            time.sleep(0.4)
            # ★バッファリング対策: 各チェック後に強制出力
            sys.stdout.flush() 
        except: continue

    process_inbox_done()
    sync_manual_checks_from_students()
    
    print("=== 完了 ===")

if __name__ == "__main__":
    main()
