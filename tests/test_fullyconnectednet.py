import unittest

import torch
from parameterized import parameterized

from monai.networks.nets import FullyConnectedNet, VarFullyConnectedNet

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

FC_TEST_CASE_0 = [0]
FC_TEST_CASE_1 = [0.15]

FC_CASES = [FC_TEST_CASE_0, FC_TEST_CASE_1]

VFC_TEST_CASE_0 = [
    {
        "in_channels": 2,
        "out_channels": 2,
        "latent_size": 64,
        "encode_channels": (16, 32, 64),
        "decode_channels": (16, 32, 64),
    },
    (3, 2, 64, 64),
    (3, 2, 64, 64),
]

VFC_CASES = [VFC_TEST_CASE_0]


class TestFullyConnectedNet(unittest.TestCase):
    def setUp(self):
        self.batch_size = 10
        self.inSize = 10
        self.arrShape = (self.batch_size, self.inSize)
        self.outSize = 3
        self.channels = [8, 16]
        self.arr = torch.randn(self.arrShape, dtype=torch.float32).to(device)

    @parameterized.expand(FC_CASES)
    def test_fc_shape(self, dropout):
        net = FullyConnectedNet(self.inSize, self.outSize, self.channels, dropout).to(device)
        out = net(self.arr)
        self.assertEqual(out.shape, (self.batch_size, self.outSize))

    @parameterized.expand(VFC_CASES)
    def test_vfc_shape(self, input_param, input_shape, expected_shape):
        net = VarFullyConnectedNet(**input_param).to(device)
        net.eval()
        with torch.no_grad():
            result = net.forward(torch.randn(input_shape).to(device))
            self.assertEqual(result.shape, expected_shape)


if __name__ == "__main__":
    unittest.main()
