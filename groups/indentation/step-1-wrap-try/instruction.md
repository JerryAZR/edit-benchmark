Edit src/layout.py: wrap the body of `outer()` in a try/except block.

The function should become:

```python
def outer():
    """Outer function with nested logic."""
    try:
        x = 1
        if x > 0:
            print("positive")
        else:
            print("non-positive")
        return x
    except Exception:
        return -1
```

The docstring stays at its current indentation (4 spaces). Everything between the docstring and the existing return needs 4 more spaces of indentation. Add the try/except lines.
