Edit src/layout.py: add a `remove()` method to the `Container` class.

Add this method after `add()` at the same indentation level:

```python
    def remove(self, item):
        if item in self.items:
            self.items.remove(item)
        return len(self.items)
```

Do not change any existing methods.
