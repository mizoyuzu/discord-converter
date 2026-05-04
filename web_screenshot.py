# 外部モジュール
import asyncio
import re
import io
import discord
from discord.ext import commands
from discord import app_commands
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from PIL import Image

# URL抽出用の正規表現
URL_PATTERN = re.compile(
    r'https?://[^\s<>"\)\]]+'
)

# ローリングスクリーンショットの分割高さ (px)
SLICE_HEIGHT = 1600
# ビューポート幅
VIEWPORT_WIDTH = 1280
# 最大ページ高さ（無限スクロール対策）
MAX_PAGE_HEIGHT = 16000
# 1メッセージあたりの最大ファイル数（Discord制限）
FILES_PER_MESSAGE = 10
# 代表的なデスクトップChromeのユーザーエージェント
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
EXTRA_HEADERS = {
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}
NAVIGATION_TIMEOUT_MS = 45000
POST_LOAD_WAIT_SEC = 2


class CloudflareBlockedError(RuntimeError):
    """Cloudflareのブロック/エラーページが表示されたことを示す。"""


class WebScreenshot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._playwright = None
        self._browser = None

        # コンテキストメニュー登録
        self.ctx_menu = app_commands.ContextMenu(
            name='ページをスクリーンショット',
            callback=self.screenshot_message_links,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_load(self):
        """Cog読み込み時にPlaywrightブラウザを起動"""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
            ],
            ignore_default_args=['--enable-automation'],
        )
        print("Playwright browser launched")

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        print("Playwright browser closed")

    def extract_urls(self, text: str) -> list[str]:
        """テキストからURLを抽出"""
        if not text:
            return []
        return URL_PATTERN.findall(text)

    async def _wait_for_ready(self, page: "Page"):
        """domcontentloaded後にnetworkidle待機し、長期通信のタイムアウトは無視する。"""
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except (PlaywrightTimeoutError, asyncio.TimeoutError):
            return

    async def _detect_cloudflare_error(self, page: "Page") -> bool:
        """cf-error系DOMやタイトルでCloudflare検知時はTrue、それ以外はFalseを返す。"""
        selectors = [
            "#cf-error-details",
            "#cf-error-footer",
            ".cf-error-details",
            ".cf-error-footer",
        ]
        for selector in selectors:
            if await page.query_selector(selector):
                return True
        title = (await page.title()).lower()
        return "cloudflare" in title and (
            "error" in title or "attention" in title or "just a moment" in title
        )

    async def take_rolling_screenshot(self, url: str) -> list[bytes]:
        """
        URLのローリングスクリーンショットを撮影。
        ページ全体をSLICE_HEIGHTごとに分割してJPEG画像リストとして返す。
        """
        context = await self._browser.new_context(
            viewport={'width': VIEWPORT_WIDTH, 'height': 900},
            device_scale_factor=1.5,
            locale='ja-JP',
            timezone_id='Asia/Tokyo',
            user_agent=USER_AGENT,
            extra_http_headers=EXTRA_HEADERS,
            java_script_enabled=True,
            ignore_https_errors=True,
        )
        page = await context.new_page()

        try:
            # Cloudflare等のボット判定を避けて正しい描画を取得するための対策
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            # ページ読み込み（最大30秒）
            await page.goto(url, wait_until='domcontentloaded', timeout=NAVIGATION_TIMEOUT_MS)
            await self._wait_for_ready(page)
            await asyncio.sleep(POST_LOAD_WAIT_SEC)

            if await self._detect_cloudflare_error(page):
                raise CloudflareBlockedError(
                    "Cloudflareのエラーページが表示されました。URLがブロックされている可能性があります。"
                )

            # ページ全体の高さを取得
            full_height = await page.evaluate(
                'Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)'
            )
            full_height = min(full_height, MAX_PAGE_HEIGHT)

            # ページ幅も取得
            full_width = await page.evaluate(
                'Math.max(document.body.scrollWidth, document.documentElement.scrollWidth)'
            )
            # ビューポート幅に収まるように、最低でもVIEWPORT_WIDTHは確保
            full_width = max(full_width, VIEWPORT_WIDTH)

            # 全ページスクリーンショットを撮影
            full_screenshot = await page.screenshot(
                full_page=True,
                type='png',
            )

            # PILで分割処理
            img = Image.open(io.BytesIO(full_screenshot))
            img_width, img_height = img.size

            # デバイススケールを考慮した分割高さ
            scale = img_height / full_height if full_height > 0 else 1
            slice_px = int(SLICE_HEIGHT * scale)

            slices = []
            y = 0
            while y < img_height:
                bottom = min(y + slice_px, img_height)
                cropped = img.crop((0, y, img_width, bottom))

                buf = io.BytesIO()
                cropped.save(buf, format='JPEG', quality=85)
                slices.append(buf.getvalue())
                y = bottom

            return slices

        except Exception as e:
            print(f"スクリーンショットエラー ({url}): {e}")
            raise
        finally:
            await page.close()
            await context.close()

    async def screenshot_message_links(
        self, interaction: discord.Interaction, message: discord.Message
    ):
        """メッセージコンテキストメニューからURLをスクリーンショット化"""
        # メッセージ本文 + Embedの各種テキストからURLを抽出
        text_parts = [message.content or '']
        for embed in message.embeds:
            if embed.url:
                text_parts.append(embed.url)
            if embed.description:
                text_parts.append(embed.description)
        full_text = ' '.join(text_parts)
        urls = self.extract_urls(full_text)

        # 重複除去（順序保持）
        seen = set()
        unique_urls = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)
        urls = unique_urls

        if not urls:
            await interaction.response.send_message(
                'このメッセージにはURLが含まれていません。',
                ephemeral=True,
            )
            return

        # ephemeral=False で応答（全員に見える）
        await interaction.response.send_message(
            f'{len(urls)}個のURLをスクリーンショット中...'
        )

        for url in urls:
            try:
                slices = await self.take_rolling_screenshot(url)
                total = len(slices)

                # タイトルEmbed
                embed = discord.Embed(
                    title=url,
                    url=url,
                    description=f'{total}枚に分割',
                    color=discord.Color.green(),
                )
                await interaction.channel.send(embed=embed)

                # 10枚ずつ送信
                for i in range(0, total, FILES_PER_MESSAGE):
                    chunk = slices[i:i + FILES_PER_MESSAGE]
                    files = [
                        discord.File(
                            io.BytesIO(data),
                            filename=f'page_{i + j + 1}.jpg',
                        )
                        for j, data in enumerate(chunk)
                    ]
                    start_num = i + 1
                    end_num = i + len(chunk)
                    await interaction.channel.send(
                        content=f'{start_num} ~ {end_num} / {total}',
                        files=files,
                    )

            except Exception as e:
                await interaction.channel.send(f'{url} のスクリーンショットに失敗しました: {e}')

        await interaction.edit_original_response(
            content=f'{len(urls)}個のURLのスクリーンショットが完了しました。'
        )


async def setup(bot):
    await bot.add_cog(WebScreenshot(bot))
