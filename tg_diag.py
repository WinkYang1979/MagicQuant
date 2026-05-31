import os, urllib.request, urllib.parse
from dotenv import load_dotenv
load_dotenv(r'C:\MagicQuant\.env')

token = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('TG_BOT_TOKEN') or os.getenv('BOT_TOKEN')
chat  = os.getenv('TELEGRAM_CHAT_ID')  or os.getenv('TG_CHAT_ID')   or os.getenv('CHAT_ID')

print('token:', (token[:10] + '...') if token else 'NOT FOUND')
print('chat_id:', chat if chat else 'NOT FOUND')

if not token or not chat:
    print('ERROR: token 或 chat_id 未找到,检查 .env 文件')
else:
    url  = f'https://api.telegram.org/bot{token}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': chat, 'text': 'MagicQuant TG 诊断测试'}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
        print('✅ 发送成功')
    except Exception as e:
        print(f'❌ 发送失败: {e}')
