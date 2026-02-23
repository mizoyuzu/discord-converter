# 外部モジュール
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import io
import os
import pdf2image

# 内部モジュール
from mylib.PDFConverter import PDFConverter

class FileViewer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supported_extensions = [
            "application/pdf",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ]
        # コンテキストメニュー（メッセージ右クリック→アプリ）を登録
        self.ctx_menu = app_commands.ContextMenu(
            name='ファイルを画像化',
            callback=self.convert_message_files,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def convert_attachment(self, attachment) -> list:
        """添付ファイルを画像リストに変換する共通処理"""
        loop = asyncio.get_running_loop()
        images = []
        
        # PDFの場合
        if attachment.content_type == "application/pdf":
            pdf_io = io.BytesIO()
            await attachment.save(pdf_io)
            images = await loop.run_in_executor(
                None, pdf2image.convert_from_bytes, pdf_io.read()
            )
        
        # Officeファイルの場合
        elif attachment.content_type in self.supported_extensions:
            await attachment.save(attachment.filename)
            # カレントディレクトリに一時保存して変換
            converter = PDFConverter(attachment.filename, ".")
            await loop.run_in_executor(None, converter.start)
            
            # 変換後のPDFを画像化
            pdf_filename = attachment.filename.rsplit(".", 1)[0] + ".pdf"
            
            try:
                images = await loop.run_in_executor(
                    None,
                    pdf2image.convert_from_path,
                    pdf_filename,
                )
            except Exception as e:
                print(f"変換エラー: {e}")
            
            # お掃除
            if os.path.exists(attachment.filename):
                os.remove(attachment.filename)
            if os.path.exists(pdf_filename):
                os.remove(pdf_filename)
        
        return images

    async def send_images_to_channel(self, channel, attachment, images):
        """画像をチャンネル/スレッドに送信する共通処理"""
        if not images:
            await channel.send(f"{attachment.filename} の変換に失敗しました。")
            return
        
        # 画像を送信（10枚ずつ）
        await channel.send(
            embed=discord.Embed(
                title=attachment.filename, color=discord.Color.blue()
            )
        )
        
        # 10枚区切りで送信
        chunked_images = [images[i : i + 10] for i in range(0, len(images), 10)]
        
        total_count = 1
        for chunk in chunked_images:
            files = []
            for img in chunk:
                fileio = io.BytesIO()
                img.save(fileio, format="jpeg")
                fileio.seek(0)
                files.append(discord.File(fileio, filename=f"image_{total_count}.jpg"))
                total_count += 1
            
            await channel.send(
                content=f"{total_count - len(files)} ~ {total_count - 1}ページ", 
                files=files
            )

    async def get_or_create_thread(self, message, name):
        """スレッドを取得または作成する。既にあればそれを返す"""
        # 既にスレッドがある場合はそれを使う
        # hasattrでチェック（discord.pyバージョン互換性のため）
        existing_thread = getattr(message, 'thread', None)
        if existing_thread:
            return existing_thread
        
        # スレッドを作成
        try:
            thread = await message.create_thread(name=name[:100])  # 名前は100文字まで
            return thread
        except discord.HTTPException as e:
            # スレッド作成に失敗した場合はNoneを返す
            print(f"スレッド作成エラー: {e}")
            return None
        except AttributeError as e:
            # create_threadが使えない場合
            print(f"スレッド作成未対応: {e}")
            return None

    @commands.Cog.listener()
    async def on_message(self, message):
        """メッセージ監視：添付ファイルがあれば自動変換"""
        if message.author.bot:
            return
        if len(message.attachments) == 0:
            return
        
        # テキストチャンネルのみ対応（スレッドやDMは除外）
        if message.channel.type != discord.ChannelType.text:
            return
        
        # 対応している拡張子かチェック
        attachments = [
            attachment
            for attachment in message.attachments
            if attachment.content_type in self.supported_extensions
        ]
        if len(attachments) == 0:
            return
        
        print(f"ファイル検出: {len(attachments)}個 - {[a.filename for a in attachments]}")
        
        # スレッドを取得または作成
        try:
            thread = await self.get_or_create_thread(message, attachments[0].filename)
        except Exception as e:
            print(f"スレッド取得/作成中に例外: {e}")
            # スレッド作成に失敗した場合は元のチャンネルに送信
            thread = message.channel
        
        if not thread:
            # スレッド作成に失敗した場合は元のチャンネルに送信
            print("スレッド作成失敗、元のチャンネルに送信します")
            thread = message.channel
        
        for attachment in attachments:
            try:
                images = await self.convert_attachment(attachment)
                await self.send_images_to_channel(thread, attachment, images)
            except Exception as e:
                print(f"変換エラー ({attachment.filename}): {e}")
                await thread.send(f"{attachment.filename} の変換中にエラーが発生しました: {e}")

    # ==============================
    # スラッシュコマンド: /convert
    # ==============================
    @app_commands.command(name="convert", description="添付ファイルを画像に変換します")
    @app_commands.describe(file="変換するファイル（PDF, Excel, Word, PowerPoint）")
    async def convert_command(self, interaction: discord.Interaction, file: discord.Attachment):
        """スラッシュコマンドでファイルを変換"""
        if file.content_type not in self.supported_extensions:
            await interaction.response.send_message(
                f"このファイル形式には対応していません: {file.content_type}\n"
                "対応形式: PDF, Excel (.xls, .xlsx), Word (.doc, .docx), PowerPoint (.ppt, .pptx)",
                ephemeral=True
            )
            return
        
        # まず応答を返す（3秒以内に応答しないとタイムアウトする）
        await interaction.response.send_message(f"**{file.filename}** を変換中...")
        
        try:
            # 変換処理
            images = await self.convert_attachment(file)
            
            if not images:
                await interaction.edit_original_response(content=f"**{file.filename}** の変換に失敗しました。")
                return
            
            # スレッドを作らずに直接チャンネルに送信
            await self.send_images_to_channel(interaction.channel, file, images)
            await interaction.edit_original_response(content=f"**{file.filename}** の変換が完了しました。")
                
        except Exception as e:
            print(f"変換エラー: {e}")
            await interaction.edit_original_response(content=f"エラーが発生しました: {e}")

    # ==============================
    # コンテキストメニュー: メッセージ右クリック→アプリ→「ファイルを画像化」
    # ==============================
    async def convert_message_files(self, interaction: discord.Interaction, message: discord.Message):
        """メッセージコンテキストメニューからファイルを変換"""
        print(f"App呼び出し: message.id={message.id}")
        
        # 添付ファイルを直接取得（属性アクセスを避ける）
        try:
            msg_attachments = list(message.attachments)
            print(f"App: attachments = {len(msg_attachments)}")
        except Exception as e:
            print(f"App: attachments取得エラー: {e}")
            await interaction.response.send_message(
                f"メッセージの取得に失敗しました: {e}",
                ephemeral=True
            )
            return
        
        if len(msg_attachments) == 0:
            await interaction.response.send_message(
                "このメッセージには添付ファイルがありません。",
                ephemeral=True
            )
            return
        
        # 対応している拡張子かチェック
        attachments = []
        for attachment in msg_attachments:
            ct = getattr(attachment, 'content_type', None)
            print(f"App: ファイル {attachment.filename}, content_type={ct}")
            if ct in self.supported_extensions:
                attachments.append(attachment)
        
        if len(attachments) == 0:
            await interaction.response.send_message(
                "このメッセージには対応しているファイルがありません。\n"
                "対応形式: PDF, Excel (.xls, .xlsx), Word (.doc, .docx), PowerPoint (.ppt, .pptx)",
                ephemeral=True
            )
            return
        
        # まず応答を返す（3秒以内に応答しないとタイムアウトする）
        await interaction.response.send_message(
            f"{len(attachments)}個のファイルを変換中...",
            ephemeral=True
        )
        
        try:
            # Appからの場合は interaction.channel を使用（スレッドは作らない）
            target_channel = interaction.channel
            print(f"App: 送信先チャンネル = {target_channel}")
            
            for attachment in attachments:
                print(f"App: 変換開始 - {attachment.filename}")
                images = await self.convert_attachment(attachment)
                print(f"App: 変換完了 - {len(images)}ページ")
                await self.send_images_to_channel(target_channel, attachment, images)
                print(f"App: 送信完了 - {attachment.filename}")
            
            await interaction.edit_original_response(
                content=f"{len(attachments)}個のファイルの変換が完了しました。"
            )
            
        except Exception as e:
            import traceback
            print(f"App変換エラー: {e}")
            traceback.print_exc()
            await interaction.edit_original_response(
                content=f"エラーが発生しました: {e}"
            )


async def setup(bot):
    await bot.add_cog(FileViewer(bot))
