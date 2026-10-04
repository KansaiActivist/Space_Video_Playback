# Space_Video_Playback
Twikitを使用しXのスペース機能で任意の音声、動画ファイルを再生する。
# セットアップ
.envを作成し、以下のように設定を書き込みます。
```
AUTH_TOKEN=xxx
CT0=xxx

VIDEO_FILE=Video.mp4

SPACE_TITLE=ファイル再生

CONVERSATION_CONTROLS=2

VOLUME=1.0
```
AUTH_TOKEN,CT0はX画面で開発者ツールを開き、アプリケーション→CookieのAUTH_TOKEN,CT0を貼り付けてください。
VIDEO_FILEは再生したいビデオのファイル名を入力。
SPACE_TITLEはスペース名を入力してください。
CONVERSATION_CONTROLESは0は自分のみ発言可能、1は招待されたユーザーのみ発言可能、2は誰でも発言可能です。
VOLUMEは任意の音量（普通は1.0）に調整してください。
# 実行
ターミナルで```python main.py```と実行してください。<br>
FFmpegが実行に必要です。<br>
モジュールが足りないと言われたら```pip install モジュール名```でインストールしてください。<br>
正しく実行されれば自動的にスペースが開き、動画が再生されています。
