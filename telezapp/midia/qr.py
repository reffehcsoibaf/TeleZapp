# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Ler um codigo QR de um arquivo de imagem ou da camera. Sem wx."""
import logging
import time

log = logging.getLogger("telezapp.qr")


def _ler_quadro(cv2, quadro):
    texto = cv2.QRCodeDetector().detectAndDecode(quadro)[0]
    return texto or ""


def ler_arquivo(caminho):
    """O texto do codigo na imagem, ou "". Le pelos bytes: o OpenCV nao abre
    caminhos com acento no Windows."""
    import cv2
    import numpy as np
    imagem = cv2.imdecode(np.fromfile(caminho, dtype=np.uint8),
                          cv2.IMREAD_COLOR)
    return "" if imagem is None else _ler_quadro(cv2, imagem)


def ler_camera(segundos=30, parar=None):
    """Olha a primeira camera ate achar um codigo; "" se nao achar a tempo."""
    import cv2
    camera = cv2.VideoCapture(0)
    try:
        fim = time.monotonic() + segundos
        while time.monotonic() < fim and not (parar and parar.is_set()):
            ok, quadro = camera.read()
            if not ok:
                time.sleep(0.2)
                continue
            texto = _ler_quadro(cv2, quadro)
            if texto:
                return texto
        return ""
    finally:
        camera.release()
