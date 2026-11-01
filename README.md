# baweri-content

Content for the Baweri app: the book list, and the books' text. The app downloads these files through jsDelivr, for example:

```
https://cdn.jsdelivr.net/gh/baweri/baweri-content@main/books/index.json
```

Everything here is public, and the app reads it as is. Change a file and push to `main`, and the app picks it up. jsDelivr can take up to 12 hours to show a change; to make it show right away, open the file's address with `purge` in place of `cdn`, e.g. `https://purge.jsdelivr.net/gh/baweri/baweri-content@main/books/index.json`.

## `books/index.json`: the book list

```json
{
  "version": 1,
  "books": [
    {
      "id": 3001,
      "title": "Sözler",
      "author": "Bediüzzaman Said Nursî",
      "language": "tr",
      "category": "tasavvuf",
      "cover": "https://…/cover.jpg",
      "hasText": true
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `id` | Unique number. Never reuse or change one: the app saves reading progress and bookmarks by it. |
| `title` | Book title, written as it should appear (not all in capitals). |
| `author` | Author or publisher, or `null`. |
| `language` | `tr`, `en`, `ar`, `ku` (Kurmancî), `ckb` (Soranî), `nb` (Norsk). |
| `category` | One of the values below, or `null`. A book without one shows only under "All". |
| `cover` | Cover image address, or `null` for a plain cover. |
| `hasText` | `true` once the book's text is in `books/{id}/` and it can be read in the app. |

**Categories:** `fikih`, `hadis`, `ilmihal`, `tefsir`, `siyer`, `tasavvuf` (religious books); `edebiyat`, `tarih`, `cocuk` (other books). A new category also needs adding to the app.

## `books/{id}/`: a book's text

Each book is split into chapters, so the app only downloads what's being read.

**`books/{id}/book.json`**: the table of contents. `part` groups chapters under a part of the book, when it has parts. `version` goes up by one whenever any of the book's chapters change: the app keeps chapters on the phone and only downloads them again for a new version. The converter raises it on every run; when editing chapters by hand, raise it yourself.

```json
{
  "id": 6016,
  "title": "Hadislerle İslam 1",
  "version": 2,
  "chapters": [
    { "n": 8, "title": "İstiâze: Âlemlerin Rabbine Sığınmak" },
    { "n": 12, "title": "Allah: Âlemlerin Rabbi", "part": "1. Bölüm: Allah, Âlem, İnsan ve Din" }
  ]
}
```

**`books/{id}/{n}.json`**: one chapter, as a list of blocks, and its footnotes.

```json
{
  "n": 8,
  "title": "İstiâze: Âlemlerin Rabbine Sığınmak",
  "blocks": [
    { "type": "arabic", "text": "قَالَ أَبُو هُرَيْرَةَ: إِنَّ رَسُولَ اللَّهِ ﷺ كَانَ يَدْعُو…" },
    { "type": "paragraph", "text": "Ebû Hüreyre, Allah Resûlü’nün (sav) şöyle dua ettiğini söylemektedir:" },
    { "type": "paragraph", "parts": [
      { "text": "“Allah’ım! Bozgunculuktan… sana sığınırım.”", "italic": true },
      { "note": "12" }
    ] },
    { "type": "source", "text": "(D1546 Ebû Dâvûd, Vitr, 32)" },
    { "type": "divider" }
  ],
  "notes": [{ "id": "12", "text": "Müslim, Salât, 222." }]
}
```

| Block | Shown as |
|---|---|
| `heading` | a heading inside the chapter |
| `paragraph` | body text |
| `arabic` | Arabic text, right to left, in the Qur'an font |
| `quote` | an indented quotation |
| `source` | a hadith's or quotation's source, small and grey |
| `divider` | a break between sections (no text) |
| `pageBreak` | what follows starts a new page, e.g. the text after a preface (no text) |
| `title` | where the chapter's title goes, if not at its top, e.g. after a preface that comes first (no text) |

A block has either `text` (plain) or `parts`, for text with italic or bold runs and footnote references: each part is `{ "text", "italic"?, "bold"?, "red"? }` or `{ "note": "<id>" }`, pointing at an entry in the chapter's `notes`.

An `arabic` block with `"center": true` is set in the middle of the line, as the book prints it (the Risale-i Nur's standalone Arabic); others run from the right.

`red` is for what the book itself prints in red, as the Risale-i Nur prints its Arabic: a part with `"red": true`, or an `arabic` block with `"red": true`. Other books leave it out, and their Arabic stays in the text's color.

The app draws everything with its own fonts and colors, so the text carries no formatting beyond italic and bold.

## Converting an EPUB

```
python3 tools/epub_to_book.py BOOK.epub BOOK_ID
```

Writes `books/BOOK_ID/` (table of contents, chapters, cover). Then set the book's `hasText` to `true` in `books/index.json`, its `cover` to `https://cdn.jsdelivr.net/gh/baweri/baweri-content@main/books/BOOK_ID/cover.jpg`, and check a few chapters. The script was built on Diyanet's EPUBs; other publishers' EPUBs may need it extended. It reads EPUB 2 (`toc.ncx`) as well as EPUB 3, tells Arabic paragraphs by their letters, leaves out pictures of text (some books set their Arabic as pictures) and printed tables of contents, and splits a book whose table of contents is a single entry at its top headings. Chapters are written without spacing, and covers should be shrunk before committing (`sips -s format jpeg -s formatOptions 75 -Z 900`), so the repository stays small enough for jsDelivr.
