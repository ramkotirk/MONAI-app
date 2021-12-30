# Copyright (c) MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import collections.abc
import inspect
import itertools
import random
import types
import warnings
from ast import literal_eval
from distutils.util import strtobool
from typing import Any, Callable, Optional, Sequence, Tuple, Union, cast

import numpy as np
import torch

from monai.utils.module import version_leq

__all__ = [
    "zip_with",
    "star_zip_with",
    "first",
    "issequenceiterable",
    "ensure_tuple",
    "ensure_tuple_size",
    "ensure_tuple_rep",
    "fall_back_tuple",
    "is_scalar_tensor",
    "is_scalar",
    "progress_bar",
    "get_seed",
    "set_determinism",
    "list_to_dict",
    "MAX_SEED",
    "copy_to_device",
    "ImageMetaKey",
    "is_module_ver_at_least",
    "has_option",
]

_seed = None
_flag_deterministic = torch.backends.cudnn.deterministic
_flag_cudnn_benchmark = torch.backends.cudnn.benchmark
MAX_SEED = np.iinfo(np.uint32).max + 1  # 2**32, the actual seed should be in [0, MAX_SEED - 1] for uint32


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


def issequenceiterable(obj: Any) -> bool:
    """
    Determine if the object is an iterable sequence and is not a string.
    """
    if isinstance(obj, torch.Tensor):
        return int(obj.dim()) > 0  # a 0-d tensor is not iterable
    return isinstance(obj, collections.abc.Iterable) and not isinstance(obj, (str, bytes))


def ensure_tuple(vals: Any) -> Tuple[Any, ...]:
    """
    Returns a tuple of `vals`.
    """
    if not issequenceiterable(vals):
        return (vals,)

    return tuple(vals)


def ensure_tuple_size(tup: Any, dim: int, pad_val: Any = 0) -> Tuple[Any, ...]:
    """
    Returns a copy of `tup` with `dim` values by either shortened or padded with `pad_val` as necessary.
    """
    new_tup = ensure_tuple(tup) + (pad_val,) * dim
    return new_tup[:dim]


def ensure_tuple_rep(tup: Any, dim: int) -> Tuple[Any, ...]:
    """
    Returns a copy of `tup` with `dim` values by either shortened or duplicated input.

    Raises:
        ValueError: When ``tup`` is a sequence and ``tup`` length is not ``dim``.

    Examples::

        >>> ensure_tuple_rep(1, 3)
        (1, 1, 1)
        >>> ensure_tuple_rep(None, 3)
        (None, None, None)
        >>> ensure_tuple_rep('test', 3)
        ('test', 'test', 'test')
        >>> ensure_tuple_rep([1, 2, 3], 3)
        (1, 2, 3)
        >>> ensure_tuple_rep(range(3), 3)
        (0, 1, 2)
        >>> ensure_tuple_rep([1, 2], 3)
        ValueError: Sequence must have length 3, got length 2.

    """
    if isinstance(tup, torch.Tensor):
        tup = tup.detach().cpu().numpy()
    if isinstance(tup, np.ndarray):
        tup = tup.tolist()
    if not issequenceiterable(tup):
        return (tup,) * dim
    if len(tup) == dim:
        return tuple(tup)

    raise ValueError(f"Sequence must have length {dim}, got {len(tup)}.")


def fall_back_tuple(
    user_provided: Any, default: Union[Sequence, np.ndarray], func: Callable = lambda x: x and x > 0
) -> Tuple[Any, ...]:
    """
    Refine `user_provided` according to the `default`, and returns as a validated tuple.

    The validation is done for each element in `user_provided` using `func`.
    If `func(user_provided[idx])` returns False, the corresponding `default[idx]` will be used
    as the fallback.

    Typically used when `user_provided` is a tuple of window size provided by the user,
    `default` is defined by data, this function returns an updated `user_provided` with its non-positive
    components replaced by the corresponding components from `default`.

    Args:
        user_provided: item to be validated.
        default: a sequence used to provided the fallbacks.
        func: a Callable to validate every components of `user_provided`.

    Examples::

        >>> fall_back_tuple((1, 2), (32, 32))
        (1, 2)
        >>> fall_back_tuple(None, (32, 32))
        (32, 32)
        >>> fall_back_tuple((-1, 10), (32, 32))
        (32, 10)
        >>> fall_back_tuple((-1, None), (32, 32))
        (32, 32)
        >>> fall_back_tuple((1, None), (32, 32))
        (1, 32)
        >>> fall_back_tuple(0, (32, 32))
        (32, 32)
        >>> fall_back_tuple(range(3), (32, 64, 48))
        (32, 1, 2)
        >>> fall_back_tuple([0], (32, 32))
        ValueError: Sequence must have length 2, got length 1.

    """
    ndim = len(default)
    user = ensure_tuple_rep(user_provided, ndim)
    return tuple(  # use the default values if user provided is not valid
        user_c if func(user_c) else default_c for default_c, user_c in zip(default, user)
    )


def is_scalar_tensor(val: Any) -> bool:
    return isinstance(val, torch.Tensor) and val.ndim == 0


def is_scalar(val: Any) -> bool:
    if isinstance(val, torch.Tensor) and val.ndim == 0:
        return True
    return bool(np.isscalar(val))


def progress_bar(index: int, count: int, desc: Optional[str] = None, bar_len: int = 30, newline: bool = False) -> None:
    """print a progress bar to track some time consuming task.

    Args:
        index: current status in progress.
        count: total steps of the progress.
        desc: description of the progress bar, if not None, show before the progress bar.
        bar_len: the total length of the bar on screen, default is 30 char.
        newline: whether to print in a new line for every index.
    """
    end = "\r" if not newline else "\r\n"
    filled_len = int(bar_len * index // count)
    bar = f"{desc} " if desc is not None else ""
    bar += "[" + "=" * filled_len + " " * (bar_len - filled_len) + "]"
    print(f"{index}/{count} {bar}", end=end)
    if index == count:
        print("")


def get_seed() -> Optional[int]:
    return _seed


def set_determinism(
    seed: Optional[int] = np.iinfo(np.uint32).max,
    use_deterministic_algorithms: Optional[bool] = None,
    additional_settings: Optional[Union[Sequence[Callable[[int], Any]], Callable[[int], Any]]] = None,
) -> None:
    """
    Set random seed for modules to enable or disable deterministic training.

    Args:
        seed: the random seed to use, default is np.iinfo(np.int32).max.
            It is recommended to set a large seed, i.e. a number that has a good balance
            of 0 and 1 bits. Avoid having many 0 bits in the seed.
            if set to None, will disable deterministic training.
        use_deterministic_algorithms: Set whether PyTorch operations must use "deterministic" algorithms.
        additional_settings: additional settings that need to set random seed.

    """
    if seed is None:
        # cast to 32 bit seed for CUDA
        seed_ = torch.default_generator.seed() % (np.iinfo(np.int32).max + 1)
        torch.manual_seed(seed_)
    else:
        seed = int(seed) % MAX_SEED
        torch.manual_seed(seed)

    global _seed
    _seed = seed
    random.seed(seed)
    np.random.seed(seed)

    if additional_settings is not None:
        additional_settings = ensure_tuple(additional_settings)
        for func in additional_settings:
            func(seed)

    if torch.backends.flags_frozen():
        warnings.warn("PyTorch global flag support of backends is disabled, enable it to set global `cudnn` flags.")
        torch.backends.__allow_nonbracketed_mutation_flag = True

    if seed is not None:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    else:  # restore the original flags
        torch.backends.cudnn.deterministic = _flag_deterministic
        torch.backends.cudnn.benchmark = _flag_cudnn_benchmark
    if use_deterministic_algorithms is not None:
        if hasattr(torch, "use_deterministic_algorithms"):  # `use_deterministic_algorithms` is new in torch 1.8.0
            torch.use_deterministic_algorithms(use_deterministic_algorithms)
        elif hasattr(torch, "set_deterministic"):  # `set_deterministic` is new in torch 1.7.0
            torch.set_deterministic(use_deterministic_algorithms)  # type: ignore
        else:
            warnings.warn("use_deterministic_algorithms=True, but PyTorch version is too old to set the mode.")


def list_to_dict(items):
    """
    To convert a list of "key=value" pairs into a dictionary.
    For examples: items: `["a=1", "b=2", "c=3"]`, return: {"a": "1", "b": "2", "c": "3"}.
    If no "=" in the pair, use None as the value, for example: ["a"], return: {"a": None}.
    Note that it will remove the blanks around keys and values.

    """

    def _parse_var(s):
        items = s.split("=", maxsplit=1)
        key = items[0].strip(" \n\r\t'")
        value = items[1].strip(" \n\r\t'") if len(items) > 1 else None
        return key, value

    d = {}
    if items:
        for item in items:
            key, value = _parse_var(item)

            try:
                if key in d:
                    raise KeyError(f"encounter duplicated key {key}.")
                d[key] = literal_eval(value)
            except ValueError:
                try:
                    d[key] = bool(strtobool(str(value)))
                except ValueError:
                    d[key] = value
    return d


def copy_to_device(
    obj: Any, device: Optional[Union[str, torch.device]], non_blocking: bool = True, verbose: bool = False
) -> Any:
    """
    Copy object or tuple/list/dictionary of objects to ``device``.

    Args:
        obj: object or tuple/list/dictionary of objects to move to ``device``.
        device: move ``obj`` to this device. Can be a string (e.g., ``cpu``, ``cuda``,
            ``cuda:0``, etc.) or of type ``torch.device``.
        non_blocking: when `True`, moves data to device asynchronously if
            possible, e.g., moving CPU Tensors with pinned memory to CUDA devices.
        verbose: when `True`, will print a warning for any elements of incompatible type
            not copied to ``device``.
    Returns:
        Same as input, copied to ``device`` where possible. Original input will be
            unchanged.
    """

    if hasattr(obj, "to"):
        return obj.to(device, non_blocking=non_blocking)
    if isinstance(obj, tuple):
        return tuple(copy_to_device(o, device, non_blocking) for o in obj)
    if isinstance(obj, list):
        return [copy_to_device(o, device, non_blocking) for o in obj]
    if isinstance(obj, dict):
        return {k: copy_to_device(o, device, non_blocking) for k, o in obj.items()}
    if verbose:
        fn_name = cast(types.FrameType, inspect.currentframe()).f_code.co_name
        warnings.warn(f"{fn_name} called with incompatible type: " + f"{type(obj)}. Data will be returned unchanged.")

    return obj


class ImageMetaKey:
    """
    Common key names in the meta data header of images
    """

    FILENAME_OR_OBJ = "filename_or_obj"
    PATCH_INDEX = "patch_index"


def has_option(obj, keywords: Union[str, Sequence[str]]) -> bool:
    """
    Return a boolean indicating whether the given callable `obj` has the `keywords` in its signature.
    """
    if not callable(obj):
        return False
    sig = inspect.signature(obj)
    return all(key in sig.parameters for key in ensure_tuple(keywords))


def is_module_ver_at_least(module, version):
    """Determine if a module's version is at least equal to the given value.

    Args:
        module: imported module's name, e.g., `np` or `torch`.
        version: required version, given as a tuple, e.g., `(1, 8, 0)`.
    Returns:
        `True` if module is the given version or newer.
    """
    test_ver = ".".join(map(str, version))
    return module.__version__ != test_ver and version_leq(test_ver, module.__version__)
