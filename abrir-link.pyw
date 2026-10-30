# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Pelo codigo-fonte: o que o Windows chama para abrir um link no TeleZapp. O
Windows nao abre na pasta do projeto, e passar por um .bat ou pelo cmd deixaria
um & do link virar comando."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telezapp.__main__ import main  # noqa: E402

sys.exit(main())
