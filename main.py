import requests
import google.generativeai as genai
import json
import os
from datetime import datetime
from colorama import Fore, Style, init

# Initialize Colorama for colored terminal output
init(autoreset=True)

# HARDCODED CONFIG
WEBHOOK_URL = "https://discord.com/api/webhooks/1342534329431232512/lipQxHkCX2OwF6sUgdkkms9_ti7SKy7rbr9qlOq_H4WmDOi2E2q4gSOgGgERfHMzX-5s"
DEFAULT_GEMINI_API_KEY = "AIzaSyDFVAlc48thzOn3Uv7ymHDCflJD12-NIVo"
REQUESTS_LOG_FILE = "requests_log.json"

# Prompt user for token
TOKEN = input(Fore.YELLOW + "[?] Enter your Discord token: ").strip()

# Headers for Discord API requests
HEADERS = {
    "Authorization": TOKEN,
    "Content-Type": "application/json"
}

# Load or create the request log
def load_requests_log():
    if os.path.exists(REQUESTS_LOG_FILE):
        with open(REQUESTS_LOG_FILE, "r") as file:
            try:
                return json.load(file)
            except json.JSONDecodeError:
                return {}
    return {}

# Save request log
def save_requests_log(log):
    with open(REQUESTS_LOG_FILE, "w") as file:
        json.dump(log, file)

# Check request limit
def check_request_limit():
    today = datetime.now().strftime("%Y-%m-%d")
    log = load_requests_log()
    
    if today not in log:
        log[today] = 0  # Reset count for new day
    
    if log[today] >= 10:
        print(Fore.RED + "🚨 Due to Rate Limits, we only allow 10 requests per day.")
        print(Fore.YELLOW + "🔑 To avoid these limits, you may use your own Google Gemini API key.")
        print(Fore.CYAN + "Get one at: https://aistudio.google.com/apikey (Requires an 18+ account)")
        
        choice = input("Would you like to use your own API key? (yes/no): ").strip().lower()
        if choice == "yes":
            user_api_key = input("Enter your Google Gemini API Key: ").strip()
            if user_api_key:
                return user_api_key  # Use user's key
        
        print(Fore.RED + "❌ Request denied. Try again tomorrow.")
        return None  # Deny request if user refuses
    
    log[today] += 1
    save_requests_log(log)
    return DEFAULT_GEMINI_API_KEY  # Use default key if under limit

# Configure Gemini AI
def configure_gemini():
    api_key = check_request_limit()
    if not api_key:
        return None  # Stop execution if limit reached
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash")

# Get user servers
def get_user_servers():
    response = requests.get("https://discord.com/api/v9/users/@me/guilds", headers=HEADERS)
    if response.status_code != 200:
        print(Fore.RED + "❌ Failed to fetch servers! Invalid token?")
        return []
    
    return response.json()

# Get server channels
def get_server_channels(server_id):
    response = requests.get(f"https://discord.com/api/v9/guilds/{server_id}/channels", headers=HEADERS)
    if response.status_code != 200:
        print(Fore.RED + "❌ Failed to fetch channels!")
        return []
    
    return response.json()

# Get first 3 messages of a channel
def get_channel_messages(channel_id):
    response = requests.get(f"https://discord.com/api/v9/channels/{channel_id}/messages?limit=3", headers=HEADERS)
    if response.status_code == 200:
        return [msg["content"] for msg in response.json()]
    return []

# Check if server is a scam using Gemini AI
def analyze_server_with_ai(model, server_name, messages, has_chat, has_vouches):
    # Flatten messages (list of lists) into a single list of strings
    flattened_messages = [msg for sublist in messages for msg in sublist]
    
    scam_keywords = ["invite-rewards", "redeem", "crypto giveaway", "free nitro", "airdrop", "claim reward"]
    # (Optional) Example: Check if any message contains a scam keyword
    suspicious = any(
        any(keyword in msg.lower() for keyword in scam_keywords) for msg in flattened_messages
    )
    
    prompt = f"""
    You are an AI that detects scam Discord servers. Answer only with "Yes", "No", or "I don't know."
    
    Server Name: {server_name}
    Chat Channel Exists: {has_chat}
    Vouches Channel Exists: {has_vouches}
    
    First Messages in Channels:
    {flattened_messages}
    
    Rules:
    - If there's no chat or vouches channel, it's suspicious.
    - If scam-related keywords like "invite-rewards", "redeem" appear, it's likely a scam.
    - If uncertain, reply with "I don't know."
    """
    
    response = model.generate_content(prompt).text.strip()
    return response

# Get server invite & owner ID
def get_server_info(server_id):
    # Get server owner ID
    response = requests.get(f"https://discord.com/api/v9/guilds/{server_id}", headers=HEADERS)
    if response.status_code != 200:
        return None, None
    
    server_data = response.json()
    owner_id = server_data.get("owner_id", "Unknown")

    # Get invite link (tries first 10 channels)
    response = requests.get(f"https://discord.com/api/v9/guilds/{server_id}/channels", headers=HEADERS)
    if response.status_code != 200:
        return owner_id, None
    
    channels = response.json()
    for channel in channels[:10]:  # Check first 10 channels for invite perms
        invite_response = requests.post(f"https://discord.com/api/v9/channels/{channel['id']}/invites", 
                                        headers=HEADERS, json={"max_age": 0, "max_uses": 0})
        if invite_response.status_code == 200:
            code = invite_response.json().get('code')
            if code:
                return owner_id, f"https://discord.gg/{code}"

    return owner_id, "No Invite Available"

# Send scam alert to webhook
def send_scam_alert(server_id, server_name, owner_id, invite):
    data = {
        "content": f"🚨 **Scam Server Detected!**\n\n**Server:** {server_name}\n**ID:** {server_id}\n**Owner ID:** {owner_id}\n**Invite:** {invite}"
    }
    requests.post(WEBHOOK_URL, json=data)

# Main function
def main():
    model = configure_gemini()
    if not model:
        return  # Stop execution if API check failed
    
    servers = get_user_servers()
    if not servers:
        print(Fore.RED + "No servers found or invalid token.")
        return

    print(Fore.CYAN + "\nAvailable Servers:")
    for i, server in enumerate(servers, 1):
        print(Fore.YELLOW + f"[{i}] {server['name']}")

    try:
        choice = int(input(Fore.CYAN + "\nEnter the number of the server to analyze: "))
    except ValueError:
        print(Fore.RED + "Invalid input. Exiting.")
        return

    if choice < 1 or choice > len(servers):
        print(Fore.RED + "Invalid selection.")
        return
    
    selected_server = servers[choice - 1]
    server_id, server_name = selected_server["id"], selected_server["name"]

    channels = get_server_channels(server_id)
    # For each channel, get the first 3 messages (this returns a list of lists)
    messages = [get_channel_messages(ch["id"]) for ch in channels if ch["type"] == 0]

    has_chat = any("chat" in ch["name"].lower() for ch in channels)
    has_vouches = any("vouch" in ch["name"].lower() for ch in channels)

    result = analyze_server_with_ai(model, server_name, messages, has_chat, has_vouches)
    print(Fore.CYAN + f"AI Response: {result}")

    if result.strip().lower() == "yes":
        owner_id, invite = get_server_info(server_id)
        send_scam_alert(server_id, server_name, owner_id, invite)
        print(Fore.RED + "🚨 Scam server detected! Details sent to the webhook.")
    elif result.strip().lower() == "no":
        print(Fore.GREEN + "✅ Server appears to be safe.")
    else:
        print(Fore.YELLOW + "⚠️ AI is unsure. Further analysis needed.")

if __name__ == "__main__":
    main()
