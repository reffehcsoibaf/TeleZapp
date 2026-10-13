# SPDX-License-Identifier: GPL-3.0-or-later
"""Um wx minimo, so para testar a logica da janela fora do Windows.

Nao desenha nada: guarda itens, selecao e foco, e executa CallAfter na hora.
Os testes de verdade da interface (NVDA, teclado) sao feitos no Windows.
"""
import types

_foco = [None]
ID_ANY, ID_OK, ID_CANCEL = -1, 5100, 5101
YES, NO, OK, CANCEL = 2, 8, 4, 16
YES_NO = YES | NO
ICON_WARNING = ICON_QUESTION = ICON_INFORMATION = 0
DEFAULT_DIALOG_STYLE = RESIZE_BORDER = 0
LB_SINGLE = LB_HSCROLL = TE_MULTILINE = TE_PASSWORD = TE_READONLY = 0
VERTICAL = HORIZONTAL = EXPAND = ALL = BOTTOM = TOP = LEFT = RIGHT = 0
ALIGN_RIGHT = 0
WXK_ESCAPE, WXK_RETURN, WXK_NUMPAD_ENTER = 27, 13, 370
WXK_UP, WXK_DOWN, WXK_HOME, WXK_END, WXK_PAGEUP, WXK_PAGEDOWN = range(
    315, 321)
EVT_CLOSE = EVT_CHAR_HOOK = EVT_MENU = EVT_LISTBOX_DCLICK = object()
EVT_CONTEXT_MENU = EVT_KEY_DOWN = EVT_BUTTON = object()
DefaultPosition = (-1, -1)
mensagens = []          # o que passou por MessageBox
resposta_messagebox = [NO]


def CallAfter(f, *a, **k):
    f(*a, **k)


def CallLater(ms, f, *a, **k):
    return None


def MessageBox(texto, titulo="", estilo=0, pai=None):
    mensagens.append(texto)
    return resposta_messagebox[0]


def Point(x, y):
    return (x, y)


class Janela:
    def __init__(self, *a, **k):
        self.vivo = True

    def Bind(self, *a, **k):
        pass

    def SetFocus(self):
        _foco[0] = self

    def __bool__(self):
        return getattr(self, "vivo", True)


class Frame(Janela):
    def SetTitle(self, t):
        self.titulo = t

    def CreateStatusBar(self):
        self.status = ""

    def SetStatusText(self, t):
        self.status = t

    def SetMenuBar(self, b):
        pass

    def Centre(self):
        pass

    def Show(self):
        pass

    def Hide(self):
        pass

    def Raise(self):
        pass

    def Destroy(self):
        self.vivo = False

    def IsActive(self):
        return True

    def FindFocus(self):
        return _foco[0]


class Dialog(Frame):
    pass


class Panel(Janela):
    def SetSizer(self, s):
        pass


class StaticText(Janela):
    def __init__(self, pai=None, label="", **k):
        super().__init__()
        self.label = label

    def SetLabel(self, t):
        self.label = t

    def Wrap(self, n):
        pass


class ListBox(Janela):
    def __init__(self, *a, **k):
        super().__init__()
        self.itens, self.sel = [], -1

    def Set(self, itens):
        self.itens, self.sel = list(itens), -1

    def GetCount(self):
        return len(self.itens)

    def GetSelection(self):
        return self.sel

    def SetSelection(self, i):
        assert 0 <= i < len(self.itens), (i, len(self.itens))
        self.sel = i

    def GetString(self, i):
        return self.itens[i]

    def selecionado(self):
        return self.itens[self.sel] if self.sel >= 0 else None


class TextCtrl(Janela):
    def __init__(self, *a, value="", **k):
        super().__init__()
        self.valor = value

    def GetValue(self):
        return self.valor

    def SetValue(self, v):
        self.valor = v

    def Clear(self):
        self.valor = ""


class Button(Janela):
    pass


class BoxSizer:
    def __init__(self, *a):
        pass

    def Add(self, *a, **k):
        pass


class MenuItem:
    def __init__(self):
        self.marcado = False

    def Check(self, v=True):
        self.marcado = v


class Menu:
    def Append(self, *a, **k):
        return MenuItem()

    AppendCheckItem = AppendRadioItem = Append

    def AppendSeparator(self):
        pass


class MenuBar:
    def Append(self, *a):
        pass


TheClipboard = types.SimpleNamespace(Open=lambda: False)
