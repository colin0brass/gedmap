# Use metaclass for NoNewAttrs
class NoNewAttrs(type):
    def __call__(cls, *args, **kwargs):
        obj = type.__call__(cls, *args, **kwargs)
        obj._initialized = True
        return obj

# StrictNoNewAttrs should be a base class, not a metaclass
class StrictNoNewAttrs:
    def __setattr__(self, name, value):
        if not hasattr(self, '_initialized') or not self._initialized:
            object.__setattr__(self, name, value)
        else:
            if hasattr(self, name):
                object.__setattr__(self, name, value)
            else:
                raise AttributeError(f"Cannot add new attribute '{name}' to {self.__class__.__name__}")

class StrictNoNewAttrs(type):
    def __call__(cls, *args, **kwargs):
        obj = type.__call__(cls, *args, **kwargs)
        obj._initialized = True
        return obj

    def __setattr__(cls, name, value):
        # Prevent adding new class attributes after initialization
        if hasattr(cls, name):
            super().__setattr__(name, value)
        else:
            raise AttributeError(f"Cannot add new class attribute '{name}' to {cls.__name__}")

# To block new instance attributes, add this to your classes:
class NoNewInstanceAttrs:
    def __setattr__(self, name, value):
        if not hasattr(self, '_initialized') or not self._initialized:
            object.__setattr__(self, name, value)
        else:
            if hasattr(self, name):
                object.__setattr__(self, name, value)
            else:
                raise AttributeError(f"Cannot add new attribute '{name}' to {self.__class__.__name__}")