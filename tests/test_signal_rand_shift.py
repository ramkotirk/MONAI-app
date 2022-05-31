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
import unittest

import numpy as np
from parameterized import parameterized

from monai.transforms.signal.array import SignalRandShift

TEST_SIGNAL = os.path.join(os.path.dirname(__file__), "testing_data", "signal.npy")
VALID_CASES = [(-1, "wrap"), (0,"constant"), (1,"wrap")]

class TestSignalRandShift(unittest.TestCase):
    @parameterized.expand(VALID_CASES)
    def test_correct_parameters_multi_channels(self, method, current_sample_rate, target_sample_rate):
        self.assertIsInstance(SignalRandShift(method, current_sample_rate, target_sample_rate), SignalRandShift)
        sig = np.load(TEST_SIGNAL)
        shifted = SignalRandShift(method, current_sample_rate, target_sample_rate)
        shiftedsignal = shifted(sig)
        self.assertEqual(len(shiftedsignal), len(sig))

    @parameterized.expand(VALID_CASES)
    def test_correct_parameters_mono_channels(self, method, current_sample_rate, target_sample_rate):
        self.assertIsInstance(SignalRandShift(method, current_sample_rate, target_sample_rate), SignalRandShift)

        sig = np.load(TEST_SIGNAL)[0, :]
        shifted = SignalRandShift(method, current_sample_rate, target_sample_rate)
        shidtedsignal = shifted(sig)
        self.assertEqual(len(shidtedsignal), len(sig))


if __name__ == "__main__":
    unittest.main()
