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

from monai.apps.detection.transforms.dictionary import BoxToMaskd, ConvertBoxModed, MaskToBoxd
from monai.transforms import CastToTyped, Invertd
from tests.utils import TEST_NDARRAYS_NO_META_TENSOR, assert_allclose

TESTS_3D = []
boxes = [[0, 0, 0, 0, 0, 0], [0, 1, 0, 2, 3, 3], [0, 1, 1, 2, 3, 4]]
labels = [1, 1, 0]
scores = [[0.2, 0.8], [0.3, 0.7], [0.6, 0.4]]
image_size = [1, 4, 6, 4]
image = np.zeros(image_size)

for p in TEST_NDARRAYS_NO_META_TENSOR:
    TESTS_3D.append(
        [
            {"box_keys": "boxes", "dst_mode": "xyzwhd"},
            {"boxes": p(boxes), "image": p(image), "labels": p(labels), "scores": p(scores)},
            p([[0, 0, 0, 0, 0, 0], [0, 1, 0, 2, 2, 3], [0, 1, 1, 2, 2, 3]]),
            p([[0, 0, 0, 0, 0, 0], [0, 3, 0, 1, 9, 4.5], [0, 3, 1.5, 1, 9, 6]]),
            p([[1, -6, -1, 1, -6, -1], [1, -3, -1, 2, 3, 3.5], [1, -3, 0.5, 2, 3, 5]]),
            p([[4, 6, 4, 4, 6, 4], [2, 3, 1, 4, 5, 4], [2, 3, 0, 4, 5, 3]]),
            p([[0, 1, 0, 2, 3, 3], [0, 1, 1, 2, 3, 4]]),
        ]
    )

TESTS_2D = []
boxes = [[0, 1, 2, 2], [0, 0, 1, 1]]
labels = [1, 0]
image_size = [1, 2, 2]
image = np.zeros(image_size)
for p in TEST_NDARRAYS_NO_META_TENSOR:
    TESTS_2D.append(
        [{"boxes": p(boxes), "image": p(image), "labels": p(labels)}, p([[[0, 2], [0, 2]], [[1, 0], [0, 0]]])]
    )


class TestBoxTransform(unittest.TestCase):
    @parameterized.expand(TESTS_2D)
    def test_value_2d(self, data, expected_mask):
        test_dtype = [torch.float32, torch.float16]
        for dtype in test_dtype:
            data = CastToTyped(keys=["image", "boxes"], dtype=dtype)(data)
            transform_to_mask = BoxToMaskd(
                box_keys="boxes",
                box_mask_keys="box_mask",
                box_ref_image_keys="image",
                label_keys="labels",
                min_fg_label=0,
                ellipse_mask=False,
            )
            transform_to_box = MaskToBoxd(
                box_keys="boxes", box_mask_keys="box_mask", label_keys="labels", min_fg_label=0
            )
            data_mask = transform_to_mask(data)
            assert_allclose(data_mask["box_mask"], expected_mask, type_test=True, device_test=True, atol=1e-3)
            data_back = transform_to_box(data_mask)
            assert_allclose(data_back["boxes"], data["boxes"], type_test=False, device_test=False, atol=1e-3)
            assert_allclose(data_back["labels"], data["labels"], type_test=False, device_test=False, atol=1e-3)

    def test_value_3d_mask(self):
        test_dtype = [torch.float32, torch.float16]
        image = np.zeros((1, 32, 33, 34))
        boxes = np.array([[7, 8, 9, 10, 12, 13], [1, 3, 5, 2, 5, 9], [0, 0, 0, 1, 1, 1]])
        data = {"image": image, "boxes": boxes, "labels": np.array((1, 0, 3))}
        for dtype in test_dtype:
            data = CastToTyped(keys=["image", "boxes"], dtype=dtype)(data)
            transform_to_mask = BoxToMaskd(
                box_keys="boxes",
                box_mask_keys="box_mask",
                box_ref_image_keys="image",
                label_keys="labels",
                min_fg_label=0,
                ellipse_mask=False,
            )
            transform_to_box = MaskToBoxd(
                box_keys="boxes", box_mask_keys="box_mask", label_keys="labels", min_fg_label=0
            )
            data_mask = transform_to_mask(data)
            assert_allclose(data_mask["box_mask"].shape, (3, 32, 33, 34), type_test=True, device_test=True, atol=1e-3)
            data_back = transform_to_box(data_mask)
            assert_allclose(data_back["boxes"], data["boxes"], type_test=False, device_test=False, atol=1e-3)
            assert_allclose(data_back["labels"], data["labels"], type_test=False, device_test=False, atol=1e-3)

    @parameterized.expand(TESTS_3D)
    def test_value_3d(
        self,
        keys,
        data,
        expected_convert_result,
        expected_zoom_result,
        expected_zoom_keepsize_result,
        expected_flip_result,
        expected_clip_result,
    ):
        test_dtype = [torch.float32]
        for dtype in test_dtype:
            data = CastToTyped(keys=["image", "boxes"], dtype=dtype)(data)
            # test ConvertBoxToStandardModed
            transform_convert_mode = ConvertBoxModed(**keys)
            convert_result = transform_convert_mode(data)
            assert_allclose(
                convert_result["boxes"], expected_convert_result, type_test=True, device_test=True, atol=1e-3
            )

            # invert_transform_convert_mode = Invertd(
            #     keys=["boxes"], transform=transform_convert_mode, orig_keys=["boxes"]
            # )
            # data_back = invert_transform_convert_mode(convert_result)
            # assert_allclose(data_back["boxes"], data["boxes"], type_test=False, device_test=False, atol=1e-3)

            # # test ZoomBoxd
            # transform_zoom = ZoomBoxd(
            #     image_keys="image", box_keys="boxes", box_ref_image_keys="image", zoom=[0.5, 3, 1.5], keep_size=False
            # )
            # zoom_result = transform_zoom(data)
            # assert_allclose(zoom_result["boxes"], expected_zoom_result, type_test=True, device_test=True, atol=1e-3)
            # invert_transform_zoom = Invertd(
            #     keys=["image", "boxes"], transform=transform_zoom, orig_keys=["image", "boxes"]
            # )
            # data_back = invert_transform_zoom(zoom_result)
            # assert_allclose(data_back["boxes"], data["boxes"], type_test=False, device_test=False, atol=1e-3)
            # assert_allclose(data_back["image"], data["image"], type_test=False, device_test=False, atol=1e-3)

            # transform_zoom = ZoomBoxd(
            #     image_keys="image", box_keys="boxes", box_ref_image_keys="image", zoom=[0.5, 3, 1.5], keep_size=True
            # )
            # zoom_result = transform_zoom(data)
            # assert_allclose(
            #     zoom_result["boxes"], expected_zoom_keepsize_result, type_test=True, device_test=True, atol=1e-3
            # )

            # # test RandZoomBoxd
            # transform_zoom = RandZoomBoxd(
            #     image_keys="image",
            #     box_keys="boxes",
            #     box_ref_image_keys="image",
            #     prob=1.0,
            #     min_zoom=(0.3,) * 3,
            #     max_zoom=(3.0,) * 3,
            #     keep_size=False,
            # )
            # zoom_result = transform_zoom(data)
            # invert_transform_zoom = Invertd(
            #     keys=["image", "boxes"], transform=transform_zoom, orig_keys=["image", "boxes"]
            # )
            # data_back = invert_transform_zoom(zoom_result)
            # assert_allclose(data_back["boxes"], data["boxes"], type_test=False, device_test=False, atol=0.01)
            # assert_allclose(data_back["image"], data["image"], type_test=False, device_test=False, atol=1e-3)

            # # test AffineBoxToImageCoordinated
            # transform_affine = AffineBoxToImageCoordinated(box_keys="boxes", box_ref_image_keys="image")
            # with self.assertRaises(Exception) as context:
            #     transform_affine(data)
            # self.assertTrue("Please check whether it is the correct the image meta key." in str(context.exception))

            # data["image_meta_dict"] = {"affine": torch.diag(1.0 / torch.Tensor([0.5, 3, 1.5, 1]))}
            # affine_result = transform_affine(data)
            # assert_allclose(affine_result["boxes"], expected_zoom_result, type_test=True, device_test=True, atol=0.01)
            # invert_transform_affine = Invertd(keys=["boxes"], transform=transform_affine, orig_keys=["boxes"])
            # data_back = invert_transform_affine(affine_result)
            # assert_allclose(data_back["boxes"], data["boxes"], type_test=False, device_test=False, atol=0.01)

            # # test FlipBoxd
            # transform_flip = FlipBoxd(
            #     image_keys="image", box_keys="boxes", box_ref_image_keys="image", spatial_axis=[0, 1, 2]
            # )
            # flip_result = transform_flip(data)
            # assert_allclose(flip_result["boxes"], expected_flip_result, type_test=True, device_test=True, atol=1e-3)
            # invert_transform_flip = Invertd(
            #     keys=["image", "boxes"], transform=transform_flip, orig_keys=["image", "boxes"]
            # )
            # data_back = invert_transform_flip(flip_result)
            # assert_allclose(data_back["boxes"], data["boxes"], type_test=False, device_test=False, atol=1e-3)
            # assert_allclose(data_back["image"], data["image"], type_test=False, device_test=False, atol=1e-3)

            # # test RandFlipBoxd
            # for spatial_axis in [(0,), (1,), (2,), (0, 1), (1, 2)]:
            #     transform_flip = RandFlipBoxd(
            #         image_keys="image",
            #         box_keys="boxes",
            #         box_ref_image_keys="image",
            #         prob=1.0,
            #         spatial_axis=spatial_axis,
            #     )
            #     flip_result = transform_flip(data)
            #     invert_transform_flip = Invertd(
            #         keys=["image", "boxes"], transform=transform_flip, orig_keys=["image", "boxes"]
            #     )
            #     data_back = invert_transform_flip(flip_result)
            #     assert_allclose(data_back["boxes"], data["boxes"], type_test=False, device_test=False, atol=1e-3)
            #     assert_allclose(data_back["image"], data["image"], type_test=False, device_test=False, atol=1e-3)

            # # test ClipBoxToImaged
            # transform_clip = ClipBoxToImaged(
            #     box_keys="boxes", box_ref_image_keys="image", label_keys=["labels", "scores"], remove_empty=True
            # )
            # clip_result = transform_clip(data)
            # assert_allclose(clip_result["boxes"], expected_clip_result, type_test=True, device_test=True, atol=1e-3)
            # assert_allclose(clip_result["labels"], data["labels"][1:], type_test=True, device_test=True, atol=1e-3)
            # assert_allclose(clip_result["scores"], data["scores"][1:], type_test=True, device_test=True, atol=1e-3)

            # transform_clip = ClipBoxToImaged(
            #     box_keys="boxes", box_ref_image_keys="image", label_keys=[], remove_empty=True
            # )  # corner case when label_keys is empty
            # clip_result = transform_clip(data)
            # assert_allclose(clip_result["boxes"], expected_clip_result, type_test=True, device_test=True, atol=1e-3)

            # # test RandCropBoxByPosNegLabeld
            # transform_crop = RandCropBoxByPosNegLabeld(
            #     image_keys="image", box_keys="boxes", label_keys=["labels", "scores"], spatial_size=2, num_samples=3
            # )
            # crop_result = transform_crop(data)
            # assert len(crop_result) == 3
            # for ll in range(3):
            #     assert_allclose(
            #         crop_result[ll]["boxes"].shape[0],
            #         crop_result[ll]["labels"].shape[0],
            #         type_test=True,
            #         device_test=True,
            #         atol=1e-3,
            #     )
            #     assert_allclose(
            #         crop_result[ll]["boxes"].shape[0],
            #         crop_result[ll]["scores"].shape[0],
            #         type_test=True,
            #         device_test=True,
            #         atol=1e-3,
            #     )


if __name__ == "__main__":
    unittest.main()
