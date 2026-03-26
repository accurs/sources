def example(text: str):
    def decorator(func):
        func.__example__ = text
        if hasattr(func, '__func__'):
            func.__func__.__example__ = text
        return func
    return decorator
