# 大規模 Discord Bot

複数の機能を備えた本格的な Discord Bot です。モデレーション、エンターテイメント、ユーティリティ機能を搭載し、拡張可能な設計になっています。

## 機能

**すべてのコマンドはスラッシュコマンド（/）で実行します**

### モデレーション・管理機能
- `/kick` - ユーザーをキック
- `/ban` - ユーザーをバン
- `/unban` - バンを解除
- `/timeout` - ユーザーをタイムアウト
- `/untimeout` - タイムアウト解除
- `/warn` - ユーザーに警告
- `/clear` - メッセージを削除
- `/userinfo` - ユーザー情報を表示

### エンターテイメント機能
- `/8ball` - 8ボール占い
- `/rps` - じゃんけん (rock/paper/scissors)
- `/dice` - サイコロを振る
- `/flip` - コインを投げる
- `/joke` - ジョークを言う
- `/choose` - 選択肢から1つを選ぶ
- `/ping` - ボットのピングを表示

### ユーティリティ機能
- `/serverinfo` - サーバー情報を表示
- `/avatar` - アバターを表示
- `/roleinfo` - ロール情報を表示
- `/help` - ヘルプを表示
- `/uptime` - ボットの稼働時間
- `/botinfo` - ボット情報
- `/suggest` - 機能を提案

### レベル・経験値システム
- `/rank` - 自分または他のユーザーのランクを表示
- `/leaderboard` - サーバーのレベルランキング
- `/setlevel` - [管理者] ユーザーのレベルを設定
- `/addxp` - [管理者] ユーザーにXPを追加
- メッセージ送信でXP獲得、レベルアップ通知

### 音楽再生機能

#### スラッシュコマンド
- `/play` - YouTube URLまたは検索で音楽を再生
- `/search` - YouTube から曲を検索して候補から選択
- `/pause` / `/resume` - 一時停止 / 再開
- `/skip` - 現在の曲をスキップ
- `/stop` - 音楽を停止してキューをクリア
- `/repeat` - リピートモード変更（OFF → 1曲 → 全曲）
- `/shuffle` - シャッフル有効/無効
- `/nowplaying` - 現在再生中の曲と進行状況を表示
- `/queue` - 現在のキューを表示（リピート・シャッフル状態も表示）
- `/favorite` - 現在再生中の曲をお気に入りに追加
- `/favorites` - お気に入りリストを表示
- `/volume` - 音量調整（0-100%）
- `/leave` - ボイスチャネルから退出
- `/lyrics` - 再生中の曲の歌詞を表示（Genius + uta-net 対応）
- `/stats` - あなたの再生統計を表示
- `/recommend` - 再生履歴から曲をおすすめ

#### プレフィックスコマンド (h!)
快速操作用のプレフィックスコマンド：
- `h!p [URL or キーワード]` - 曲を再生（URL で直接再生または検索キーワード）
- `h!search [キーワード]` - 曲を検索して結果から選択
- `h!np` - 現在再生中の曲を表示
- `h!pause` - 一時停止 / 再開（トグル）
- `h!skip [count]` - スキップ（デフォルト 1 曲、`h!skip 3` で 3 曲スキップ）
- `h!vol [+/-num]` - 音量調整（例：`h!vol +10`、`h!vol -5`）

> **注意**: プレフィックスコマンドを使用するには、`.env` ファイルで `COMMAND_PREFIX=h` に設定してください。

### ウェルカムシステム
- `/welcome-setup` - ウェルカムメッセージを設定
- `/welcome-toggle` - 有効/無効を切り替え
- `/welcome-autorole` - 自動ロールを設定
- `/welcome-test` - テストメッセージを送信
- 新規メンバー参加時の自動通知

### 投票・アンケート
- `/poll` - 最大5つの選択肢で投票を作成
- `/quickpoll` - はい/いいえの簡易投票
- `/pollresult` - 投票結果を表示

### チケットシステム
- `/ticket-setup` - チケットシステムをセットアップ
- `/ticket-add` - チケットにユーザーを追加
- `/ticket-remove` - チケットからユーザーを削除
- `/ticket-close` - チケットを閉じる
- ボタンで簡単にチケット作成

### その他
- `/mchistory` - Minecraft プレイヤー名履歴を表示
- SQLiteデータベース連携
- エラーハンドリング機能
- ロギング機能

## セットアップ

### 1. 必要なライブラリのインストール

```bash
pip install -r requirements.txt
```

### 2. FFmpegのインストール（音楽再生機能に必要）

**Windows:**
1. https://ffmpeg.org/download.html から FFmpeg をダウンロード
2. 解凍して `C:\ffmpeg` などに配置
3. 環境変数PATHに `C:\ffmpeg\bin` を追加

**Linux/Mac:**
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# Mac
brew install ffmpeg
```

### 3. 環境設定

`.env.example` をコピーして `.env` ファイルを作成します：

```bash
cp .env.example .env
```

`.env` ファイルを編集して設定を行います：

```
DISCORD_TOKEN=your_discord_bot_token_here
COMMAND_PREFIX=h
BOT_OWNER_ID=your_user_id
LOG_LEVEL=INFO
GENIUS_API_TOKEN=your_genius_token_here
```

**COMMAND_PREFIX について:**
- このボットはプレフィックスコマンド（例：`h!p`, `h!skip` など）で快速操作ができます
- `COMMAND_PREFIX=h` で `h!` がプレフィックスになります
- `COMMAND_PREFIX=!` に設定すると `!p`, `!skip` などになります
- スラッシュコマンド（`/play` など）はプレフィックス設定の影響を受けません

### 4. Discord Bot の登録

1. [Discord Developer Portal](https://discord.com/developers/applications) にアクセス
2. 「New Application」をクリック
3. アプリケーション名を入力して作成
4. 左側の「Bot」をクリック
5. 「Add Bot」をクリック
6. 「TOKEN」セクションの「Copy」をクリックしてトークンをコピー
7. `.env` ファイルの `DISCORD_TOKEN` に貼り付け

### 5. ボットの権限設定

1. 左側の「OAuth2」→「URL Generator」をクリック
2. **Scopes** で以下を選択：
   - `bot`
   - `applications.commands`
3. **Permissions** で以下を選択：
   - `Send Messages`
   - `Embed Links`
   - `Read Message History`
   - `Manage Messages` (モデレーション機能用)
   - `Manage Roles` (ミュート機能用)
   - `Kick Members` (キック機能用)
   - `Ban Members` (バン機能用)
   - `Manage Channels` (チケットシステム用)
   - `Connect` (音楽再生用)
   - `Speak` (音楽再生用)
4. 生成された URL をコピーしてブラウザで開き、ボットをサーバーに招待

## 使い方

### ボットの起動

```bash
python bot.py
```

ボットが起動すると、ログが表示されます。Discord に接続されたら、利用準備完了です。

### コマンドの実行

すべてのコマンドは **スラッシュコマンド（/）** で実行します。Discord でメッセージ入力欄に `/` を入力すると、利用可能なコマンドが表示されます。

**例:**
```
/kick @user - ユーザーをキック
/8ball question:明日は晴れますか？ - 8ボール占い
/serverinfo - サーバー情報を表示
/help - すべてのコマンドを表示
/mchistory username:Notch - Minecraft プレイヤー名履歴を表示
```

**スラッシュコマンドの利点:**
- コマンドの自動補完
- パラメータの説明が表示される
- タイプミスが減る
- より直感的な操作

## API 仕様

このボットは以下の Mojang API を使用しています:

### UUID 取得
- **URL**: `https://api.mojang.com/users/profiles/minecraft/{username}`
- **メソッド**: GET
- **レスポンス例**:
  ```json
  {
    "id": "4566e69fc90740d312c5b641e8ad8b49",
    "name": "Notch"
  }
  ```

### 名前履歴取得
- **URL**: `https://api.mojang.com/user/profiles/{uuid}/names`
- **メソッド**: GET
- **レスポンス例**:
  ```json
  [
    {
      "name": "Notch"
    },
    {
      "name": "Brand",
      "changedToAt": 1417952000000
    }
  ]
  ```

## エラーハンドリング

- プレイヤー名が見つからない場合
- 名前の履歴を取得できない場合
- API が応答しない場合

上記の場合、適切なエラーメッセージが Discord に表示されます。

## コードの説明

### MinecraftAPI クラス

Minecraft/Mojang API と通信するためのクラスです。

- `get_uuid(username)`: プレイヤー名から UUID を取得
- `get_name_history(uuid)`: UUID から名前の履歴を取得

### /mchistory コマンド

1. ユーザーの入力を検証（プレイヤー名の長さ）
2. Mojang API から UUID を取得
3. UUID から名前の履歴を取得
4. 結果を Discord Embed として表示

## ライセンス

MIT

## 注意事項

- このボットは Mojang API の利用規約に従って動作しています
- API には レート制限がある場合があります
- 大量のリクエストを送らないでください

## トラブルシューティング

### トークンが設定されていません
→ `.env` ファイルを作成し、`DISCORD_TOKEN` を設定してください

### コマンドが表示されない
→ ボットを再起動してから数分待ってください。Discord のコマンド同期に時間がかかる場合があります

### API エラーが出る
→ Minecraft API が一時的に利用できない可能性があります。しばらく待ってから再度試してください

## サポート

問題が発生した場合は、コンソール出力を確認してください。詳細なエラーログが表示されます。
