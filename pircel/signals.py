# -*- coding: utf-8 -*-
import blinker


def namespace(name):
    def inner_func(signal, *args, **kwargs):
        namespace_signal = 'possel_{}_{}'.format(name, signal)
        return blinker.signal(namespace_signal, *args, **kwargs)
    return inner_func
