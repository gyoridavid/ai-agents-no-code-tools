from fastapi import FastAPI, status, APIRouter, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Literal, Optional
import os
import signal
import sys
from loguru import logger
from video.tts import TTS
from video.stt import STT
from video.storage import Storage
from video.caption import Caption
from video.media import MediaUtils
from video.builder import VideoBuilder
from video.config import device

CHUNK_SIZE = 1024 * 1024 * 10  # 10MB chunks

logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level> | <blue>{extra}</blue>",
    level="DEBUG",
)

logger.info("This server was created by the 'AI Agents A-Z' YouTube channel")
logger.info("https://www.youtube.com/@aiagentsaz")
logger.info("Using device: {}", device)

def iterfile(path: str):
    with open(path, mode="rb") as file:
        while chunk := file.read(CHUNK_SIZE):
            yield chunk


def signal_handler(sig, frame):
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

app = FastAPI()

@app.get("/health")
def read_root():
    return {"status": "ok"}


api_router = APIRouter()
v1_api_router = APIRouter()
v1_media_api_router = APIRouter()

storage = Storage(
    storage_path=os.path.abspath(os.path.join(os.path.dirname(__file__), "media"))
)


@v1_media_api_router.get("/audio-tools/tts/kokoro/voices")
def get_kokoro_voices():
    tts_manager = TTS()
    voices = tts_manager.valid_kokoro_voices()
    return {"voices": voices}


@v1_media_api_router.post("/audio-tools/tts/kokoro")
def generate_kokoro_tts(
    background_tasks: BackgroundTasks,
    text: str = Form(..., description="Text to convert to speech"),
    voice: Optional[str] = Form(None, description="Voice name for kokoro TTS"),
    speed: Optional[float] = Form(None, description="Speed for kokoro TTS"),
):
    """
    Generate audio from text using specified TTS engine.
    """
    if not voice:
        voice = "af_heart"
    tts_manager = TTS()
    voices = tts_manager.valid_kokoro_voices()
    if voice not in voices:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid voice: {voice}. Valid voices: {voices}"},
        )
    audio_id, audio_path = storage.create_media_filename_with_id(
        media_type="audio", file_extension=".wav"
    )
    tmp_file_id = storage.create_tmp_file(audio_id)

    def bg_task():
        tts_manager.kokoro(
            text=text,
            output_path=audio_path,
            voice=voice,
            speed=speed if speed else 1.0,
        )
        storage.delete_media(tmp_file_id)

    background_tasks.add_task(bg_task)

    return {"file_id": audio_id}


@v1_media_api_router.post("/audio-tools/tts/chatterbox")
def generate_chatterbox_tts(
    background_tasks: BackgroundTasks,
    text: str = Form(..., description="Text to convert to speech"),
    sample_audio_id: Optional[str] = Form(
        None, description="Sample audio ID for voice cloning"
    ),
    sample_audio_file: Optional[UploadFile] = File(
        None, description="Sample audio file for voice cloning"
    ),
    exaggeration: Optional[float] = Form(
        0.5, description="Exaggeration factor for voice cloning"
    ),
    cfg_weight: Optional[float] = Form(0.5, description="CFG weight for voice cloning"),
    temperature: Optional[float] = Form(
        0.8, description="Temperature for voice cloning (default: 0.8)"
    ),
):
    """
    Generate audio from text using Chatterbox TTS.
    """
    tts_manager = TTS()
    audio_id, audio_path = storage.create_media_filename_with_id(
        media_type="audio", file_extension=".wav"
    )

    sample_audio_path = None
    if sample_audio_file:
        if not sample_audio_file.filename.endswith(".wav"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Sample audio file must be a .wav file."},
            )
        sample_audio_id = storage.upload_media(
            media_type="tmp",
            media_data=sample_audio_file.file.read(),
            file_extension=".wav",
        )
        sample_audio_path = storage.get_media_path(sample_audio_id)
    elif sample_audio_id:
        if not storage.media_exists(sample_audio_id):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": f"Sample audio with ID {sample_audio_id} not found."},
            )
        sample_audio_path = storage.get_media_path(sample_audio_id)

    tmp_file_id = storage.create_tmp_file(audio_id)

    def bg_task():
        try:
            tts_manager.chatterbox(
                text=text,
                output_path=audio_path,
                sample_audio_path=sample_audio_path,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=temperature,
            )
        except Exception as e:
            logger.error(f"Error in Chatterbox TTS: {e}")
        finally:
            storage.delete_media(tmp_file_id)

    background_tasks.add_task(bg_task)

    return {"file_id": audio_id}


@v1_media_api_router.post("/storage")
def upload_file(
    file: Optional[UploadFile] = File(None, description="File to upload"),
    url: Optional[str] = Form(None, description="URL of the file to upload (optional)"),
    media_type: Literal["image", "video", "audio"] = Form(
        ..., description="Type of media being uploaded"
    ),
):
    """
    Upload a file and return its ID.
    """
    if media_type not in ["image", "video", "audio"]:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid media type: {media_type}"},
        )
    if file:
        file_id = storage.upload_media(
            media_type=media_type,
            media_data=file.file.read(),
            file_extension=os.path.splitext(file.filename)[1],
        )

        return {"file_id": file_id}
    elif url:
        if not storage.is_valid_url(url):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": f"Invalid URL: {url}"},
            )
        file_id = storage.upload_media_from_url(media_type=media_type, url=url)
        return {"file_id": file_id}
        
@v1_media_api_router.get("/storage")
def list_files(media_type: Optional[str] = None):
    """
    List all media files, optionally filtered by media_type.
    """
    all_files = storage.list_media(media_type=media_type)
    return {"data": all_files}

@v1_media_api_router.get("/storage/{file_id}")
def download_file(file_id: str):
    """
    Download a file by its ID.
    """
    if not storage.media_exists(file_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"File with ID {file_id} not found."},
        )

    file_path = storage.get_media_path(file_id)
    return StreamingResponse(
        iterfile(file_path),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename={os.path.basename(file_path)}"
        },
    )


@v1_media_api_router.delete("/storage/{file_id}")
def delete_file(file_id: str):
    """
    Delete a file by its
    """
    if storage.media_exists(file_id):
        storage.delete_media(file_id)
    return {"status": "success"}


@v1_media_api_router.get("/storage/{file_id}/status")
def file_status(file_id: str):
    """
    Check the status of a file by its ID.
    """
    tmp_id = storage.create_tmp_file_id(file_id)
    if storage.media_exists(tmp_id):
        return {"status": "processing"}
    elif storage.media_exists(file_id):
        return {"status": "ready"}
    return {"status": "not_found"}


@v1_media_api_router.post("/video-tools/merge")
def merge_videos(
    background_tasks: BackgroundTasks,
    video_ids: str = Form(..., description="List of video IDs to merge"),
    background_music_id: Optional[str] = Form(
        None, description="Background music ID (optional)"
    ),
    background_music_volume: Optional[float] = Form(
        0.5, description="Volume for background music (0.0 to 1.0)"
    ),
):
    """
    Merge multiple videos into one.
    """
    video_ids = video_ids.split(",") if video_ids else []
    if not video_ids:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "At least one video ID is required."},
        )

    merged_video_id, merged_video_path = storage.create_media_filename_with_id(
        media_type="video", file_extension=".mp4"
    )

    video_paths = []
    for video_id in video_ids:
        if not storage.media_exists(video_id):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": f"Video with ID {video_id} not found."},
            )
        video_paths.append(storage.get_media_path(video_id))

    if background_music_id and not storage.media_exists(background_music_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": f"Background music with ID {background_music_id} not found."
            },
        )
    background_music_path = (
        storage.get_media_path(background_music_id) if background_music_id else None
    )

    utils = MediaUtils()

    temp_file_id = storage.create_tmp_file(merged_video_id)

    def bg_task():
        utils.merge_videos(
            video_paths=video_paths,
            output_path=merged_video_path,
            background_music_path=background_music_path,
            background_music_volume=background_music_volume,
        )
        storage.delete_media(temp_file_id)

    background_tasks.add_task(bg_task)

    return {"file_id": merged_video_id}


@v1_media_api_router.post("/video-tools/generate/tts-captioned-video")
def generate_captioned_video(
    background_tasks: BackgroundTasks,
    background_id: str = Form(..., description="Background image ID"),
    text: Optional[str] = Form(None, description="Text to generate video from"),
    width: Optional[int] = Form(1080, description="Width of the video (default: 1080)"),
    height: Optional[int] = Form(
        1920, description="Height of the video (default: 1920)"
    ),
    audio_id: Optional[str] = Form(
        None, description="Audio ID for the video (optional)"
    ),
    kokoro_voice: Optional[str] = Form(
        "af_heart", description="Voice for kokoro TTS (default: af_heart)"
    ),
    kokoro_speed: Optional[float] = Form(
        1.0, description="Speed for kokoro TTS (default: 1.0)"
    ),
):
    """
    Generate a captioned video from text and background image.

    """
    if audio_id and not storage.media_exists(audio_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Audio with ID {audio_id} not found."},
        )
    ttsManager = TTS()
    if not audio_id and kokoro_voice not in ttsManager.valid_kokoro_voices():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid voice: {kokoro_voice}."},
        )
    media_type = storage.get_media_type(background_id)
    if media_type not in ["image"]:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid media type: {media_type}"},
        )
    if not storage.media_exists(background_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Background image with ID {background_id} not found."},
        )

    output_id, output_path = storage.create_media_filename_with_id(
        media_type="video", file_extension=".mp4"
    )
    dimensions = (width, height)
    builder = VideoBuilder(
        dimensions=dimensions,
    )
    builder.set_media_utils(MediaUtils())

    tmp_file_id = storage.create_tmp_file(output_id)

    def bg_task(
        tmp_file_id: str = tmp_file_id,
    ):
        tmp_file_ids = [tmp_file_id]

        # set audio, generate captions
        captions = None
        tts_audio_id = audio_id
        if tts_audio_id:
            audio_path = storage.get_media_path(tts_audio_id)
            stt = STT(model_size="tiny")
            captions = stt.transcribe(audio_path=audio_path)[0]
            builder.set_audio(audio_path)
        # generate TTS and set audio
        else:
            tts_audio_id, audio_path = storage.create_media_filename_with_id(
                media_type="audio", file_extension=".wav"
            )
            tmp_file_ids.append(tts_audio_id)
            captions = ttsManager.kokoro(
                text=text,
                output_path=audio_path,
                voice=kokoro_voice,
                speed=kokoro_speed,
            )[0]
        builder.set_audio(audio_path)

        # create subtitle
        captionsManager = Caption()
        subtitle_id, subtitle_path = storage.create_media_filename_with_id(
            media_type="tmp", file_extension=".ass"
        )
        tmp_file_ids.append(subtitle_id)
        segments = captionsManager.create_subtitle_segments_english(
            captions=captions,
            lines=1,
            max_length=1,
        )
        captionsManager.create_subtitle(
            segments=segments,
            font_size=120,
            output_path=subtitle_path,
            dimensions=dimensions,
            shadow_blur=10,
            stroke_size=5,
        )
        builder.set_captions(
            file_path=subtitle_path,
        )

        builder.set_background_image(
            storage.get_media_path(background_id),
        )

        builder.set_output_path(output_path)

        builder.execute()

        for tmp_file_id in tmp_file_ids:
            if storage.media_exists(tmp_file_id):
                storage.delete_media(tmp_file_id)

    background_tasks.add_task(bg_task, tmp_file_id=tmp_file_id)

    return {
        "file_id": output_id,
    }


v1_api_router.include_router(v1_media_api_router, prefix="/media", tags=["media"])
api_router.include_router(v1_api_router, prefix="/v1", tags=["v1"])
app.include_router(api_router, prefix="/api", tags=["api"])
