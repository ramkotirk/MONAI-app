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

from __future__ import annotations

import unittest

import numpy as np
import torch
from parameterized import parameterized

from monai.networks.layers import MedianFilter


class MedianFilterTestCase(unittest.TestCase):
    @parameterized.expand(
        [
            ("3d_big", torch.ones(1, 1, 2, 3, 5), MedianFilter([1, 2, 4])),
            ("3d", torch.ones(1, 1, 4, 3, 4), MedianFilter(1)),
        ]
    )
    def test_3d(self, name, input_tensor, filter):
        filter = filter.to(torch.device("cpu:0"))

        expected = input_tensor.numpy()
        output = filter(input_tensor).cpu().numpy()

        np.testing.assert_allclose(output, expected, rtol=1e-5)

    def test_3d_radii(self):
        a = torch.ones(1, 1, 4, 3, 2)
        g = MedianFilter([3, 2, 1]).to(torch.device("cpu:0"))

        expected = a.numpy()
        out = g(a).cpu().numpy()
        np.testing.assert_allclose(out, expected, rtol=1e-5)
        if torch.cuda.is_available():
            g = MedianFilter([3, 2, 1]).to(torch.device("cuda:0"))
            np.testing.assert_allclose(g(a.cuda()).cpu().numpy(), expected, rtol=1e-2)

    def test_wrong_args(self):
        with self.assertRaisesRegex(ValueError, ""):
            MedianFilter([3, 2]).to(torch.device("cpu:0"))
        MedianFilter([3, 2, 1]).to(torch.device("cpu:0"))  # test init


if __name__ == "__main__":
    unittest.main()
