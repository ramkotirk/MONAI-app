# Copyright 2020 MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import itertools
from collections.abc import Iterable

import numpy as np
import torch


def zip_with(op, *vals, mapfunc=map):
    """
    Map `op`, using `mapfunc`, to each tuple derived from zipping the iterables in `vals`.
    """
    return mapfunc(op, zip(*vals))


def star_zip_with(op, *vals):
    """
    Use starmap as the mapping function in zipWith.
    """
    return zip_with(op, *vals, mapfunc=itertools.starmap)


def first(iterable, default=None):
    """
    Returns the first item in the given iterable or `default` if empty, meaningful mostly with 'for' expressions.
    """
    for i in iterable:
        return i
    return default


def issequenceiterable(obj):
    """
    Determine if the object is an iterable sequence and is not a string
    """
    return isinstance(obj, Iterable) and not isinstance(obj, str)


def ensure_tuple(vals):
    """Returns a tuple of `vals`"""
    if not issequenceiterable(vals):
        vals = (vals,)

    return tuple(vals)


def ensure_tuple_size(tup, dim):
    """Returns a copy of `tup` with `dim` values by either shortened or padded with zeros as necessary."""
    tup = tuple(tup) + (0,) * dim
    return tup[:dim]


def ensure_tuple_rep(tup, dim, require_matched_size=False):
    """
    Returns a copy of `tup` with `dim` values by either shortened or duplicated input.
    if require_matched_size is True, then the input tup must be non-iterable and have length equal to dim
    """
    if not issequenceiterable(tup):
        return (tup,) * dim
    elif not require_matched_size or len(tup) >= dim:
        return tuple(tup)[:dim]

    raise ValueError(f"sequence must have length {dim}, got length {len(tup)}.")


def is_scalar_tensor(val):
    if torch.is_tensor(val) and val.ndim == 0:
        return True
    return False


def is_scalar(val):
    if torch.is_tensor(val) and val.ndim == 0:
        return True
    return np.isscalar(val)


def process_bar(index, count, bar_len=30, newline=False):
    """print a process bar to track some time consuming task.

    Args:
        index (int): current satus in process.
        count (int): total steps of the process.
        bar_len(int): the total length of the bar on screen, default is 30 char.
        newline (bool): whether to print in a new line for every index.
    """
    end = "\r" if newline is False else "\r\n"
    filled_len = int(bar_len * index // count)
    bar = "[" + "=" * filled_len + " " * (bar_len - filled_len) + "]"
    print(f"{index}/{count} {bar:s}  ", end=end)
    if index == count:
        print("")
