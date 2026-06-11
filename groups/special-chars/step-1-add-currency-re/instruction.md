Edit src/patterns.py: add a new CURRENCY_RE pattern right after the EMAIL_RE line.

```python
CURRENCY_RE = r'\$?[+-]?\d+(?:\.\d{2})?'
```

Insert it between EMAIL_RE and PHONE_RE.
