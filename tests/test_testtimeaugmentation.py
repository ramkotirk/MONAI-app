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

import unittest
from functools import partial
from typing import TYPE_CHECKING

import numpy as np
import torch
from torch._C import has_cuda

from monai.data import CacheDataset, DataLoader, create_test_image_2d
from monai.data.test_time_augmentation import TestTimeAugmentation
from monai.data.utils import pad_list_data_collate
from monai.losses import DiceLoss
from monai.networks.nets import UNet
from monai.transforms import (
    Activations,
    AddChanneld,
    AsDiscrete,
    Compose,
    CropForegroundd,
    DivisiblePadd,
    KeepLargestConnectedComponent,
    RandAffined,
)
from monai.transforms.croppad.dictionary import SpatialPadd
from monai.utils import optional_import, set_determinism

if TYPE_CHECKING:
    import tqdm

    has_tqdm = True
else:
    tqdm, has_tqdm = optional_import("tqdm")

trange = partial(tqdm.trange, desc="training") if has_tqdm else range

set_determinism(seed=0)


class TestTestTimeAugmentation(unittest.TestCase):
    def test_test_time_augmentation(self):
        input_size = (20, 20)
        device = "cuda" if has_cuda else "cpu"
        num_training_ims = 10
        data = []
        custom_create_test_image_2d = partial(
            create_test_image_2d, *input_size, rad_max=7, num_seg_classes=1, num_objs=1
        )
        keys = ["image", "label"]

        for _ in range(num_training_ims):
            im, label = custom_create_test_image_2d()
            data.append({"image": im, "label": label})

        transforms = Compose(
            [
                AddChanneld(keys),
                RandAffined(
                    keys,
                    prob=1.0,
                    spatial_size=(30, 30),
                    rotate_range=(np.pi / 3, np.pi / 3),
                    translate_range=(3, 3),
                    scale_range=((0.8, 1), (0.8, 1)),
                    padding_mode="zeros",
                    mode=("bilinear", "nearest"),
                    as_tensor_output=False,
                ),
                CropForegroundd(keys, source_key="image"),
                DivisiblePadd(keys, 4),
            ]
        )

        train_ds = CacheDataset(data, transforms)
        # output might be different size, so pad so that they match
        train_loader = DataLoader(train_ds, batch_size=2, collate_fn=pad_list_data_collate)

        model = UNet(2, 1, 1, channels=(6, 6), strides=(2, 2)).to(device)
        loss_function = DiceLoss(sigmoid=True)
        optimizer = torch.optim.Adam(model.parameters(), 1e-3)

        num_epochs = 10
        for _ in trange(num_epochs):
            epoch_loss = 0

            for batch_data in train_loader:
                inputs, labels = batch_data["image"].to(device), batch_data["label"].to(device)
                optimizer.zero_grad()
                outputs = model(inputs)
                loss = loss_function(outputs, labels)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()

            epoch_loss /= len(train_loader)

        image, label = custom_create_test_image_2d()
        test_data = {"image": image, "label": label}

        post_trans = Compose(
            [
                Activations(sigmoid=True),
                AsDiscrete(threshold_values=True),
                KeepLargestConnectedComponent(applied_labels=1),
            ]
        )

        def inferrer_fn(x):
            return post_trans(model(x))

        tt_aug = TestTimeAugmentation(transforms, batch_size=5, num_workers=0, inferrer_fn=inferrer_fn, device=device)
        mean, std = tt_aug(test_data)
        self.assertEqual(mean.shape, (1,) + input_size)
        self.assertEqual((mean.min(), mean.max()), (0.0, 1.0))
        self.assertEqual(std.shape, (1,) + input_size)

    def test_fail_non_random(self):
        transforms = Compose([AddChanneld("im"), SpatialPadd("im", 1)])
        with self.assertRaises(RuntimeError):
            TestTimeAugmentation(transforms, None, None, None, None)


if __name__ == "__main__":
    unittest.main()
