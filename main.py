import discord
from discord.ext import commands
import os
import asyncio
import sys
from pathlib import Path

# バッファリングを無効化してログを即座に表示
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def load_local_env(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        os.environ.setdefault(key, value)


load_local_env(Path(__file__).resolve().with_name(".env"))

# Tokenは環境変数から取得します（前後の空白を除去）
TOKEN = (os.getenv("DISCORD_TOKEN") or "").strip()

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
        for ext in ("file_viewer", "web_screenshot"):
            try:
                await bot.load_extension(ext)
                print(f'拡張機能を読み込みました: {ext}')
            except Exception as e:
                print(f'拡張機能の読み込みに失敗しました ({ext}): {e}')
        try:
            await bot.start(TOKEN)
        except discord.LoginFailure:
            print("エラー: Discordトークンが無効です。DISCORD_TOKEN を確認してください。")
            sys.exit(1)

if __name__ == "__main__":
    if not TOKEN:
        print("エラー: 環境変数 DISCORD_TOKEN が設定されていません。")
        sys.exit(1)
    else:
        asyncio.run(main())
