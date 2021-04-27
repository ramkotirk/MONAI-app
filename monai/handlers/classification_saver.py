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

import logging
from typing import TYPE_CHECKING, Callable, Optional, List

import torch

from monai.data import CSVSaver
from monai.handlers.utils import evenly_divisible_all_gather, string_list_all_gather
from monai.utils import ImageMetaKey as Key
from monai.utils import exact_version, optional_import

idist, _ = optional_import("ignite", "0.4.4", exact_version, "distributed")
Events, _ = optional_import("ignite.engine", "0.4.4", exact_version, "Events")
if TYPE_CHECKING:
    from ignite.engine import Engine
else:
    Engine, _ = optional_import("ignite.engine", "0.4.4", exact_version, "Engine")


class ClassificationSaver:
    """
    Event handler triggered on completing every iteration to save the classification predictions as CSV file.
    If running in distributed data parallel, only saves CSV file in the specified rank.

    """

    def __init__(
        self,
        output_dir: str = "./",
        filename: str = "predictions.csv",
        overwrite: bool = True,
        batch_transform: Callable = lambda x: x,
        output_transform: Callable = lambda x: x,
        name: Optional[str] = None,
        save_rank: int = 0,
    ) -> None:
        """
        Args:
            output_dir: output CSV file directory.
            filename: name of the saved CSV file name.
            overwrite: whether to overwriting existing CSV file content. If we are not overwriting,
                then we check if the results have been previously saved, and load them to the prediction_dict.
            batch_transform: a callable that is used to transform the
                ignite.engine.batch into expected format to extract the meta_data dictionary.
            output_transform: a callable that is used to transform the
                ignite.engine.output into the form expected model prediction data.
                The first dimension of this transform's output will be treated as the
                batch dimension. Each item in the batch will be saved individually.
            name: identifier of logging.logger to use, defaulting to `engine.logger`.
            save_rank: only the handler on specified rank will save to CSV file in multi-gpus validation,
                default to 0.

        """
        self._expected_rank: bool = idist.get_rank() == save_rank
        self.saver = CSVSaver(output_dir, filename, overwrite)
        self.output_dir = output_dir
        self.filename = filename
        self.overwrite = overwrite
        self.batch_transform = batch_transform
        self.output_transform = output_transform

        self.logger = logging.getLogger(name)
        self._name = name
        self._outputs: List[torch.Tensor] = []
        self._filenames: List[str] = []

    def attach(self, engine: Engine) -> None:
        """
        Args:
            engine: Ignite Engine, it can be a trainer, validator or evaluator.
        """
        if self._name is None:
            self.logger = engine.logger
        if not engine.has_event_handler(self, Events.ITERATION_COMPLETED):
            engine.add_event_handler(Events.ITERATION_COMPLETED, self)
        if not engine.has_event_handler(self.saver.finalize, Events.COMPLETED):
            engine.add_event_handler(Events.COMPLETED, self._finalize)

    def __call__(self, engine: Engine) -> None:
        """
        This method assumes self.batch_transform will extract metadata from the input batch.

        Args:
            engine: Ignite Engine, it can be a trainer, validator or evaluator.
        """
        filenames = self.batch_transform(engine.state.batch).get(Key.FILENAME_OR_OBJ, None)
        if filenames is not None:
            self._filenames.extend(filenames)
        outputs = self.output_transform(engine.state.output)
        if outputs is not None:
            self._outputs.append(outputs)

    def _finalize(self, engine: Engine) -> None:
        """
        All gather classification results from ranks and save to CSV file.

        Args:
            engine: Ignite Engine, it can be a trainer, validator or evaluator.
        """
        outputs = evenly_divisible_all_gather(torch.cat(self._outputs, dim=0))
        filenames = string_list_all_gather(self._filenames)
        if len(filenames) == 0:
            meta_dict = None
        elif len(filenames) != len(outputs):
            raise RuntimeError(f"filenames length: {len(filenames)} doesn't match outputs length: {len(outputs)}.")
        else:
            meta_dict = {Key.FILENAME_OR_OBJ: filenames}

        # save to CSV file only in the expected rank
        if self._expected_rank:
            saver = CSVSaver(self.output_dir, self.filename, self.overwrite)
            saver.save_batch(outputs, meta_dict)
            saver.finalize()
        # reset cache
        self._outputs = []
        self._filenames = []
