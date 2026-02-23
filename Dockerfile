FROM python:3.9.13-bullseye

# タイムゾーン
RUN apt update; apt -y install tzdata && \
cp /usr/share/zoneinfo/Asia/Tokyo /etc/localtime

RUN apt update
RUN apt -yV upgrade

# poppler (PDF処理用)
RUN apt install -y poppler-utils poppler-data

# libreoffice (オフィスファイル変換用)
RUN apt install -y libgl1-mesa-dev
RUN apt install -y libreoffice libreoffice-l10n-ja libreoffice-dmaths libreoffice-ogltrans libreoffice-writer2xhtml libreoffice-help-ja

# 日本語用のフォント (文字化け対策)
RUN wget https://moji.or.jp/wp-content/ipafont/IPAexfont/IPAexfont00301.zip
RUN unzip IPAexfont00301.zip
RUN mkdir -p /usr/share/fonts/ipa
RUN cp IPAexfont00301/*.ttf /usr/share/fonts/ipa

# フォントを更新
RUN fc-cache -fv

RUN pip install -U pip==23.0.1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# PlaywrightのChromiumをインストール（依存ライブラリ含む）
RUN playwright install --with-deps chromium

# ソースコードをコンテナ内にコピー
COPY . .

CMD ["python", "main.py"]
