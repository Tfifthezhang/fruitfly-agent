"""External service contracts remain protected until isolated trials are supplied."""
from .registration import definition


def definitions():
    return (definition(),)
