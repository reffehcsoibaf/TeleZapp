# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Quadros de um video numa imagem so (uma grade com a hora de cada quadro),
para descrever o video com qualquer provedor que veja imagens."""
from telezapp.nucleo.ia.provedores import ErroIA

# perfil -> (quadros, colunas, largura de cada quadro)
GRADES = {"curto": (4, 2, 480), "medio": (9, 3, 480),
          "detalhado": (12, 4, 400)}


def _hora(segundos):
    s = int(round(segundos))
    return "%d:%02d" % (s // 60, s % 60)


def grade_de_quadros(caminho, perfil="medio"):
    """(jpeg, [horas em segundos]) com os quadros do video espalhados por
    toda a duracao. ErroIA se o video nao pode ser lido."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise ErroIA("arquivo", "Este computador não tem o leitor de vídeo "
                                "necessário para descrever o vídeo.")
    quantos, colunas, largura = GRADES.get(perfil, GRADES["medio"])
    cap = cv2.VideoCapture(caminho)
    try:
        if not cap.isOpened():
            raise ErroIA("arquivo", "Não consegui abrir o vídeo.")
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        if fps <= 0 or fps > 1000:
            fps = 25.0
        quadros, tempos = [], []
        if total > 0:
            for i in range(quantos):
                alvo = min(total - 1, int(total * (i + 0.5) / quantos))
                cap.set(cv2.CAP_PROP_POS_FRAMES, alvo)
                ok, q = cap.read()
                if ok and q is not None:
                    quadros.append(q)
                    tempos.append(alvo / fps)
        if not quadros:
            raise ErroIA("arquivo", "Não consegui ler os quadros do vídeo. O "
                                    "formato pode não ser suportado.")
    finally:
        cap.release()
    altura = max(int(largura * quadros[0].shape[0] / quadros[0].shape[1]), 1)
    pecas = []
    for q, t in zip(quadros, tempos):
        q = cv2.resize(q, (largura, altura))
        texto = _hora(t)
        cv2.putText(q, texto, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(q, texto, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    (255, 255, 255), 2, cv2.LINE_AA)
        pecas.append(q)
    while len(pecas) % colunas:
        pecas.append(np.zeros_like(pecas[0]))
    linhas = [np.hstack(pecas[i:i + colunas])
              for i in range(0, len(pecas), colunas)]
    ok, jpeg = cv2.imencode(".jpg", np.vstack(linhas),
                            [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise ErroIA("arquivo", "Não consegui montar a imagem do vídeo.")
    return jpeg.tobytes(), tempos
