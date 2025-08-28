class NoNewAttrs(type):
    def __setattr__(cls, name, value):
        if not hasattr(cls, name):
            raise AttributeError(f"Cannot create new class attribute '{name}'")
        super().__setattr__(name, value)