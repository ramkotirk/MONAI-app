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

import torch

from monai.metrics.functional.meandice import compute_meandice


class DiceMetric:
    """
    Compute average Dice loss between two tensors. It can support both multi-classes and multi-labels tasks.
    Input logits `input` (BNHW[D] where N is number of classes) is compared with ground truth `target` (BNHW[D]).
    Axis N of `input` is expected to have logit predictions for each class rather than being image channels,
    while the same axis of `target` can be 1 or N (one-hot format). The `smooth` parameter is a value added to the
    intersection and union components of the inter-over-union calculation to smooth results and prevent divide by 0,
    this value should be small. The `include_background` class attribute can be set to False for an instance of
    DiceLoss to exclude the first category (channel index 0) which is by convention assumed to be background.
    If the non-background segmentations are small compared to the total image size they can get overwhelmed by
    the signal from the background so excluding it in such cases helps convergence.

    """

    def __init__(
        self,
        include_background: bool = True,
        to_onehot_y: bool = False,
        mutually_exclusive: bool = False,
        sigmoid: bool = False,
        logit_thresh: float = 0.5,
        reduction: str = "mean",
    ):
        super().__init__()

        if reduction not in ["none", "mean", "sum", "mean_batch", "sum_batch"]:
            raise ValueError(f"reduction={reduction} is invalid. Valid options are: none, mean or sum.")

        self.include_background = include_background
        self.to_onehot_y = to_onehot_y
        self.mutually_exclusive = mutually_exclusive
        self.sigmoid = sigmoid
        self.logit_thresh = logit_thresh
        self.reduction = reduction

        self.not_nans = None  # keep track for valid elements in the batch

    def __call__(self, input: torch.Tensor, target: torch.Tensor):

        # compute dice (BxC) for each channel for each batch
        f = compute_meandice(
            y_pred=input,
            y=target,
            include_background=self.include_background,
            to_onehot_y=self.to_onehot_y,
            mutually_exclusive=self.mutually_exclusive,
            sigmoid=self.sigmoid,
            logit_thresh=self.logit_thresh,
        )

        # some dice elements might be Nan (if ground truth y was missing (zeros))
        # we need to account for it

        nans = torch.isnan(f)
        not_nans = (~nans).float()
        f[nans] = 0

        t_zero = torch.zeros(1, device=f.device, dtype=torch.float)

        if self.reduction == "mean":
            # 2 steps, first, mean by  batch (accounting for nans), then by channel

            not_nans = not_nans.sum(dim=0)
            f = torch.where(not_nans > 0, f.sum(dim=0) / not_nans, t_zero)  # batch average

            not_nans = not_nans.sum()
            f = torch.where(not_nans > 0, f.sum() / not_nans, t_zero)  # channel average

        elif self.reduction == "sum":
            not_nans = not_nans.sum()
            f = torch.sum(f)  # sum over the batch and channel dims
        elif self.reduction == "mean_batch":
            not_nans = not_nans.sum(dim=0)
            f = torch.where(not_nans > 0, f.sum(dim=0) / not_nans, t_zero)  # batch average
        elif self.reduction == "sum_batch":
            not_nans = not_nans.sum(dim=0)
            f = f.sum(dim=0)  # the batch sum
        elif self.reduction == "none":
            pass
        else:
            raise ValueError(f"reduction={self.reduction} is invalid.")

        self.not_nans = not_nans  # preserve, since we may need it later to know how many elements were valid

        return f
