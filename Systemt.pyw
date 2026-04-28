
import discord
from discord.ext import commands
import os
import json
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

if not os.path.exists(CONFIG_FILE):
    print(f"Config not found: {CONFIG_FILE}")
    sys.exit(1)

with open(CONFIG_FILE, 'r') as f:
    cfg = json.load(f)

TOKEN = cfg.get("token")
PREFIX = cfg.get("command_prefix", "!")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    print(f"Working directory: {os.getcwd()}")
    print(f"Script directory: {SCRIPT_DIR}")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

bot.run(TOKEN)
