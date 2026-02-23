import glob
import logging
import os
import subprocess
import shutil

default_user_profile = os.environ["HOME"] + "/.config/libreoffice/4/user"

class PDFConverter:
    def __init__(
        self,
        file_in: str,
        file_out: str,
        timeout_sec: int = 30,
        user_profile: str = None,
    ):
        self.file_in = file_in  # 変換対象のOffice文書
        self.file_out = file_out  # 変換されたPDF文書の格納ディレクトリ
        self.timeout_sec = timeout_sec  # 変換のタイムアウトリミット
        # デフォルトのユーザプロファイルから、新しいユーザプロファイルを作成
        self.user_profile = user_profile
        if self.user_profile:
            if not os.path.exists(self.user_profile):
                shutil.copytree(default_user_profile, self.user_profile)

    def __enter__(self):
        return self

    def __exit__(self):
        self.stop()

    def start(self):
        args = [
            "libreoffice",
            "--headless",
            "--language=ja",
            '--infilter=",,64"',
            "--convert-to",
            "pdf",
            self.file_in,
            "--outdir",
            self.file_out,
        ]
        if self.user_profile:
            args.append("-env:UserInstallation=file://%s" % self.user_profile)
        stdout_str = ""
        stderr_str = ""
        rc = 0
        try:
            # PDF変換実行、タイムアウトになったらsofficeプロセスを終了させる
            ret = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=self.timeout_sec,
                check=True,
                text=True,
            )
            rc = ret.returncode
            stdout_str = ret.stdout
            stderr_str = ret.stderr
        except subprocess.CalledProcessError as cpe:
            rc = -1
            stdout_str = cpe.stdout
            stderr_str = cpe.stderr
        except subprocess.TimeoutExpired as te:
            rc = -2
            stdout_str = te.stdout
            stderr_str = te.stderr
        finally:
            if stdout_str:
                logging.info(stdout_str)
            if stderr_str:
                logging.info(stderr_str)
            self.stop()
            return rc

    def stop(self):
        # タイムアウト時に生成される一時ファイルを削除
        tmp_files = self.file_out + "/*.tmp"
        for f in glob.glob(tmp_files):
            os.remove(f)
        logging.info("soffice finished")
