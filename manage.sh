#!/bin/bash

# Discord File Bot 管理スクリプト
CONTAINER_NAME="discord-file-bot"
IMAGE_NAME="discord-file-bot"

show_menu() {
    echo ""
    echo "================================"
    echo "  Discord File Bot 管理メニュー"
    echo "================================"
    echo "  1) 起動 (start)"
    echo "  2) 停止 (stop)"
    echo "  3) 再起動 (restart)"
    echo "  4) ログを表示 (logs)"
    echo "  5) ログをリアルタイム表示 (logs -f)"
    echo "  6) ステータス確認 (status)"
    echo "  7) リビルド & 起動 (rebuild)"
    echo "  8) コンテナに入る (shell)"
    echo "  9) 終了 (exit)"
    echo "================================"
    echo -n "選択してください [1-9]: "
}

do_start() {
    echo "🚀 コンテナを起動中..."
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        docker start $CONTAINER_NAME
    else
        docker run -d --name $CONTAINER_NAME --env-file .env $IMAGE_NAME
    fi
    echo "✅ 起動しました"
}

do_stop() {
    echo "🛑 コンテナを停止中..."
    docker stop $CONTAINER_NAME 2>/dev/null
    echo "✅ 停止しました"
}

do_restart() {
    echo "🔄 コンテナを再起動中..."
    docker restart $CONTAINER_NAME 2>/dev/null || do_start
    echo "✅ 再起動しました"
}

do_logs() {
    echo "📋 最新ログ (最後の50行):"
    docker logs --tail 50 $CONTAINER_NAME
}

do_logs_follow() {
    echo "📋 ログをリアルタイム表示中 (Ctrl+C で終了):"
    docker logs -f --tail 20 $CONTAINER_NAME
}

do_status() {
    echo "📊 ステータス:"
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "✅ 実行中"
        docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    elif docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "⏹️ 停止中"
        docker ps -a --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}"
    else
        echo "❌ コンテナが存在しません"
    fi
}

do_rebuild() {
    echo "🔨 リビルド中..."
    docker stop $CONTAINER_NAME 2>/dev/null
    docker rm $CONTAINER_NAME 2>/dev/null
    docker build -t $IMAGE_NAME .
    if [ $? -eq 0 ]; then
        echo "✅ ビルド完了"
        do_start
    else
        echo "❌ ビルド失敗"
    fi
}

do_shell() {
    echo "🐚 コンテナにシェルで接続中..."
    docker exec -it $CONTAINER_NAME /bin/bash
}

# 引数がある場合は直接実行
if [ $# -gt 0 ]; then
    case "$1" in
        start) do_start ;;
        stop) do_stop ;;
        restart) do_restart ;;
        logs) do_logs ;;
        logs-f) do_logs_follow ;;
        status) do_status ;;
        rebuild) do_rebuild ;;
        shell) do_shell ;;
        *) echo "使用法: $0 {start|stop|restart|logs|logs-f|status|rebuild|shell}" ;;
    esac
    exit 0
fi

# インタラクティブモード
while true; do
    show_menu
    read choice
    case $choice in
        1) do_start ;;
        2) do_stop ;;
        3) do_restart ;;
        4) do_logs ;;
        5) do_logs_follow ;;
        6) do_status ;;
        7) do_rebuild ;;
        8) do_shell ;;
        9) echo "👋 終了します"; exit 0 ;;
        *) echo "❌ 無効な選択です" ;;
    esac
    echo ""
    echo "Enterを押して続行..."
    read
done
