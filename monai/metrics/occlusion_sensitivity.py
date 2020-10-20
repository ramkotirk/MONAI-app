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

from collections.abc import Sequence
from typing import Union

import numpy as np
import torch
import torch.nn as nn

try:
    from tqdm import trange
except (ImportError, AttributeError):
    trange = range


def _check_input_image(image):
    # Only accept batch size of 1
    if image.shape[0] > 1:
        raise RuntimeError("Expected batch size of 1.")
    return image


def _check_input_label(label, image):
    # If necessary turn the label into a 1-element tensor
    if isinstance(label, int):
        label = torch.tensor([[label]], dtype=torch.int64).to(image.device)
    # If the label is a tensor, make sure  there's only 1 element
    elif label.numel() != image.shape[0]:
        raise RuntimeError("Expected as many labels as batches.")
    return label


def _check_input_bounding_box(b_box, im_shape):

    # If no bounding box has been supplied, set min and max to None
    if b_box is None:
        b_box_min = b_box_max = None

    # Bounding box has been supplied
    else:
        # Should be twice as many elements in `b_box` as `im_shape`
        if len(b_box) != 2 * len(im_shape):
            raise ValueError("Bounding box should contain upper and lower for all dimensions except batch number")

        # If any min's or max's are -ve, set them to 0 and im_shape-1, respectively.
        b_box_min = np.array(b_box[::2])
        b_box_max = np.array(b_box[1::2])
        b_box_min[b_box_min < 0] = 0
        b_box_max[b_box_max < 0] = np.array(im_shape)[b_box_max < 0] - 1
        # Check all min's are <= max's
        if np.any(b_box_min > b_box_max):
            raise ValueError("Min bounding box should be <= max for all values")

    return b_box_min, b_box_max


def _is_in_bound(idx, b_box_min, b_box_max):
    """Check index is in bounds.
    If the bounding box is ``None``, return ``True``."""
    if b_box_min is None:
        return True
    for i, i_min, i_max in zip(idx, b_box_min, b_box_max):
        if not i_min <= i <= i_max:
            return False
    return True


def compute_occlusion_sensitivity(
    model: nn.Module,
    image: torch.Tensor,
    label: Union[int, torch.Tensor],
    pad_val: float = 0.0,
    margin: Union[int, Sequence] = 2,
    n_batch: int = 128,
    b_box: Union[Sequence, None] = None,
) -> np.ndarray:
    """
    This function computes the occlusion sensitivity for a model's prediction
    of a given image. By occlusion sensitivity, we mean how the probability of a given
    prediction changes as the occluded section of an image changes. This can
    be useful to understand why a network is making certain decisions.

    The result is given as ``baseline`` (the probability of
    a certain output) minus the probability of the output with the occluded
    area.

    Therefore, higher values in the output image mean there was a
    greater the drop in certainty, indicating the occluded region was more
    important in the decision process.

    See: R. R. Selvaraju et al. Grad-CAM: Visual Explanations from Deep Networks via Gradient-based Localization. https://doi.org/10.1109/ICCV.2017.74

    Args:
        model: model to use for inference
        image: image to test
        label: classification label to check for changes (normally the true
            label, but doesn't have to be)
        pad_val: when occluding part of the image, which values should we put
            in the image?
        margin: we'll create a cuboid/cube around the voxel to be occluded. if
            ``margin==2``, then we'll create a cube that is +/- 2 voxels in
            all directions (i.e., a cube of 5 x 5 x 5 voxels). A ``Sequence``
            can be supplied to have a margin of different sizes (i.e., create
            a cuboid).
        n_batch: number of images in a batch before inference.
        b_box: Bounding box on which to perform the analysis. The output image
            will also match in size. There should be a minimum and maximum for
            all dimensions except batch: ``[min1, max1, min2, max2,...]``.
            * By default, the whole image will be used. Decreasing the size will
            speed the analysis up, which might be useful for larger images.
            * Min and max are inclusive, so [0, 63, ...] will have size (64, ...).
            * Use -ve to use 0 for min values and im.shape[x]-1 for xth dimension.
    Returns:
        Numpy array. If no bounding box is supplied, this will be the same size
        as the input image. If a bounding box is used, the output image will be
        cropped to this size.
    """

    # Check input arguments
    image = _check_input_image(image)
    label = _check_input_label(label, image)
    im_shape = image.shape[1:]
    b_box_min, b_box_max = _check_input_bounding_box(b_box, im_shape)

    # Get baseline probability
    baseline = model(image).detach()[0, label].item()

    # Create some lists
    batch_images_lst = []
    batch_ids_lst = []

    heatmap = torch.empty(0, dtype=torch.float32, device=image.device)

    # Loop 1D over image
    for i in trange(image.numel()):
        # Get corresponding ND index
        idx = np.unravel_index(i, im_shape)

        # Skip if out of bounds
        if not _is_in_bound(idx, b_box_min, b_box_max):
            continue

        # Get min and max index of box to occlude
        min_idx = [max(0, i - margin) for i in idx]
        max_idx = [min(j, i + margin) for i, j in zip(idx, im_shape)]

        # Clone and replace target area with `pad_val`
        occlu_im = image.clone()
        occlu_im[(...,) + tuple(slice(i, j) for i, j in zip(min_idx, max_idx))] = pad_val

        # Add to list
        batch_images_lst.append(occlu_im)
        batch_ids_lst.append(label)

        # Once the batch is complete (or on last iteration)
        if len(batch_images_lst) == n_batch:
            # Get the predictions and append to tensor
            batch_images = torch.cat(batch_images_lst, dim=0)
            batch_ids = torch.cat(batch_ids_lst, dim=0)
            scores = model(batch_images).detach().gather(1, batch_ids)
            heatmap = torch.cat((heatmap, scores))

            # Clear lists
            batch_images_lst = []
            batch_ids_lst = []

    # If there are any predictions remaining to be done (because required
    # number of predictions isn't a multiple of the batch size), then do them.
    if len(batch_images_lst) > 0:
        # Get the predictions and append to tensor
        batch_images = torch.cat(batch_images_lst, dim=0)
        batch_ids = torch.cat(batch_ids_lst, dim=0)
        scores = model(batch_images).detach().gather(1, batch_ids)
        heatmap = torch.cat((heatmap, scores))

    # Convert tensor to numpy
    diffmaps = heatmap.cpu().numpy()

    # If no bounding box supplied, output shape is same as input shape.
    # If bounding box is present, shape is max - min + 1
    output_im_shape = im_shape if b_box is None else tuple(x - y + 1 for x, y in zip(b_box_max, b_box_min))

    # Reshape to size of output image
    diffmaps = diffmaps.reshape(output_im_shape)

    # Squeeze, subtract from baseline and return
    return baseline - np.squeeze(diffmaps)
