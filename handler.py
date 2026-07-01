import json
import os
import time
import boto3
import requests

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

# --- ENVIRONMENT VARIABLES ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE')
S3_BUCKET = os.environ.get('S3_BUCKET')

# --- GLOBAL URL ---
URL = f"https://api.telegram.org/bot{TOKEN}/"

# --- HELPER FUNCTIONS ---
def send_message(chat_id, text):
    requests.post(URL + "sendMessage", json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}, timeout=5)

def get_crypto_price(coin):
    try:
        r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin.lower()}&vs_currencies=usd", timeout=5)
        return r.json().get(coin.lower(), {}).get('usd')
    except:
        return None

def handle_s3_upload(file_id, user_id, file_name):
    file_info = requests.get(URL + f"getFile?file_id={file_id}", timeout=5).json()
    file_path = file_info['result']['file_path']
    file_data = requests.get(f"https://api.telegram.org/file/bot{TOKEN}/{file_path}", timeout=10).content
    s3_key = f"{user_id}/{file_name}"
    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=file_data)
    return s3_key


# --- MAIN BRAIN ---
def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        if 'message' not in body:
            return {"statusCode": 200, "body": "No message"}
            
        message = body['message']
        chat_id = message['chat']['id']
        user_id = str(message['from']['id'])
        
        # --- FILE UPLOAD INTERCEPTOR ---
        if 'document' in message or 'photo' in message:
            file_id = message['photo'][-1]['file_id'] if 'photo' in message else message['document']['file_id']
            file_name = f"upload_{int(time.time())}.jpg" if 'photo' in message else message['document']['file_name']
            
            try:
                s3_key = handle_s3_upload(file_id, user_id, file_name)
                send_message(chat_id, f"✅ File secured in Vault.\nUse `pull` to fetch your uploads.\nS3 Path: `{s3_key}`")
                print(f"SUCCESS: User {user_id} uploaded file {file_name} to S3.")
            except Exception as e:
                send_message(chat_id, f"❌ Upload failed: {str(e)}")
                print(f"ERROR: S3 Upload failed for user {user_id} - {str(e)}")
            return {"statusCode": 200}

        # --- TEXT COMMAND ROUTING ---
        text = message.get('text', '').strip()
        parts = text.split()
        command = parts[0].lower() if parts else ""
        
        if command in ["start", "help"]:
            help_text = (
                "🏦 **Crypto Portfolio**\n\n"
                "`hello` - Check system status\n"
                "`price <coin>` - Live coin price\n"
                "`hold` - Download portfolio from database\n"
                "`portfolio` - Full value & coin breakdown\n"
                "`save <coin> <amt>` - Add to your bag\n"
                "`pull` - Download your S3 uploaded files\n"
                "`weather <city>` - Get local weather\n"
                "`reset` - Clear your portfolio database\n"
                "`crash` - Test system alerts"
            )
            send_message(chat_id, help_text)

        elif command == "hello":
            send_message(chat_id, "Hello! I'm alive and tracking your gains. 🚀")

        elif command == "price" and len(parts) > 1:
            coin = parts[1].lower()
            price = get_crypto_price(coin)
            msg = f"📈 **{coin.upper()}**: ${price}" if price else "❌ Coin not found."
            send_message(chat_id, msg)

        elif command == "weather" and len(parts) > 1:
            city = " ".join(parts[1:])
            try:
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
                geo_res = requests.get(geo_url, timeout=5).json()
                
                if 'results' not in geo_res:
                    send_message(chat_id, f"❌ Could not find city: {city.title()}")
                else:
                    lat = geo_res['results'][0]['latitude']
                    lon = geo_res['results'][0]['longitude']
                    real_name = geo_res['results'][0]['name']
                    
                    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                    w_res = requests.get(weather_url, timeout=5).json()
                    
                    temp = w_res['current_weather']['temperature']
                    wind = w_res['current_weather']['windspeed']
                    
                    send_message(chat_id, f"🌤 **{real_name} Live Weather:**\n🌡 Temp: {temp}°C\n💨 Wind: {wind} km/h")
            except Exception as e:
                send_message(chat_id, "❌ Weather API temporarily down.")
                print(f"WARNING: Weather API failed for city {city} - {str(e)}")

        elif command == "hold":
            table = dynamodb.Table(DYNAMODB_TABLE)
            response = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id))
            items = response.get('Items', [])
            if not items:
                send_message(chat_id, "📭 Nothing in your 'hold' list.")
            else:
                reply = "💎 **Current Holdings (DB):**\n"
                for i in items:
                    reply += f"- {i['coin'].upper()}: {i['amount']}\n"
                send_message(chat_id, reply)

        elif command == "portfolio":
            table = dynamodb.Table(DYNAMODB_TABLE)
            items = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id)).get('Items', [])
            
            if not items:
                send_message(chat_id, "Your portfolio is empty. Use `save` first!")
            else:
                total_val = 0
                reply = "💼 **Portfolio Detailed Breakdown:**\n"
                for i in items:
                    coin = i['coin']
                    amt = float(i['amount'])
                    price = get_crypto_price(coin) or 0
                    value = amt * price
                    total_val += value
                    reply += f"• **{coin.upper()}**: {amt} @ ${price:.2f} = *${value:.2f}*\n"
                
                reply += f"\n💰 **Total Portfolio Value: ${total_val:.2f}**"
                send_message(chat_id, reply)

        elif command == "save" and len(parts) > 2:
            coin = parts[1].lower()
            try:
                add_amount = float(parts[2])
                table = dynamodb.Table(DYNAMODB_TABLE)
                
                response = table.get_item(Key={'user_id': user_id, 'coin': coin})
                
                if 'Item' in response:
                    old_amount = float(response['Item']['amount'])
                    new_total = old_amount + add_amount
                else:
                    new_total = add_amount
                
                table.put_item(Item={'user_id': user_id, 'coin': coin, 'amount': str(new_total)})
                send_message(chat_id, f"💾 Added {add_amount} {coin.upper()}!\n💰 **New Total:** {new_total} {coin.upper()}")
                print(f"INFO: User {user_id} updated {coin} balance to {new_total}")
            
            except ValueError:
                send_message(chat_id, "❌ Invalid number. Try again like this: `save bitcoin 1.25`")

        elif command == "pull":
            if len(parts) == 1:
                response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"{user_id}/")
                files = response.get('Contents', [])
                if not files:
                    send_message(chat_id, "📂 No uploaded files found in S3.")
                else:
                    reply = "📥 **Your S3 Uploads (send `pull <filename>` to download):**\n"
                    for f in files:
                        reply += f"- `{f['Key'].split('/')[-1]}`\n"
                    send_message(chat_id, reply)
            else:
                file_name = parts[1]
                s3_key = f"{user_id}/{file_name}"
                try:
                    s3_object = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
                    file_content = s3_object['Body'].read()
                    
                    url = f"{URL}sendDocument"
                    files = {'document': (file_name, file_content)}
                    requests.post(url, data={'chat_id': chat_id}, files=files, timeout=15)
                    print(f"SUCCESS: User {user_id} pulled file {file_name} from S3.")
                except Exception as e:
                    send_message(chat_id, f"❌ Could not download file: {str(e)}")
                    print(f"ERROR: S3 Pull failed for user {user_id} - {str(e)}")

        elif command == "reset":
            table = dynamodb.Table(DYNAMODB_TABLE)
            response = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id))
            items = response.get('Items', [])
            
            if not items:
                send_message(chat_id, "📭 Session reset. Your portfolio was already empty.")
            else:
                for i in items:
                    table.delete_item(Key={'user_id': user_id, 'coin': i['coin']})
                send_message(chat_id, "🧹 Session reset! Your portfolio database has been wiped clean.")
            print(f"WARNING: User {user_id} triggered a full database reset.")

        elif command == "crash":
            print(f"CRITICAL: User {user_id} intentionally triggered a system crash.")
            raise ValueError("Intentional crash triggered!")

        else:
            print(f"CLOUDWATCH ALERT: Unknown command '{text}' entered by user {user_id}.")
            send_message(chat_id, "🤖 I don't recognize that command. Type `help` to see the menu.")

        return {"statusCode": 200, "body": "Success"}

    except Exception as e:
        print(f"SYSTEM FAULT CAUGHT: {str(e)}")
        if 'chat_id' in locals():
            send_message(chat_id, "⚠️ System Error logged to CloudWatch.")
        
        # We MUST return 200 so Telegram stops retrying the message!
        return {"statusCode": 200, "body": "Success"}