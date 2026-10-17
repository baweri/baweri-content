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

**`books/{id}/book.json`**: the table of contents.

```json
{
  "id": 3001,
  "chapters": [
    { "n": 1, "title": "Birinci Söz" },
    { "n": 2, "title": "İkinci Söz" }
  ]
}
```

**`books/{id}/{n}.json`**: one chapter, as a list of blocks.

```json
{
  "n": 1,
  "title": "Birinci Söz",
  "blocks": [
    { "type": "heading", "text": "Bismillah her hayrın başıdır." },
    { "type": "paragraph", "text": "Biz dahi başta ona başlarız…" },
    { "type": "arabic", "text": "بِسْمِ اللّٰهِ الرَّحْمٰنِ الرَّحِيمِ" },
    { "type": "quote", "text": "…" },
    { "type": "note", "text": "…" }
  ]
}
```

| Block | Shown as |
|---|---|
| `heading` | a heading inside the chapter |
| `paragraph` | body text |
| `arabic` | Arabic text, right to left, in the Qur'an font |
| `quote` | an indented quotation |
| `note` | a smaller footnote |

The app draws everything with its own fonts and colors, so the text has no formatting of its own: only plain text in these blocks.
