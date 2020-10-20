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

import unittest

import torch
from parameterized import parameterized
from tests.utils import test_script_save
from monai.networks.nets import Discriminator

TEST_CASE_0 = [
    {"in_shape": (1, 64, 64), "channels": (2, 4, 8), "strides": (2, 2, 2), "num_res_units": 0},
    torch.rand(16, 1, 64, 64),
    (16, 1),
]

TEST_CASE_1 = [
    {"in_shape": (1, 64, 64), "channels": (2, 4, 8), "strides": (2, 2, 2), "num_res_units": 2},
    torch.rand(16, 1, 64, 64),
    (16, 1),
]

TEST_CASE_2 = [
    {"in_shape": (1, 64, 64), "channels": (2, 4), "strides": (2, 2), "num_res_units": 0},
    torch.rand(16, 1, 64, 64),
    (16, 1),
]

CASES = [TEST_CASE_0, TEST_CASE_1, TEST_CASE_2]


class TestDiscriminator(unittest.TestCase):
    @parameterized.expand(CASES)
    def test_shape(self, input_param, input_data, expected_shape):
        net = Discriminator(**input_param)
        net.eval()
        with torch.no_grad():
            result = net.forward(input_data)
            self.assertEqual(result.shape, expected_shape)

    def test_script(self):
        net = Discriminator(in_shape=(1, 64, 64), channels=(2, 4), strides=(2, 2), num_res_units=0)
        test_data = torch.rand(16, 1, 64, 64)
        out_orig, out_reloaded = test_script_save(net, test_data)
        assert torch.allclose(out_orig, out_reloaded)


if __name__ == "__main__":
    unittest.main()
