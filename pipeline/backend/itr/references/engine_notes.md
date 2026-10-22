# Showing Indic text correctly

These are the problems that came up while shipping 13 Indian languages. Check
them before calling a language done.

## Shaping: conjuncts and vowel signs

Indic scripts need a text shaper (HarfBuzz or the platform's own text engine)
to join consonants and place vowel signs. A renderer that draws one glyph per
code point shows broken text, such as क ् ष instead of क्ष.

- cocos2d-x: a TTF Label and a BMFont Label do not shape. Route any text in a
  complex script, or any non-ASCII text, through `Label::createWithSystemFont`.
  Android, iOS and macOS shape system-font text correctly. Bundled TTFs show
  missing-glyph boxes for ✓, → and other symbols, so send those to the system
  font too.
- cocos2d-x: `Label::Overflow::SHRINK` is ignored for system-font labels. To
  fit text in one line, measure the label unconstrained and rebuild it at
  `size * room / width`.
- cocos2d-x: `setLineHeight` on a system-font label asserts ("Not supported
  system font!") and kills a debug build at launch. A release build skips the
  check silently, so testing only release builds hides it. Guard the call with
  `getLabelType() != Label::LabelType::STRING_TEXTURE`. `enableBold` on those
  labels only logs a kerning warning, which is harmless.
- Unity: the built-in Text and TextMeshPro do not shape Indic scripts unless you
  add a shaping plugin. Pre-shaped strings or a native text view are the usual
  workarounds.
- Web, Flutter, React Native and native Android or iOS views shape correctly.
  You only need fonts that cover the script.

## Right-to-left (Urdu, Kashmiri, Sindhi in Arabic script)

Use a bidi-aware renderer; system fonts on Android and iOS are. Align
paragraphs to the right for these languages. Digits and Latin acronyms inside
Urdu text are laid out by the bidi algorithm, so leave them as they are.

## Fonts

Android 7+ and iOS 13+ ship fonts for all tier 1 scripts. Ol Chiki (Santali)
and Meetei Mayek (Manipuri) may be missing on older Android phones. Bundle
Noto Sans Ol Chiki or Noto Sans Meetei Mayek, and test on a real low-end phone.

## Size and wrapping

- Indic text runs 10-40% longer than English and needs more line height
  because of vowel signs above and below the line. Use a line height of at
  least 1.3x the font size, and never use fixed-height text boxes.
- Lay screens out from measured label heights, not fixed y-offsets, or a
  longer language pushes text into the next element.
- Thai-style line breaking is not needed. Indic text breaks at spaces.

## Resource lists frozen at configure time

CMake, including cocos2d-x's own CMake, lists bundled resources when it
configures, not when it builds. A language file added later is silently left
out of the iOS and macOS bundle. Create a placeholder for every language up
front (`{"schemes": []}` or `{}`) and let it fall back to English, or re-run
CMake after adding a file. Android Gradle reading `Resources/` directly is not
affected.

## Falling back to English

Load English as the base and lay each language over it, field by field. A
half-finished translation then still shows complete screens, with English only
where the translation is missing. `itr.py apply --overlay` writes files shaped
for this.

## The language picker

- Show each language's own name in its own script, plus the English name.
- Remember the choice, and let the user change it from the main screen.
- If a chip or button shows a native name, make sure the widest one fits:
  "English", "தமிழ்" and "മലയാളം" are the usual offenders.
