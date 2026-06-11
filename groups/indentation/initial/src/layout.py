"""Layout module — exercise indentation-sensitive edits in Python."""


def outer():
    """Outer function with nested logic."""
    x = 1
    if x > 0:
        print("positive")
    else:
        print("non-positive")
    return x


class Container:
    """Simple container with one method."""

    def __init__(self):
        self.items = []

    def add(self, item):
        if item is not None:
            self.items.append(item)
        return len(self.items)
