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

from typing import Optional

import torch

from monai.metrics.utils import do_metric_reduction
from monai.utils import MetricReduction

from .metric import CumulativeIterationMetric


class CumulativeAverage(CumulativeIterationMetric):
    """
    Cumulatively record data value and aggregate for the average value.
    It supports single class or multi-class data, for example,
    value can be 0.44 (like loss) or [0.3, 0.4] (like metrics of 2 classes).
    It also supports distributed data parallel, sync data when aggregating.
    For example, recording loss value and compute the oveall average value in every 5 iterations:

    .. code-block:: python

        metric = CumulativeAverage()
        for i, d in enumerate(dataloader):
            loss = ...
            metric(loss)
            if i % 5 == 0:
                print(f"cumulative average of loss: {metric.aggregate()}")
        metric.reset()

    """

    def __init__(self) -> None:
        super().__init__()
        self.sum = None
        self.not_nans = None

    def reset(self):
        """
        Reset all the running status, including buffers, sum, not nans count, etc.

        """
        super().reset()
        self.sum = None
        self.not_nans = None

    def _compute_tensor(self, value: torch.Tensor, y: Optional[torch.Tensor] = None):
        while value.ndim < 2:
            value = value.unsqueeze(0)
        return value

    def aggregate(self):  # type: ignore
        """
        Sync data from all the ranks and compute the average value with previous sum value.

        """
        data = self.get_buffer()
        if not isinstance(data, torch.Tensor):
            raise ValueError("the data to aggregate must be PyTorch Tensor.")

        # do metric reduction
        f, not_nans = do_metric_reduction(data, reduction=MetricReduction.SUM_BATCH)
        # clear the buffer for next update
        super().reset()
        self.sum = f if self.sum is None else (self.sum + f)
        self.not_nans = not_nans if self.not_nans is None else (self.not_nans + not_nans)

        return self.sum / self.not_nans
