Edit src/handlers.py: inside handle_event(), add a log call before `result = process(data)`:

```python
    print(f"[EVENT] received: {data}")
```

Do not modify handle_request, handle_response, handle_notification, or handle_alert.
