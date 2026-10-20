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
NO_DEFAULT = 0
ICON_WARNING = ICON_QUESTION = ICON_INFORMATION = 0
DEFAULT_DIALOG_STYLE = RESIZE_BORDER = 0
LB_SINGLE = LB_HSCROLL = TE_MULTILINE = TE_PASSWORD = TE_READONLY = 0
VERTICAL = HORIZONTAL = EXPAND = ALL = BOTTOM = TOP = LEFT = RIGHT = 0
ALIGN_RIGHT = ALIGN_CENTER = RA_SPECIFY_COLS = TE_PROCESS_ENTER = 0
EVT_RADIOBOX = EVT_TEXT_ENTER = EVT_TEXT_PASTE = EVT_SIZE = object()
TE_CENTER = 0
WHITE = (255, 255, 255)
escolha_lista = [0]       # o que o SingleChoiceDialog "escolhe"
resposta_lista = [ID_OK]
WXK_ESCAPE, WXK_RETURN, WXK_NUMPAD_ENTER = 27, 13, 370
WXK_DELETE, WXK_SPACE = 127, 32
WXK_UP, WXK_DOWN, WXK_HOME, WXK_END, WXK_PAGEUP, WXK_PAGEDOWN = range(
    315, 321)
LC_REPORT = LC_SINGLE_SEL = LC_NO_HEADER = 0
EVT_LIST_ITEM_ACTIVATED = object()
EVT_CLOSE = EVT_CHAR_HOOK = EVT_MENU = EVT_LISTBOX_DCLICK = object()
EVT_CONTEXT_MENU = EVT_KEY_DOWN = EVT_BUTTON = EVT_LISTBOX = object()
EVT_CHOICE = EVT_TEXT = object()
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

    def Show(self, v=True):
        self.visivel = v

    def Layout(self):
        pass

    def Close(self, *a):
        self.vivo = False

    def RequestUserAttention(self, *a):
        pass

    def SetFocus(self):
        _foco[0] = self

    def HasFocus(self):
        return _foco[0] is self

    def __bool__(self):
        return getattr(self, "vivo", True)


class Frame(Janela):
    def SetTitle(self, t):
        self.titulo = t

    def GetTitle(self):
        return self.titulo

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

    def SetBackgroundColour(self, c):
        pass

    def ShowFullScreen(self, v):
        self.cheia = v

    def GetClientSize(self):
        return (1920, 1080)

    def FindFocus(self):
        return _foco[0]


class Fonte:
    def GetPointSize(self):
        return 9

    def SetPointSize(self, n):
        pass


class SingleChoiceDialog:
    def __init__(self, pai, texto, titulo, opcoes):
        self.opcoes = opcoes

    def ShowModal(self):
        return resposta_lista[0]

    def GetSelection(self):
        return escolha_lista[0]

    def Destroy(self):
        pass


class MultiChoiceDialog(SingleChoiceDialog):
    def SetSelections(self, itens):
        self.marcadas = list(itens)

    def GetSelections(self):
        return getattr(self, "novas", self.marcadas)


class Dialog(Frame):
    def SetSizer(self, s):
        pass

    def SetEscapeId(self, i):
        pass

    def Fit(self):
        pass

    def Layout(self):
        pass

    def CentreOnParent(self):
        pass

    def GetTitle(self):
        return getattr(self, "titulo", "")

    def __init__(self, pai=None, title="", **k):
        super().__init__()
        self.titulo = title
        self.mostrado = False

    def Show(self, v=True):
        self.mostrado = v

    def SetSizerAndFit(self, s):
        pass


class RadioBox(Janela):
    def __init__(self, *a, **k):
        super().__init__()
        self.sel = 0

    def GetSelection(self):
        return self.sel

    def SetSelection(self, i):
        self.sel = i


class StaticBitmap(Janela):
    def SetBitmap(self, b):
        self.bitmap = b

    def SetPosition(self, p):
        self.posicao = p


class Image:
    def __init__(self, w, h, dados):
        assert len(dados) == w * h * 3
        self.w, self.h = w, h


class Bitmap:
    def __init__(self, img):
        self.img = img


class Panel(Janela):
    def SetSizer(self, s):
        pass

    def SetSize(self, t):
        self.tamanho = t

    def SetBackgroundColour(self, c):
        pass

    def Show(self, v=True):
        self.visivel = v

    def Layout(self):
        pass


class Choice(Janela):
    def __init__(self, *a, choices=(), **k):
        super().__init__()
        self.itens, self.sel = list(choices), -1

    def Set(self, itens):
        self.itens, self.sel = list(itens), -1

    def GetSelection(self):
        return self.sel

    def SetSelection(self, i):
        assert 0 <= i < len(self.itens), (i, len(self.itens))
        self.sel = i


class StaticText(Janela):
    def __init__(self, pai=None, label="", **k):
        super().__init__()
        self.label = label

    def SetLabel(self, t):
        self.label = t

    def GetLabel(self):
        return self.label

    def Wrap(self, n):
        pass


class ListBox(Janela):
    def __init__(self, *a, **k):
        super().__init__()
        self.itens, self.sel = [], -1

    def Set(self, itens):
        self.itens, self.sel = list(itens), -1

    def SetString(self, i, texto):
        self.itens[i] = texto

    def Append(self, texto):
        self.itens.append(texto)

    def Delete(self, i):
        del self.itens[i]

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


class ListCtrl(Janela):
    """Lista de uma coluna (so o que a janela usa), com os itens em
    `itens` como no ListBox falso."""

    def __init__(self, *a, **k):
        super().__init__()
        self.itens, self.sel = [], -1

    def InsertColumn(self, *a, **k):
        pass

    def SetColumnWidth(self, *a, **k):
        pass

    def GetClientSize(self):
        return types.SimpleNamespace(width=300, height=300)

    def InsertItem(self, i, texto):
        self.itens.insert(i, texto)

    def DeleteAllItems(self):
        self.itens, self.sel = [], -1

    def DeleteItem(self, i):
        del self.itens[i]

    def GetItemCount(self):
        return len(self.itens)

    def GetItemText(self, i):
        return self.itens[i]

    def SetItemText(self, i, texto):
        self.itens[i] = texto

    def GetFirstSelected(self):
        return self.sel

    def Select(self, i, ligar=True):
        assert 0 <= i < len(self.itens), (i, len(self.itens))
        if ligar:
            self.sel = i
        elif self.sel == i:
            self.sel = -1

    def Focus(self, i):
        pass

    def EnsureVisible(self, i):
        pass

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

    def WriteText(self, texto):
        self.valor += texto

    def SetInsertionPoint(self, i):
        pass

    def SetInsertionPointEnd(self):
        pass

    def GetFont(self):
        return Fonte()

    def SetFont(self, f):
        pass


class Button(Janela):
    def __init__(self, pai=None, *a, label="", **k):
        super().__init__()
        self.label = label or (a[1] if len(a) > 1 else "")
        self.visivel = True

    def SetDefault(self):
        pass

    def SetLabel(self, t):
        self.label = t

    def GetLabel(self):
        return self.label

    def Enable(self, v=True):
        self.ativo = v

    def Disable(self):
        self.ativo = False


class BoxSizer:
    def __init__(self, *a):
        pass

    def Add(self, *a, **k):
        pass


class WrapSizer(BoxSizer):
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

    def AppendSubMenu(self, submenu, rotulo):
        return MenuItem()


class MenuBar:
    def Append(self, *a):
        pass


TheClipboard = types.SimpleNamespace(Open=lambda: False)
