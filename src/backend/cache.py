from annotationlib import Format
from typing import Callable, Awaitable, Any
from time import monotonic
from inspect import signature
from collections import defaultdict

import celpy.celtypes

class TTLCache[T, U]:
    def __init__(self, max_size: int = 1024, ttl: int = 60):
        self.max_size = max_size
        self.ttl = ttl

        self._cache: dict[T, tuple[U, float]] = {}

    def expire(self, time: float = None):
        if not time: time = monotonic()
        keys = [k for k, (_, t) in self._cache.items() if t + self.ttl <= time]
        for key in keys:
            self._cache.pop(key)

    def get(self, key: T, default: U = None) -> U | None:
        self.expire()
        k = self.make_hashable(key)
        if k in self._cache:
            return self._cache[k][0]
        return default

    def set(self, key: T, value: U):
        if len(self._cache) >= self.max_size and self.make_hashable(key) not in self._cache:
            self._cache.pop(next(iter(self._cache)))

        self._cache[self.make_hashable(key)] = value, monotonic()

    def invalidate(self, key: T):
        if key in self._cache:
            del self._cache[key]

    def clear(self, predicate: Callable[[T, U], bool] | None = None):
        if predicate is None:
            self._cache.clear()
            return
        keys = [k for k, (v, _) in self._cache.items() if predicate(k, v)]
        for key in keys:
            self._cache.pop(key)

    def make_hashable(self, stuff):
        if isinstance(stuff, (list, tuple)):
            return tuple(self.make_hashable(s) for s in stuff)
        elif isinstance(stuff, (dict, celpy.celtypes.MapType)):
            return tuple((k, self.make_hashable(v)) for k, v in stuff.items())
        elif getattr(stuff, "__hash__"):
            return stuff
        return id(stuff)

    def cache(self, arguments: list[str] = None) -> Callable[[Callable[..., U]], Callable[..., U]]:
        def wrapper(function: Callable[..., U]) -> Callable[..., U]:
            sig = signature(function, annotation_format=Format.STRING)
            if arguments is None:
                args = []
                for name, _ in sig.parameters.items():
                    if name != "self":
                        args.append(name)
            else:
                args = arguments

            def call(*cargs: Any, **kwargs: Any) -> U:
                key_parts = []
                bound = sig.bind(*cargs, **kwargs)
                bound.apply_defaults()

                for argn in args:
                    if argn in bound.arguments:
                        key_parts.append(bound.arguments[argn])

                if value := self.get(key_parts):
                    return value
                value = function(*cargs, **kwargs)
                self.set(key_parts, value)
                return value
            return call
        return wrapper

    def cache_async(self, arguments: list[str] = None) -> Callable[[Callable[..., Awaitable[U]]], Callable[..., Awaitable[U]]]:
        def wrapper(function: Callable[..., Awaitable[U]]) -> Callable[..., Awaitable[U]]:
            sig = signature(function, annotation_format=Format.STRING)
            if arguments is None:
                args = []
                for name, _ in sig.parameters.items():
                    if name != "self":
                        args.append(name)
            else:
                args = arguments

            async def call(*cargs: Any, **kwargs: Any) -> U:
                bound = sig.bind(*cargs, **kwargs)
                bound.apply_defaults()

                key_parts = []
                for argn in args:
                    if argn in bound.arguments:
                        key_parts.append(bound.arguments[argn])

                cache_key = self.make_hashable(key_parts)

                if value := self.get(cache_key):
                    return value
                value = await function(*cargs, **kwargs)
                self.set(cache_key, value)
                return value
            return call
        return wrapper
