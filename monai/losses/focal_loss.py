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

import warnings
from typing import Callable, Optional, Union

import torch
from torch.nn.modules.loss import _WeightedLoss

from monai.networks import one_hot
from monai.utils import LossReduction


class FocalLoss(_WeightedLoss):
    """
    Reimplementation of the Focal Loss described in:

        - "Focal Loss for Dense Object Detection", T. Lin et al., ICCV 2017
        - "AnatomyNet: Deep learning for fast and fully automated whole‐volume segmentation of head and neck anatomy",
          Zhu et al., Medical Physics 2018
    """

    def __init__(
        self,
        include_background: bool = True,
        to_onehot_y: bool = False,
        sigmoid: bool = False,
        softmax: bool = False,
        other_act: Optional[Callable] = None,
        smooth_log: float = 1e-8,
        gamma: float = 2.0,
        weight: Optional[torch.Tensor] = None,
        reduction: Union[LossReduction, str] = LossReduction.MEAN,
    ) -> None:
        """
        Args:
            include_background: if False, channel index 0 (background category) is excluded from the calculation.
            to_onehot_y: whether to convert `y` into the one-hot format. Defaults to False.
            sigmoid: if True, apply a sigmoid function to the prediction.
            softmax: if True, apply a softmax function to the prediction.
            other_act: if don't want to use `sigmoid` or `softmax`, use other callable function to execute
                other activation layers, Defaults to ``None``. for example:
                `other_act = torch.tanh`.
            smooth_log: a small constant added to the input before log transform.
            gamma: value of the exponent gamma in the definition of the Focal loss.
            weight: weights to apply to the voxels of each class. If None no weights are applied.
                This corresponds to the weights `\alpha` in [1].
            reduction: {``"none"``, ``"mean"``, ``"sum"``}
                Specifies the reduction to apply to the output. Defaults to ``"mean"``.

                - ``"none"``: no reduction will be applied.
                - ``"mean"``: the sum of the output will be divided by the number of elements in the output.
                - ``"sum"``: the output will be summed.

        Example:
            .. code-block:: python

                import torch
                from monai.losses import FocalLoss

                pred = torch.tensor([[1, 0], [0, 1], [1, 0]], dtype=torch.float32)
                grnd = torch.tensor([[0], [1], [0]], dtype=torch.int64)
                fl = FocalLoss()
                fl(pred, grnd)

        """
        super(FocalLoss, self).__init__(weight=weight, reduction=LossReduction(reduction).value)
        if other_act is not None and not callable(other_act):
            raise TypeError(f"other_act must be None or callable but is {type(other_act).__name__}.")
        if int(sigmoid) + int(softmax) + int(other_act is not None) > 1:
            raise ValueError("Incompatible values: more than 1 of [sigmoid=True, softmax=True, other_act is not None].")
        self.include_background = include_background
        self.to_onehot_y = to_onehot_y
        self.sigmoid = sigmoid
        self.softmax = softmax
        self.other_act = other_act
        self.smooth_log = smooth_log
        self.gamma = gamma
        self.weight: Optional[torch.Tensor] = None

    def forward(self, input: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        """
        Args:
            input: the shape should be BNH[WD], where N is the number of classes.
            target: the shape should be BNH[WD] or B1H[WD], where N is the number of classes.

        Raises:
            AssertionError: When input and target (after one hot transform if setted)
                have different shapes.
            ValueError: When ``self.reduction`` is not one of ["mean", "sum", "none"].

        """

        if self.sigmoid:
            input = torch.sigmoid(input)

        n_pred_ch = input.shape[1]
        if self.softmax:
            if n_pred_ch == 1:
                warnings.warn("single channel prediction, `softmax=True` ignored.")
            else:
                input = torch.softmax(input, 1)

        if self.other_act is not None:
            input = self.other_act(input)

        if self.to_onehot_y:
            if n_pred_ch == 1:
                warnings.warn("single channel prediction, `to_onehot_y=True` ignored.")
            else:
                target = one_hot(target, num_classes=n_pred_ch)

        if not self.include_background:
            if n_pred_ch == 1:
                warnings.warn("single channel prediction, `include_background=False` ignored.")
            else:
                # if skipping background, removing first channel
                target = target[:, 1:]
                input = input[:, 1:]

        if target.shape != input.shape:
            raise AssertionError(f"ground truth has different shape ({target.shape}) from input ({input.shape})")

        i = input
        t = target

        # Change the shape of input and target to B x N x num_voxels.
        i = i.view(i.size(0), i.size(1), -1)
        t = t.view(t.size(0), t.size(1), -1)

        # Compute the log proba.
        logpt = torch.log(torch.clamp(i, self.smooth_log, 1.0))
        # Get the proba
        pt = torch.exp(logpt)  # B,H*W or B,N,H*W

        if self.weight is not None:
            self.weight = self.weight.to(i)
            # Convert the weight to a map in which each voxel
            # has the weight associated with the ground-truth label
            # associated with this voxel in target.
            at = self.weight[None, :, None]  # N => 1,N,1
            at = at.expand((t.size(0), -1, t.size(2)))  # 1,N,1 => B,N,H*W
            # Multiply the log proba by their weights.
            logpt = logpt * at

        # Compute the loss mini-batch.
        weight = torch.pow(-pt + 1.0, self.gamma)
        loss = torch.mean(-weight * t * logpt, dim=-1)
        if self.reduction == LossReduction.SUM.value:
            return loss.sum()
        if self.reduction == LossReduction.NONE.value:
            return loss
        if self.reduction == LossReduction.MEAN.value:
            return loss.mean()
        raise ValueError(f'Unsupported reduction: {self.reduction}, available options are ["mean", "sum", "none"].')
