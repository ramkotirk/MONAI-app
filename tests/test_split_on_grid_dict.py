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
import torch
from parameterized import parameterized

from monai.apps.pathology.transforms import SplitOnGridDict

A11 = torch.randn(3, 2, 2)
A12 = torch.randn(3, 2, 2)
A21 = torch.randn(3, 2, 2)
A22 = torch.randn(3, 2, 2)

A1 = torch.cat([A11, A12], 2)
A2 = torch.cat([A21, A22], 2)
A = torch.cat([A1, A2], 1)

TEST_CASE_0 = [
    {"keys": "image", "grid_size": (2, 2)},
    {"image": A},
    torch.stack([A11, A12, A21, A22]),
]

TEST_CASE_1 = [
    {"keys": "image", "grid_size": (2, 1)},
    {"image": A},
    torch.stack([A1, A2]),
]

TEST_CASE_2 = [
    {"keys": "image", "grid_size": (1, 2)},
    {"image": A1},
    torch.stack([A11, A12]),
]

TEST_CASE_3 = [
    {"keys": "image", "grid_size": (1, 2)},
    {"image": A2},
    torch.stack([A21, A22]),
]

TEST_CASE_4 = [
    {"keys": "image", "grid_size": (1, 1), "patch_size": (2, 2)},
    {"image": A},
    torch.stack([A11]),
]

TEST_CASE_5 = [
    {"keys": "image", "grid_size": 1, "patch_size": 4},
    {"image": A},
    torch.stack([A]),
]

TEST_CASE_6 = [
    {"keys": "image", "grid_size": 2, "patch_size": 2},
    {"image": A},
    torch.stack([A11, A12, A21, A22]),
]

TEST_CASE_7 = [
    {"keys": "image", "grid_size": 1},
    {"image": A},
    torch.stack([A]),
]

TEST_CASE_MC_0 = [
    {"keys": "image", "grid_size": (2, 2)},
    [{"image": A}, {"image": A}],
    [torch.stack([A11, A12, A21, A22]), torch.stack([A11, A12, A21, A22])],
]


TEST_CASE_MC_1 = [
    {"keys": "image", "grid_size": (2, 1)},
    [{"image": A}] * 5,
    [torch.stack([A1, A2])] * 5,
]


TEST_CASE_MC_2 = [
    {"keys": "image", "grid_size": (1, 2)},
    [{"image": A1}, {"image": A2}],
    [torch.stack([A11, A12]), torch.stack([A21, A22])],
]


class TestSplitOnGridDict(unittest.TestCase):
    @parameterized.expand(
        [
            TEST_CASE_0,
            TEST_CASE_1,
            TEST_CASE_2,
            TEST_CASE_3,
            TEST_CASE_4,
            TEST_CASE_5,
            TEST_CASE_6,
            TEST_CASE_7,
        ]
    )
    def test_split_pathce_single_call(self, input_parameters, img_dict, expected):
        splitter = SplitOnGridDict(**input_parameters)
        output = splitter(img_dict)[input_parameters["keys"]]
        np.testing.assert_equal(output.numpy(), expected.numpy())

    @parameterized.expand(
        [
            TEST_CASE_MC_0,
            TEST_CASE_MC_1,
            TEST_CASE_MC_2,
        ]
    )
    def test_split_pathce_multiple_call(self, input_parameters, img_list, expected_list):
        splitter = SplitOnGridDict(**input_parameters)
        for img_dict, expected in zip(img_list, expected_list):
            output = splitter(img_dict)[input_parameters["keys"]]
            np.testing.assert_equal(output.numpy(), expected.numpy())


if __name__ == "__main__":
    unittest.main()
