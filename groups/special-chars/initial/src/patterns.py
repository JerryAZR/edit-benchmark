"""Regex pattern library — exercise special character handling in edits."""

import re

# Email validation
EMAIL_RE = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

# Phone number (US)
PHONE_RE = r'\d{3}[-.]?\d{3}[-.]?\d{4}'

# URL matching
URL_RE = r'https?://(?:www\.)?[\w.-]+\.\w+(?:/[^\s]*)?'

# SQL inline comment
SQL_COMMENT = r'/\*.*?\*/'

# SQL single-quoted string
SQL_STRING = r"'(?:[^'\\]|\\.)*'"

# Filesystem path (Windows + Unix)
PATH_RE = r'(?:[a-zA-Z]:\\|\\)?(?:[\w.-]+\\)*[\w.-]+'

# Markdown link
LINK_RE = r'\[([^\]]+)\]\(([^)]+)\)'

# HTML tag
HTML_TAG = r'<(\w+)[^>]*>.*?</\1>'


def compile_all() -> list[re.Pattern]:
    """Precompile all patterns for performance testing."""
    return [
        re.compile(EMAIL_RE),
        re.compile(PHONE_RE),
        re.compile(URL_RE),
        re.compile(SQL_COMMENT),
        re.compile(SQL_STRING),
        re.compile(PATH_RE),
        re.compile(LINK_RE),
        re.compile(HTML_TAG),
    ]
