__all__ = ['getwriterdict', 'registerwriter']

import os
from warnings import warn

_writers = []
def testwriter(writer, *args, **kwds):
    try:
        writer(*args, **kwds)
        return True
    except:
        return False

def registerwriter(name, writer):
    global _writers
    _writers.insert(0, (name, writer))

def getwriterdict():
    return dict(_writers)