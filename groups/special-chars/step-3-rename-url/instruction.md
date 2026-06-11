Edit src/patterns.py: rename `URL_RE` to `URL_PATTERN`.

Rename both:
1. The variable definition (on the `URL_RE = r'...'` line)
2. The reference in `compile_all()` (`re.compile(URL_RE)`)

Use the exact same name `URL_PATTERN` for both.
