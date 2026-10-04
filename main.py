import asyncio
import os
import shutil
import subprocess
import struct
from fractions import Fraction

from dotenv import load_dotenv

import twikit
from aiortc.mediastreams import AudioFrame, AudioStreamTrack


load_dotenv()

VIDEO_FILE = os.getenv("VIDEO_FILE", "video.mp4")

SPACE_TITLE = os.getenv(
    "SPACE_TITLE",
    "動画配信"
)

CONVERSATION_CONTROLS = int(
    os.getenv("CONVERSATION_CONTROLS", "2")
)

SAMPLE_RATE = 48000
CHANNELS = 2
SAMPLES_PER_FRAME = 960

VOLUME = float(
    os.getenv("VOLUME", "1.0")
)



AUTH_TOKEN = os.getenv("AUTH_TOKEN")
CT0 = os.getenv("CT0")


def check_environment():

    missing = []

    if not AUTH_TOKEN:
        missing.append("AUTH_TOKEN")

    if not CT0:
        missing.append("CT0")

    if missing:
        raise RuntimeError(
            "環境変数が不足しています: "
            + ", ".join(missing)
        )

    if not os.path.isfile(VIDEO_FILE):
        raise FileNotFoundError(
            f"動画ファイルがありません: {VIDEO_FILE}"
        )

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "FFmpegが見つかりません。"
            "ffmpegをインストールしてPATHを設定してください。"
        )



class VideoAudioTrack(AudioStreamTrack):

    kind = "audio"

    def __init__(self, filename):

        super().__init__()

        self.filename = filename

        self.process = None

        self.pts = 0

        self.next_frame_time = None

        self.bytes_per_sample = 2

        self.frame_bytes = (
            SAMPLES_PER_FRAME
            * CHANNELS
            * self.bytes_per_sample
        )

        self.finished = False

        self._start_ffmpeg()


    def _start_ffmpeg(self):

        command = [
            "ffmpeg",

            "-hide_banner",
            "-loglevel", "error",

            "-i",
            self.filename,

            "-vn",

            "-ar",
            str(SAMPLE_RATE),

            "-ac",
            str(CHANNELS),

            "-f",
            "s16le",

            "pipe:1",
        ]

        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )


    def _read_frame(self):

        if self.process is None:
            return b""

        data = self.process.stdout.read(
            self.frame_bytes
        )

        if not data:
            self.finished = True

        return data


    def _apply_volume(self, data):

        if VOLUME == 1.0:
            return data

        sample_count = len(data) // 2

        samples = struct.unpack(
            "<" + ("h" * sample_count),
            data,
        )

        output = []

        for sample in samples:

            value = int(
                sample * VOLUME
            )

            value = max(
                -32768,
                min(32767, value)
            )

            output.append(value)

        return struct.pack(
            "<" + ("h" * len(output)),
            *output,
        )


    async def recv(self):

        loop = asyncio.get_running_loop()


        if self.next_frame_time is None:

            self.next_frame_time = loop.time()

        now = loop.time()

        delay = (
            self.next_frame_time
            - now
        )

        if delay > 0:

            await asyncio.sleep(delay)

        self.next_frame_time += 0.020

        data = await loop.run_in_executor(
            None,
            self._read_frame,
        )


        if not data:


            data = bytes(
                self.frame_bytes
            )


        data = self._apply_volume(data)


        if len(data) < self.frame_bytes:

            data += bytes(
                self.frame_bytes - len(data)
            )


        frame = AudioFrame(
            format="s16",
            layout="stereo",
            samples=SAMPLES_PER_FRAME,
        )

        frame.sample_rate = SAMPLE_RATE

        frame.pts = self.pts

        frame.time_base = Fraction(
            1,
            SAMPLE_RATE,
        )

        frame.planes[0].update(data)

        self.pts += SAMPLES_PER_FRAME

        return frame


    def close(self):

        if self.process:

            try:
                if self.process.poll() is None:
                    self.process.kill()
            except Exception:
                pass

            try:
                self.process.wait(
                    timeout=2
                )
            except Exception:
                pass

            self.process = None

        super().stop()


async def create_space(client):

    print()
    print("Spaceを作成しています...")

    created = await client.spaces.create_space(
        title=SPACE_TITLE,
        conversation_controls=CONVERSATION_CONTROLS,
    )

    broadcast = created.get("broadcast")

    if not broadcast:
        raise RuntimeError(
            f"Space作成結果にbroadcastがありません: "
            f"{created}"
        )

    space_id = broadcast.get("id")

    if not space_id:
        raise RuntimeError(
            f"Space IDを取得できません: "
            f"{created}"
        )

    print(
        f"Space作成完了: {space_id}"
    )

    return created, space_id



async def wait_until_live(
    client,
    space_id,
    timeout=60,
):

    print(
        "SpaceがLiveになるのを待っています..."
    )

    start = asyncio.get_running_loop().time()

    while True:

        space = await client.spaces.get_space(
            space_id
        )

        print(
            f"  状態: {space.state}"
        )

        if str(space.state).lower() == "running":

            print("SpaceはLiveです。")

            return space

        elapsed = (
            asyncio.get_running_loop().time()
            - start
        )

        if elapsed >= timeout:

            raise TimeoutError(
                "SpaceがLiveになりませんでした。"
                f"現在の状態: {space.state}"
            )

        await asyncio.sleep(2)



async def main():

    check_environment()

    client = twikit.Client(
        language="ja"
    )


    print("Xへ接続しています...")

    client.set_cookies({
        "auth_token": AUTH_TOKEN,
        "ct0": CT0,
    })

    user_id = await client.user_id()

    print(
        f"ログイン成功: {user_id}"
    )

    created = None
    space_id = None
    track = None
    session = None

    try:


        created, space_id = await create_space(
            client
        )

        print()
        print(
            f"Space ID: {space_id}"
        )


        await wait_until_live(
            client,
            space_id,
        )


        print()
        print(
            "動画音声を準備しています..."
        )

        track = VideoAudioTrack(
            VIDEO_FILE
        )

        print(
            f"ファイル: {VIDEO_FILE}"
        )

        print(
            f"音声: {SAMPLE_RATE}Hz / "
            f"{CHANNELS}ch / PCM16"
        )


        print()
        print(
            "Spaceへ接続しています..."
        )

        session = await client.spaces.host(
            created,
            audio_track=track,
        )

        print()
        print("========================================")
        print(" 配信開始")
        print("========================================")
        print(f"Space ID: {space_id}")
        print(f"タイトル: {SPACE_TITLE}")
        print(f"動画: {VIDEO_FILE}")
        print()
        print("動画の最後まで自動再生します。")
        print("========================================")
        print()


        while not track.finished:

            await asyncio.sleep(0.5)

        print()
        print(
            "動画の再生が終了しました。"
        )

        if track.process:

            try:
                track.process.wait(
                    timeout=5
                )
            except Exception:
                pass


        print(
            "音声配信を終了しています..."
        )

        if session:

            try:
                await session.close()
            except Exception as e:

                print(
                    f"音声セッション終了時の警告: {e}"
                )

        session = None


        print(
            "Spaceを終了しています..."
        )

        await client.spaces.end_space(
            space_id
        )

        print()
        print("========================================")
        print(" 配信終了")
        print("========================================")
        print(
            f"Space ID: {space_id}"
        )

    except Exception:


        print()
        print(
            "配信中にエラーが発生しました。"
        )

        raise

    finally:

        if track:

            track.close()


        if space_id:

            try:

                space = await client.spaces.get_space(
                    space_id
                )

                state = str(
                    space.state
                ).lower()

                if state == "running":

                    print(
                        "残っているSpaceを終了しています..."
                    )

                    await client.spaces.end_space(
                        space_id
                    )

            except Exception as e:

                print(
                    f"Space終了処理の警告: {e}"
                )


        try:

            await client.http.aclose()

        except Exception:

            pass



if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print()
        print(
            "Ctrl+Cで停止しました。"
        )

    except Exception as e:

        print()
        print("========================================")
        print(" エラー")
        print("========================================")
        print(
            f"{type(e).__name__}: {e}"
        )
