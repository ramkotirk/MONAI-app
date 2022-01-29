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

import os
import sys
import tempfile
import unittest

import nibabel as nib
import numpy as np
from parameterized import parameterized

from monai.data import DataLoader, HashCacheDataset
from monai.transforms import Compose, LoadImaged, ThreadUnsafe, Transform
from monai.utils.module import pytorch_after

TEST_CASE_1 = [Compose([LoadImaged(keys=["image", "label"])]), (128, 128, 128)]

TEST_CASE_2 = [None, (128, 128, 128)]

TEST_DS = []
for c in (0, 1, 2):
    for l in (0, 1, 2):
        TEST_DS.append([False, c, 0 if sys.platform in ("darwin", "win32") else l])
    if sys.platform not in ("darwin", "win32"):
        # persistent_workers need l > 0
        for l in (1, 2):
            TEST_DS.append([True, c, l])


class TestCacheDataset(unittest.TestCase):
    @parameterized.expand([TEST_CASE_1, TEST_CASE_2])
    def test_shape(self, transform, expected_shape):
        test_image = nib.Nifti1Image(np.random.randint(0, 2, size=[128, 128, 128]), np.eye(4))
        with tempfile.TemporaryDirectory() as tempdir:
            nib.save(test_image, os.path.join(tempdir, "test_image1.nii.gz"))
            nib.save(test_image, os.path.join(tempdir, "test_label1.nii.gz"))
            nib.save(test_image, os.path.join(tempdir, "test_image2.nii.gz"))
            nib.save(test_image, os.path.join(tempdir, "test_label2.nii.gz"))
            test_data = [
                {
                    "image": os.path.join(tempdir, "test_image1.nii.gz"),
                    "label": os.path.join(tempdir, "test_label1.nii.gz"),
                },
                {
                    "image": os.path.join(tempdir, "test_image2.nii.gz"),
                    "label": os.path.join(tempdir, "test_label2.nii.gz"),
                },
                # duplicated data for augmentation
                {
                    "image": os.path.join(tempdir, "test_image2.nii.gz"),
                    "label": os.path.join(tempdir, "test_label2.nii.gz"),
                },
            ]
            dataset = HashCacheDataset(data=test_data, transform=transform, cache_rate=1.0, num_workers=2)
            # ensure no duplicated cache content
            self.assertEqual(len(dataset._cache), 2)
            data1 = dataset[0]
            data2 = dataset[1]
            data3 = dataset[-1]
            # test slice indices
            data4 = dataset[0:-1]
            self.assertEqual(len(data4), 2)

        if transform is None:
            self.assertEqual(data1["image"], os.path.join(tempdir, "test_image1.nii.gz"))
            self.assertEqual(data2["label"], os.path.join(tempdir, "test_label2.nii.gz"))
            self.assertEqual(data3["image"], os.path.join(tempdir, "test_image2.nii.gz"))
        else:
            self.assertTupleEqual(data1["image"].shape, expected_shape)
            self.assertTupleEqual(data2["label"].shape, expected_shape)
            self.assertTupleEqual(data3["image"].shape, expected_shape)
            for d in data4:
                self.assertTupleEqual(d["image"].shape, expected_shape)


class _StatefulTransform(Transform, ThreadUnsafe):
    """
    A transform with an internal state.
    The state is changing at each call.
    """

    def __init__(self):
        self.property = 1

    def __call__(self, data):
        self.property = self.property + 1
        return data * 100 + self.property


class TestDataLoader(unittest.TestCase):
    @parameterized.expand(TEST_DS)
    def test_thread_safe(self, persistent_workers, cache_workers, loader_workers):
        expected = [102, 202, 302, 402, 502, 602, 702, 802, 902, 1002]
        _kwg = {"persistent_workers": persistent_workers} if pytorch_after(1, 8) else {}
        data_list = list(range(1, 11))
        dataset = HashCacheDataset(
            data=data_list, transform=_StatefulTransform(), cache_rate=1.0, num_workers=cache_workers, progress=False
        )
        self.assertListEqual(expected, list(dataset))
        loader = DataLoader(
            HashCacheDataset(
                data=data_list,
                transform=_StatefulTransform(),
                cache_rate=1.0,
                num_workers=cache_workers,
                progress=False,
            ),
            batch_size=1,
            num_workers=loader_workers,
            **_kwg,
        )
        self.assertListEqual(expected, [y.item() for y in loader])
        self.assertListEqual(expected, [y.item() for y in loader])


if __name__ == "__main__":
    unittest.main()
