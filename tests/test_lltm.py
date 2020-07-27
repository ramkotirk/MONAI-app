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

from monai.networks.extensions import LLTM

TEST_CASE_1 = [
    {"input_features": 32, "state_size": 2},
    torch.tensor([[-0.1622, 0.1663], [0.5465, 0.0459], [-0.1436, 0.6171], [0.3632, -0.0111]]),
    torch.tensor([[-1.3773, 0.3348], [0.8353, 1.3064], [-0.2179, 4.1739], [1.3045, -0.1444]]),
]


class TestLLTM(unittest.TestCase):
    @parameterized.expand([TEST_CASE_1])
    def test_value(self, input_param, expected_h, expected_C):
        torch.manual_seed(0)
        X = torch.randn(4, 32)
        h = torch.randn(4, 2)
        C = torch.randn(4, 2)
        new_h, new_C = LLTM(**input_param)(X, (h, C))
        (new_h.sum() + new_C.sum()).backward()

        torch.testing.assert_allclose(new_h, expected_h, rtol=0.0001, atol=1e-04)
        torch.testing.assert_allclose(new_C, expected_C, rtol=0.0001, atol=1e-04)

    @parameterized.expand([TEST_CASE_1])
    def test_value_cuda(self, input_param, expected_h, expected_C):
        device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu:0")
        torch.manual_seed(0)
        X = torch.randn(4, 32).to(device)
        h = torch.randn(4, 2).to(device)
        C = torch.randn(4, 2).to(device)
        lltm = LLTM(**input_param).to(device)
        new_h, new_C = lltm(X, (h, C))
        (new_h.sum() + new_C.sum()).backward()

        torch.testing.assert_allclose(new_h, expected_h.to(device), rtol=0.0001, atol=1e-04)
        torch.testing.assert_allclose(new_C, expected_C.to(device), rtol=0.0001, atol=1e-04)


if __name__ == "__main__":
    unittest.main()
