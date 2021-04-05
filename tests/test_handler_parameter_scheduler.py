import unittest
import torch
from torch.nn import Module
from ignite.engine import Engine, Events

from monai.handlers.parameter_scheduler import ParamSchedulerHandler
from ignite.engine import Events


class ToyNet(Module):
    def __init__(self, value):
        super(ToyNet, self).__init__()
        self.value = value

    def forward(self, input):
        return input

    def get_value(self):
        return self.value

    def set_value(self, value):
        self.value = value


class TestHandlerParameterScheduler(unittest.TestCase):
    def test_linear_scheduler(self):
        # Testing step_constant
        net = ToyNet(value=-1)
        engine = Engine(lambda e, b: None)
        ParamSchedulerHandler(
            parameter_setter=net.set_value,
            value_calculator="linear",
            vc_kwargs={"initial_value": 0, "step_constant": 2, "step_max_value": 5, "max_value": 10},
            epoch_level=True,
            event=Events.EPOCH_COMPLETED,
        ).attach(engine)
        engine.run([0] * 8, max_epochs=2)
        torch.testing.assert_allclose(net.get_value(), 0)

        # Testing linear increase
        net = ToyNet(value=-1)
        engine = Engine(lambda e, b: None)
        ParamSchedulerHandler(
            parameter_setter=net.set_value,
            value_calculator="linear",
            vc_kwargs={"initial_value": 0, "step_constant": 2, "step_max_value": 5, "max_value": 10},
            epoch_level=True,
            event=Events.EPOCH_COMPLETED,
        ).attach(engine)
        engine.run([0] * 8, max_epochs=2)
        torch.testing.assert_allclose(net.get_value(), 3.33333333)

        # Testing max_value
        net = ToyNet(value=-1)
        engine = Engine(lambda e, b: None)
        ParamSchedulerHandler(
            parameter_setter=net.set_value,
            value_calculator="linear",
            vc_kwargs={"initial_value": 0, "step_constant": 2, "step_max_value": 5, "max_value": 10},
            epoch_level=True,
            event=Events.EPOCH_COMPLETED,
        ).attach(engine)
        engine.run([0] * 8, max_epochs=10)
        torch.testing.assert_allclose(net.get_value(), 10)

    def test_exponential_scheduler(self):
        net = ToyNet(value=-1)
        engine = Engine(lambda e, b: None)
        ParamSchedulerHandler(
            parameter_setter=net.set_value,
            value_calculator="exponential",
            vc_kwargs={"initial_value": 10, "gamma": 0.99},
            epoch_level=True,
            event=Events.EPOCH_COMPLETED,
        ).attach(engine)
        engine.run([0] * 8, max_epochs=2)
        torch.testing.assert_allclose(net.get_value(), 10 * 0.99 * 0.99)

    def test_step_scheduler(self):
        net = ToyNet(value=-1)
        engine = Engine(lambda e, b: None)
        ParamSchedulerHandler(
            parameter_setter=net.set_value,
            value_calculator="step",
            vc_kwargs={"initial_value": 10, "gamma": 0.99, "step_size": 5},
            epoch_level=True,
            event=Events.EPOCH_COMPLETED,
        ).attach(engine)
        engine.run([0] * 8, max_epochs=10)
        torch.testing.assert_allclose(net.get_value(), 10 * 0.99 * 0.99)

    def test_multistep_scheduler(self):
        net = ToyNet(value=-1)
        engine = Engine(lambda e, b: None)
        ParamSchedulerHandler(
            parameter_setter=net.set_value,
            value_calculator="multistep",
            vc_kwargs={"initial_value": 10, "gamma": 0.99, "milestones": [3, 6]},
            epoch_level=True,
            event=Events.EPOCH_COMPLETED,
        ).attach(engine)
        engine.run([0] * 8, max_epochs=10)
        torch.testing.assert_allclose(net.get_value(), 10 * 0.99 * 0.99)

    def test_custom_scheduler(self):
        def custom_logic(initial_value, gamma, current_step):
            return initial_value * gamma ** (current_step % 9)

        net = ToyNet(value=-1)
        engine = Engine(lambda e, b: None)
        ParamSchedulerHandler(
            parameter_setter=net.set_value,
            value_calculator=custom_logic,
            vc_kwargs={"initial_value": 10, "gamma": 0.99},
            epoch_level=True,
            event=Events.EPOCH_COMPLETED,
        ).attach(engine)
        engine.run([0] * 8, max_epochs=2)
        torch.testing.assert_allclose(net.get_value(), 10 * 0.99 * 0.99)
