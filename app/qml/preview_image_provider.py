from __future__ import annotations

import threading

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtQuick import QQuickImageProvider


class PreviewImageProvider(QQuickImageProvider):
    """Expose the latest owned preview frame to QML."""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.Image)
        self._lock = threading.RLock()
        self._image = self._placeholder()

    @staticmethod
    def _placeholder() -> QImage:
        image = QImage(16, 16, QImage.Format_RGBA8888)
        image.fill(QColor("#0d0f10"))
        return image

    def set_image(self, image: QImage) -> None:
        if image is None or image.isNull():
            return
        with self._lock:
            # QImage 使用隐式共享；这里只持有只读帧，避免大画布每次发布都深拷贝。
            self._image = QImage(image)

    def clear(self) -> None:
        with self._lock:
            self._image = self._placeholder()

    def requestImage(self, image_id, size, requested_size):  # noqa: N802 - Qt API
        del image_id
        with self._lock:
            image = QImage(self._image)

        if requested_size.isValid() and requested_size.width() > 0 and requested_size.height() > 0:
            image = image.scaled(
                requested_size,
                aspectMode=Qt.KeepAspectRatio,
                mode=Qt.SmoothTransformation,
            )
        if isinstance(size, QSize):
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image
