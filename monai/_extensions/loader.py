# Copyright 2020 - 2021 MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from glob import glob
from os import makedirs, path

from contextlib import contextmanager
from threading import Timer
from _thread import interrupt_main

from torch import cuda
from torch.utils.cpp_extension import load

@contextmanager
def timeout(time, message):
    try:
        timer = Timer(time, interrupt_main)
        timer.daemon = True
        yield timer.start()
    except KeyboardInterrupt as e:
        if timer.is_alive():
            raise e
        raise TimeoutError(message)

dir_path = path.dirname(path.realpath(__file__))

def load_module(module_name, defines=None, verbose_build=False, build_timeout=30):
    """
    Handles the loading of c++ extention modules.

    Args:
        module_name: Name of the module to load. Must match the name of the relevant source directory in the _extensions directory.
        defines: Dictionary containing names and values of compilation defines.
        verbose_build: Set to true to enable build logging.
        build_timeout: Time in seconds before the build will throw an exception to prevent hanging.
    """

    # Ensuring named module exists in _extensions directory.
    module_dir = path.join(dir_path, module_name)
    assert path.exists(module_dir), f"No extention module named {module_name}"

    # Naming build.
    build_tag = "" if defines is None else "_".join(str(v) for v in defines.values())
    build_name = "build" if build_tag == "" else f"build_{build_tag}"
    module_name = module_name if build_tag == "" else f"{module_name}_{build_tag}"
    build_dir = path.join(module_dir, "build", build_name)

    # Ensuring build directory exists.
    if not path.exists(build_dir):
        makedirs(build_dir)

    # Gathering source files.
    source = glob(path.join(module_dir, "**/*.cpp"), recursive=True)
    if cuda.is_available:
        source += glob(path.join(module_dir, "**/*.cu"), recursive=True)

    # Constructing compilation argument list.
    define_args = [] if defines is None else [f"-D {key}={defines[key]}" for key in defines]

    # Ninja may be blocked by something out of our control.
    # This will error if the build takes longer than usual.
    with timeout(build_timeout, "Build appears to be blocked. Is there a stopped proccess building the same extention?"):

        # This will either run the build or return the existing .so object.
        module = load(
            name=module_name,
            sources=source,
            extra_cflags=define_args,
            extra_cuda_cflags=define_args,
            build_directory=build_dir,
            verbose=verbose_build,
        )

    return module
