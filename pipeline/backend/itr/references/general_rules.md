# How to translate this chunk

This file holds `items`, a list of `{"k", "ctx", "t"}`. `t` is English text
that a reader of an Indian app or website sees. `ctx` is the field it came
from, such as label, hint, button, documents, brief or title. Use it to judge
tone and length: a label stays short, a hint can be a sentence.

Write `{"items": [{"k": ..., "t": ...}, ...]}` to the path in `write_to`.
Keep every `k` unchanged and in the same order. Put the translation in `t`.
Leave out `ctx`. Do not add, merge, split or drop items.

## Keep these exactly as they are

- Placeholders and markup: `{0}`, `{name}`, `%s`, `%d`, `%1$s`, HTML tags, `\n`.
- Website addresses, e-mail addresses and links.
- Every number: phone and toll-free numbers, Aadhaar, account, IFSC, PAN, PIN
  codes, amounts, dates, percentages. Write digits as 0-9, the Western digits,
  in every language, including Urdu. People type these into forms that take
  Western digits.
- Acronyms people know in Latin letters: OTP, PAN, IFSC, UPI, KYC, e-KYC, DBT,
  BPL, APL, NFSA, PM-KISAN, SMS, PDF, ID.

## Names

- Product, app, portal and scheme names: transliterate them into the script so
  they read naturally. Keep any acronym inside them in Latin, so "APPSC
  portal" becomes APPSC followed by the word for portal.
- A button or menu label quoted from a website, such as 'Apply Online' or
  'Register', stays in English inside quotes. The reader has to find that exact
  English word on the screen.
- People and places in examples are transliterated, never replaced with other
  names.
- Government office titles are transliterated so the reader can say them at
  the counter: Tahsildar, Patwari, Talathi, Mamlatdar, BDO, Collector, Gram
  Panchayat. The language notes below give the usual local forms.

## Tone

Write for an ordinary person who may be elderly and may have had little
schooling. Use everyday spoken language, not heavy official vocabulary. Where
people really say the English word, write it in the script: online, form,
portal, login, mobile, bank, certificate, download, upload, app. Keep
instructions short and direct, in the form "do this".

"Gender" means sex (male or female). It is never the word for caste.

## Before you write

Check that you have the same number of items as the input and that every
number and placeholder came through. Write the whole file in ONE Write call,
as valid UTF-8 JSON with no `\u` escapes and nothing else in the file.
