import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

MAX_FILE = 10 * 1024 * 1024
MAX_TOTAL = 25 * 1024 * 1024
MAX_PIXELS = 20_000_000
FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class InputError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


@dataclass
class ImageInput:
    image_id: str
    data: bytes
    mime: str
    width: int
    height: int


def validate_image(data: bytes, image_id: str, declared_type: str | None = None) -> ImageInput:
    if len(data) > MAX_FILE:
        raise InputError("单张图片超过 10 MB。", 413)
    try:
        with Image.open(io.BytesIO(data)) as picture:
            if picture.format not in FORMATS:
                raise InputError("仅支持 JPEG、PNG 和 WebP。", 415)
            mime = FORMATS[picture.format]
            if declared_type not in (None, "application/octet-stream", mime):
                raise InputError("声明的图片类型与实际文件不一致。", 415)
            width, height = picture.size
            if width * height > MAX_PIXELS:
                raise InputError("解码后图片超过 20 MP。", 413)
            if getattr(picture, "n_frames", 1) > 1:
                raise InputError("请上传静态图片，不支持动画。", 415)
            picture.verify()
        with Image.open(io.BytesIO(data)) as decoded:
            decoded.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise InputError("图片损坏或无法安全解码。", 415) from error
    return ImageInput(image_id, data, mime, width, height)


async def read_uploads(files):
    if len(files) > 5:
        raise InputError("最多上传 5 张图片。")
    images, total = [], 0
    for index, upload in enumerate(files, 1):
        chunks, size = [], 0
        while chunk := await upload.read(64 * 1024):
            size += len(chunk)
            total += len(chunk)
            if size > MAX_FILE or total > MAX_TOTAL:
                raise InputError("图片超过单张 10 MB 或总计 25 MB 的限制。", 413)
            chunks.append(chunk)
        images.append(validate_image(b"".join(chunks), f"image_{index}", upload.content_type))
    return images
