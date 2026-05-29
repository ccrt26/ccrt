"""一次性脚本：获取飞书应用所在群的 chat_id"""
import json, urllib.request, os

CONFIG_PATH = os.path.expanduser("~/.feishu_bot_tmp.json")
if not os.path.exists(CONFIG_PATH):
    print("❌ 找不到 ~/.feishu_bot_tmp.json，先执行：")
    print('   echo \'{"app_id":"你的ID","app_secret":"你的Secret"}\' > ~/.feishu_bot_tmp.json')
    exit(1)

with open(CONFIG_PATH) as f:
    cfg = json.load(f)

# 1. 获取 access_token
req = urllib.request.Request(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    data=json.dumps({"app_id": cfg["app_id"], "app_secret": cfg["app_secret"]}).encode(),
    headers={"Content-Type": "application/json; charset=utf-8"},
    method="POST",
)
resp = json.loads(urllib.request.urlopen(req).read())
token = resp["tenant_access_token"]

# 2. 拉取群列表
req2 = urllib.request.Request(
    "https://open.feishu.cn/open-apis/im/v1/chats?page_size=20",
    headers={"Authorization": f"Bearer {token}"},
)
data = json.loads(urllib.request.urlopen(req2).read())

print("\n你的群列表：")
print("-" * 60)
for item in data.get("data", {}).get("items", []):
    name = item.get("name", "未命名")
    chat_id = item.get("chat_id", "")
    print(f"  群名: {name}")
    print(f"  群ID: {chat_id}")
    print("-" * 40)
