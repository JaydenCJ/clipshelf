"""Locale tables for the metadata line of My Clippings.txt.

Kindle writes the metadata line ("- Your Highlight on page 23 | Location
351-352 | Added on ...") in the device's UI language, and a clippings file
that has traveled between firmware versions or device languages routinely
mixes several of them. Rather than one regex per locale, clipshelf keeps
small keyword tables (kind words, page/location markers, month names,
am/pm markers) and lets the parser combine them, so a single pass handles
English, Spanish, French, German, Italian, Portuguese, Chinese, and
Japanese entries in the same file.

All matching is case-insensitive on casefolded text.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from .model import Kind

# --- kind keywords -----------------------------------------------------
# Longest-match wins so "clip this article" is checked before "note" etc.
# Keys are casefolded substrings searched for in the metadata line.
KIND_KEYWORDS: Dict[str, Kind] = {
    # English (current and pre-2011 firmware, which drops "Your"; entries
    # without a page skip "on" too: "- Highlight Loc. 1085-86 | Added on ...")
    "your highlight": Kind.HIGHLIGHT,
    "highlight on": Kind.HIGHLIGHT,
    "highlight loc": Kind.HIGHLIGHT,
    "your note": Kind.NOTE,
    "note on": Kind.NOTE,
    "note loc": Kind.NOTE,
    "your bookmark": Kind.BOOKMARK,
    "bookmark on": Kind.BOOKMARK,
    "bookmark loc": Kind.BOOKMARK,
    "clip this article": Kind.CLIP,
    # Spanish
    "tu subrayado": Kind.HIGHLIGHT,
    "tu nota": Kind.NOTE,
    "tu marcador": Kind.BOOKMARK,
    # French
    "votre surlignement": Kind.HIGHLIGHT,
    "votre note": Kind.NOTE,
    "votre signet": Kind.BOOKMARK,
    # German
    "ihre markierung": Kind.HIGHLIGHT,
    "ihre notiz": Kind.NOTE,
    "ihr lesezeichen": Kind.BOOKMARK,
    # Italian
    "la tua evidenziazione": Kind.HIGHLIGHT,
    "la tua nota": Kind.NOTE,
    "il tuo segnalibro": Kind.BOOKMARK,
    # Portuguese
    "seu destaque": Kind.HIGHLIGHT,
    "sua nota": Kind.NOTE,
    "seu marcador": Kind.BOOKMARK,
    # Chinese (simplified)
    "的标注": Kind.HIGHLIGHT,
    "的笔记": Kind.NOTE,
    "的书签": Kind.BOOKMARK,
    "文章剪切": Kind.CLIP,
    # Japanese
    "のハイライト": Kind.HIGHLIGHT,
    "のメモ": Kind.NOTE,
    "のブックマーク": Kind.BOOKMARK,
}

# --- page / location markers -------------------------------------------
# Words that introduce a page number. CJK page markers follow the number
# instead ("23ページ", "第 23 页"); the parser handles both orders.
PAGE_WORDS: Tuple[str, ...] = (
    "page",       # en
    "página",     # es, pt
    "pagina",     # it (and es/pt typed without the accent)
    "seite",      # de
    "la página",  # es long form
)
PAGE_SUFFIXES: Tuple[str, ...] = ("ページ", "页")

# Words that introduce a location range.
LOCATION_WORDS: Tuple[str, ...] = (
    "location",      # en (current firmware)
    "loc.",          # en (pre-2011 firmware: "Loc. 351-52")
    "posición",      # es
    "posicion",      # es without accent
    "position",      # de, fr (older French firmware)
    "posizione",     # it
    "posição",       # pt
    "posicao",       # pt without accents
    "emplacement",   # fr
    "位置no.",       # ja ("位置No. 351-352")
    "位置",          # zh ("位置 #351-352")
)

# --- "Added on" markers --------------------------------------------------
# The date segment starts with one of these; everything after it is fed to
# the date parser.
ADDED_WORDS: Tuple[str, ...] = (
    "added on",          # en
    "añadido el",        # es
    "anadido el",        # es without accent
    "ajouté le",         # fr
    "ajoute le",         # fr without accent
    "hinzugefügt am",    # de
    "hinzugefugt am",    # de without umlaut
    "aggiunto in data",  # it
    "adicionado:",       # pt
    "adicionado em",     # pt variant
    "添加于",            # zh
    "追加日：",          # ja (full-width colon)
    "追加日:",           # ja (ascii colon)
)

# --- month names ---------------------------------------------------------
# One flat casefolded name -> month-number table across every supported
# Latin-script locale. Collisions across languages agree on the number
# (e.g. "mars" fr = March), so a flat dict is safe.
MONTH_NAMES: Dict[str, int] = {}


def _months(*names: str) -> None:
    for i, name in enumerate(names, start=1):
        MONTH_NAMES[name.casefold()] = i


# English
_months("january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december")
# Spanish
_months("enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
# French
_months("janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre")
# German
_months("januar", "februar", "märz", "april", "mai", "juni",
        "juli", "august", "september", "oktober", "november", "dezember")
# Italian
_months("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")
# Portuguese
_months("janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
# Common unaccented variants typed by older firmware
MONTH_NAMES["fevrier"] = 2
MONTH_NAMES["aout"] = 8
MONTH_NAMES["decembre"] = 12
MONTH_NAMES["marz"] = 3
MONTH_NAMES["marco"] = 3

# --- am/pm markers -------------------------------------------------------
# Marker -> True when it means PM. CJK markers precede the time; English
# ones follow it. The date parser only uses these to adjust the hour.
PM_MARKERS: Dict[str, bool] = {
    "am": False,
    "a.m.": False,
    "pm": True,
    "p.m.": True,
    "上午": False,  # zh: morning
    "下午": True,   # zh: afternoon
    "午前": False,  # ja: morning
    "午後": True,   # ja: afternoon
}


def kind_of(meta_line: str) -> Optional[Kind]:
    """Detect the clipping kind from a casefolded metadata line.

    Returns None when no keyword matches; longer keywords win so that
    "clip this article" is never mistaken for a plain note.
    """
    folded = meta_line.casefold()
    best: Optional[Kind] = None
    best_len = 0
    for keyword, kind in KIND_KEYWORDS.items():
        if keyword in folded and len(keyword) > best_len:
            best = kind
            best_len = len(keyword)
    return best
