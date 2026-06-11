Edit src/patterns.py: remove the SQL_COMMENT line entirely.

Delete this line:
```python
SQL_COMMENT = r'/\*.*?\*/'
```

Also remove `re.compile(SQL_COMMENT),` from the `compile_all()` function.
