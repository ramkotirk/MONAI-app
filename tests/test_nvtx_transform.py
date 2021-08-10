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

import numpy as np
from parameterized import parameterized
from torch import Tensor

from monai.transforms import Compose, Flip, RandFlip, RandFlipD, ToTensor, ToTensorD
from monai.transforms.nvtx import Mark, RandMark, RandRangePop, RandRangePush, RangePop, RangePush
from monai.utils import optional_import

_, has_nvtx = optional_import("torch._C._nvtx", descriptor="NVTX is not installed. Are you sure you have a CUDA build?")

TEST_CASE_0 = [
    np.random.randn(3, 3),
]
TEST_CASE_1 = [
    {"image": np.random.randn(3, 3)},
]


class TestNVTXTransforms(unittest.TestCase):
    @unittest.skipUnless(has_nvtx, "CUDA is required for NVTX!")
    @parameterized.expand([TEST_CASE_0, TEST_CASE_1])
    def test_nvtx_transfroms_alone(self, input):
        transforms = Compose(
            [
                RandMark("Mark: Transform Starts!"),
                RandRangePush("Range: RandFlipD"),
                RandRangePop(),
                RangePush("Range: ToTensorD"),
                RangePop(),
                Mark("Mark: Transform Ends!"),
            ]
        )
        output = transforms(input)
        self.assertEqual(id(input), id(output))

    @unittest.skipUnless(has_nvtx, "CUDA is required for NVTX!")
    @parameterized.expand([TEST_CASE_0])
    def test_nvtx_transfroms(self, input):
        transforms = Compose(
            [
                RandMark("Mark: Transform Starts!"),
                RandRangePush("Range: RandFlip"),
                RandFlip(prob=0.5),
                RandRangePop(),
                RangePush("Range: ToTensor"),
                ToTensor(),
                RangePop(),
                Mark("Mark: Transform Ends!"),
            ]
        )
        output = transforms(input)
        self.assertIsInstance(output, Tensor)
        try:
            np.testing.assert_array_equal(input, output)
        except AssertionError:
            np.testing.assert_array_equal(input, Flip()(output.numpy()))

    @unittest.skipUnless(has_nvtx, "CUDA is required for NVTX!")
    @parameterized.expand([TEST_CASE_1])
    def test_nvtx_transfromsd(self, input):
        transforms = Compose(
            [
                RandMark("Mark: Transform Starts!"),
                RandRangePush("Range: RandFlipD"),
                RandFlipD(keys="image", prob=0.5),
                RandRangePop(),
                RangePush("Range: ToTensorD"),
                ToTensorD(keys=("image")),
                RangePop(),
                Mark("Mark: Transform Ends!"),
            ]
        )
        output = transforms(input)
        self.assertIsInstance(output["image"], Tensor)
        try:
            np.testing.assert_array_equal(input["image"], output["image"])
        except AssertionError:
            np.testing.assert_array_equal(input["image"], Flip()(output["image"].numpy()))


if __name__ == "__main__":
    unittest.main()
