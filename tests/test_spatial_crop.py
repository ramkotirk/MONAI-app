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

import unittest

import numpy as np
import torch
from parameterized import parameterized

from monai.transforms import SpatialCrop
from tests.utils import TEST_NDARRAYS, assert_allclose

TESTS = [
    # [{"roi_center": [1, 1, 1], "roi_size": [2, 2, 2]}, (3, 3, 3, 3), (3, 2, 2, 2)],
    # [{"roi_center": [1, 1, 1], "roi_size": [2, 2, 2]}, (3, 1, 1, 1), (3, 1, 1, 1)],
    # [{"roi_start": [0, 0, 0], "roi_end": [2, 2, 2]}, (3, 3, 3, 3), (3, 2, 2, 2)],
    [{"roi_start": [0, 0], "roi_end": [2, 2]}, (3, 3, 3, 3), (3, 2, 2, 3)],
    # [{"roi_start": [0, 0, 0, 0, 0], "roi_end": [2, 2, 2, 2, 2]}, (3, 3, 3, 3), (3, 2, 2, 2)],
    # [{"roi_start": [0, 0, 0, 0, 0], "roi_end": [8, 8, 8, 2, 2]}, (3, 3, 3, 3), (3, 3, 3, 3)],
    # [{"roi_start": [1, 0, 0], "roi_end": [1, 8, 8]}, (3, 3, 3, 3), (3, 0, 3, 3)],
    # [{"roi_slices": [slice(s, e) for s, e in zip([None, None, None], [None, None, None])]}, (3, 11, 12, 15), (3, 11, 12, 15)],
    # [{"roi_slices": [slice(s, e) for s, e in zip([1, None, 0], [None, None, None])]}, (3, 7, 9, 11), (3, 6, 9, 11)],
    # [{"roi_slices": [slice(s, e) for s, e in zip([0, None, None], [-1, None, None])]}, (3, 7, 9, 11), (3, 6, 9, 11)],
    # [{"roi_slices": [slice(s, e) for s, e in zip([1, None, None], [None, None, None])]}, (3, 10, 8, 6), (3, 9, 8, 6)],
    # [{"roi_slices": [slice(s, e) for s, e in zip([-1, -2, 0], [None, None, 2])]}, (3, 15, 17, 8), (3, 1, 2, 2)],
    # [{"roi_slices": [slice(s, e) for s, e in zip([None, None, None], [-2, -1, 2])]}, (3, 13, 8, 6), (3, 11, 7, 2)],
]

TEST_ERRORS = [[{"roi_slices": [slice(s, e, 2) for s, e in zip([-1, -2, 0], [None, None, 2])]}]]


class TestSpatialCrop(unittest.TestCase):
    @parameterized.expand(TESTS)
    def test_shape(self, input_param, input_shape, expected_shape):
        base_comparison = None
        input_data = np.random.randint(0, 2, size=input_shape)
        for p in TEST_NDARRAYS:
            for q in TEST_NDARRAYS + (None,):
                input_param_mod = {
                    k: q(v) if k != "roi_slices" and q is not None else v for k, v in input_param.items()
                }
                im = p(input_data)
                cropper = SpatialCrop(**input_param_mod)
                result = cropper(im)
                self.assertTupleEqual(result.shape, expected_shape)
                if base_comparison is None:
                    base_comparison = result
                else:
                    assert_allclose(result, base_comparison)
                # test inverse
                inv = cropper.inverse(result)
                self.assertTupleEqual(inv.shape, input_data.shape)
                self.assertEqual(inv.applied_operations, [])

    @parameterized.expand(TEST_ERRORS)
    def test_error(self, input_param):
        with self.assertRaises(ValueError):
            SpatialCrop(**input_param)


if __name__ == "__main__":
    unittest.main()
