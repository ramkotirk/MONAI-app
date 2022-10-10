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
from parameterized import parameterized

from monai.transforms import MedianSmoothd
from tests.utils import TEST_NDARRAYS, assert_allclose

TESTS = []
for p in TEST_NDARRAYS:
    TESTS.append(
        [
            {"keys": "img", "radius": 1},
            {"img": p(np.array([[[1, 1, 1], [2, 2, 2], [3, 3, 3]], [[4, 4, 4], [5, 5, 5], [6, 6, 6]]]))},
            np.array(
                [[[0.0, 0.0, 0.0], [0.0, 2, 0.0], [0.0, 0.0, 0.0]], [[0.0, 0.0, 0.0], [0.0, 2, 0.0], [0.0, 0.0, 0.0]]]
            ),
        ]
    )

    TESTS.append(
        [
            {"keys": "img", "radius": [1, 1, 1]},
            {"img": p(np.array([[[1, 1, 1], [2, 2, 2], [3, 3, 3]], [[4, 4, 4], [5, 5, 5], [6, 6, 6]]]))},
            np.array(
                [[[0.0, 0.0, 0.0], [0.0, 2, 0.0], [0.0, 0.0, 0.0]], [[0.0, 0.0, 0.0], [0.0, 2, 0.0], [0.0, 0.0, 0.0]]]
            ),
        ]
    )

    TESTS.append(
        [
            {"keys": "img", "radius": [1, 1, 2]},
            {"img": p(np.array([[[1, 1, 1], [2, 2, 2], [3, 3, 3]], [[4, 4, 4], [5, 5, 5], [6, 6, 6]]]))},
            np.array(
                [[[0.0, 0.0, 0.0], [0.0, 0, 0.0], [0.0, 0.0, 0.0]], [[0.0, 0.0, 0.0], [0.0, 0, 0.0], [0.0, 0.0, 0.0]]]
            ),
        ]
    )

    TESTS.append(
        [
            {"keys": "img", "radius": [1, 0, 1]},
            {"img": p(np.array([[[1, 1, 1], [2, 2, 2], [3, 3, 3]], [[4, 4, 4], [5, 5, 5], [6, 6, 6]]]))},
            np.array([[[0.0, 1, 0.0], [0.0, 2, 0.0], [0.0, 3, 0.0]], [[0.0, 1, 0.0], [0.0, 2, 0.0], [0.0, 3, 0.0]]]),
        ]
    )


class TestMedianSmoothd(unittest.TestCase):
    @parameterized.expand(TESTS)
    def test_value(self, argments, image, expected_data):
        result = MedianSmoothd(**argments)(image)
        assert_allclose(result["img"], expected_data, rtol=1e-4, type_test="tensor")


if __name__ == "__main__":
    unittest.main()
