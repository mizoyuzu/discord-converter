import discord
from discord.ext import commands
import os
import asyncio
import sys

# バッファリングを無効化してログを即座に表示
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Tokenは環境変数から取得します
TOKEN = os.getenv("DISCORD_TOKEN")

# インテントの設定（メッセージ内容の取得権限が必要）
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    # スラッシュコマンドを同期
    try:
        synced = await bot.tree.sync()
        print(f'スラッシュコマンドを{len(synced)}個同期しました')
    except Exception as e:
        print(f'スラッシュコマンドの同期に失敗: {e}')

async def main():
    async with bot:
        # Extensions を読み込む
        await bot.load_extension("file_viewer")
        await bot.load_extension("web_screenshot")
        await bot.start(TOKEN)

if __name__ == "__main__":
    if not TOKEN:
        print("エラー: 環境変数 DISCORD_TOKEN が設定されていません。")
    else:
        asyncio.run(main())
