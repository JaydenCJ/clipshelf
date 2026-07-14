"""Locale tests: one clippings file, eight device languages.

Kindle writes the metadata line in the device UI language, and a file that
outlived a language switch mixes locales freely. Each test feeds a real
metadata shape for one locale and asserts kind, location, page, and date.
"""

from clipshelf import Kind, parse_text
from clipshelf.locales import kind_of

from conftest import entry


def _one(title, meta, text="texto"):
    (c,) = parse_text(entry(title, meta, text)).clippings
    return c


def test_spanish_highlight():
    c = _one(
        "Cien años de soledad (Gabriel García Márquez)",
        "- Tu subrayado en la página 7 | posición 89-92 | Añadido el martes, 12 de marzo de 2024 21:30:15",
    )
    assert c.kind is Kind.HIGHLIGHT
    assert c.page == "7"
    assert (c.location.start, c.location.end) == (89, 92)
    assert (c.added.year, c.added.month, c.added.day) == (2024, 3, 12)
    assert c.added.hour == 21


def test_french_highlight():
    c = _one(
        "Le Petit Prince (Antoine de Saint-Exupéry)",
        "- Votre surlignement sur la page 12 | emplacement 145-147 | Ajouté le mardi 5 mars 2024 09:12:45",
    )
    assert c.kind is Kind.HIGHLIGHT
    assert c.page == "12"
    assert (c.location.start, c.location.end) == (145, 147)
    assert (c.added.month, c.added.day) == (3, 5)


def test_german_highlight_am_in_marker_does_not_mean_morning():
    # "Hinzugefügt am" contains the letters "am"; the hour must stay 21.
    c = _one(
        "Der Prozess (Franz Kafka)",
        "- Ihre Markierung bei Position 233-235 | Hinzugefügt am Dienstag, 5. März 2024 21:12:45",
    )
    assert c.kind is Kind.HIGHLIGHT
    assert (c.location.start, c.location.end) == (233, 235)
    assert c.added.hour == 21


def test_italian_highlight():
    c = _one(
        "Il nome della rosa (Umberto Eco)",
        "- La tua evidenziazione alla posizione 512-514 | Aggiunto in data martedì 5 marzo 2024 18:40:02",
    )
    assert c.kind is Kind.HIGHLIGHT
    assert (c.location.start, c.location.end) == (512, 514)
    assert (c.added.month, c.added.hour) == (3, 18)


def test_portuguese_highlight():
    c = _one(
        "Ensaio sobre a cegueira (José Saramago)",
        "- Seu destaque na página 33 | posição 410-412 | Adicionado: terça-feira, 5 de março de 2024 09:12:45",
    )
    assert c.kind is Kind.HIGHLIGHT
    assert c.page == "33"
    assert (c.location.start, c.location.end) == (410, 412)


def test_chinese_highlight_with_meridiem_markers():
    pm = _one(
        "三体 (刘慈欣)",
        "- 您在位置 #351-352的标注 | 添加于 2024年3月5日星期二 下午9:12:45",
    )
    assert pm.kind is Kind.HIGHLIGHT
    assert (pm.location.start, pm.location.end) == (351, 352)
    assert (pm.added.year, pm.added.month, pm.added.day) == (2024, 3, 5)
    assert pm.added.hour == 21  # 下午 9 = 21:00
    am = _one("三体 (刘慈欣)", "- 您在位置 #10-12的标注 | 添加于 2024年3月5日星期二 上午9:12:45")
    assert am.added.hour == 9


def test_japanese_highlight():
    c = _one(
        "こころ (夏目漱石)",
        "- 位置No. 152-155のハイライト | 追加日： 2024年4月2日火曜日 22:15:08",
    )
    assert c.kind is Kind.HIGHLIGHT
    assert (c.location.start, c.location.end) == (152, 155)
    assert (c.added.year, c.added.month, c.added.day) == (2024, 4, 2)
    assert (c.added.hour, c.added.minute, c.added.second) == (22, 15, 8)


def test_japanese_note_and_bookmark_kinds():
    note = _one("こころ (夏目漱石)", "- 位置No. 160のメモ | 追加日： 2024年4月2日火曜日 22:16:00")
    bookmark = _one("こころ (夏目漱石)", "- 位置No. 200のブックマーク | 追加日： 2024年4月3日水曜日 08:00:00", "")
    assert note.kind is Kind.NOTE
    assert bookmark.kind is Kind.BOOKMARK


def test_article_clip_kind_and_longest_keyword_wins():
    c = _one(
        "The Daily Gazette (gazette.example.test)",
        "- Clip This Article on Location 20-25 | Added on Monday, January 1, 2024 10:00:00 AM",
    )
    assert c.kind is Kind.CLIP
    # "clip this article" must not be shadowed by shorter matches.
    assert kind_of("- Clip This Article on Location 5 | ...") is Kind.CLIP
    assert kind_of("- Your Note on Location 5 | ...") is Kind.NOTE


def test_mixed_locale_file_parses_every_entry():
    raw = (
        entry("A (X)", "- Your Highlight on Location 1-2 | Added on Monday, January 1, 2024 10:00:00 AM", "a")
        + entry("B (Y)", "- Tu subrayado en la página 1 | posición 3-4 | Añadido el lunes, 1 de enero de 2024 10:00:00", "b")
        + entry("C (Z)", "- 位置No. 5-6のハイライト | 追加日： 2024年1月1日月曜日 10:00:00", "c")
    )
    result = parse_text(raw)
    assert [c.kind for c in result.clippings] == [Kind.HIGHLIGHT] * 3
    assert result.warnings == []
