Edit src/layout.py: nest the `outer()` function inside a new class called `Wrapper`.

Add `class Wrapper:` before `outer()` and indent the entire `outer()` function (including docstring and body) by 4 additional spaces. 

The file should end up with:

```python
class Wrapper:
    def outer():
        ...
```

Where `outer` is at 4-space indent inside the class. Everything in `outer` also gets 4 extra spaces.
