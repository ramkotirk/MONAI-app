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

from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

from monai.config.type_definitions import NdarrayOrTensor
from monai.transforms.transform import Transform
from monai.transforms.utils_pytorch_numpy_unification import unique
from monai.utils import convert_to_numpy, optional_import
from monai.utils.enums import TransformBackends
from monai.utils.misc import ensure_tuple_rep
from monai.utils.type_conversion import convert_to_dst_type

find_contours, _ = optional_import("skimage.measure", name="find_contours")
centroid, _ = optional_import("skimage.measure", name="centroid")

__all__ = ["GenerateSuccinctContour", "GenerateInstanceContour", "GenerateInstanceCentroid", "GenerateInstanceType"]


class GenerateSuccinctContour(Transform):
    """
    Converts Scipy-style contours(generated by skimage.measure.find_contours) to a more succinct version which only includes
    the pixels to which lines need to be drawn (i.e. not the intervening pixels along each line).

    Args:
        height: height of bounding box, used to detect direction of line segment.
        width: width of bounding box, used to detect direction of line segment.

    Returns:
        the pixels that need to be joined by straight lines to describe the outmost pixels of the foreground similar to
            OpenCV's cv.CHAIN_APPROX_SIMPLE (anti-clockwise)
    """

    backend = [TransformBackends.NUMPY]

    def __init__(self, height: int, width: int) -> None:
        self.height = height
        self.width = width

    def _generate_contour_coord(self, current: np.ndarray, previous: np.ndarray) -> Tuple[int, int]:
        """
        Generate contour coordinates. Given the previous and current coordinates of border positions,
        returns the int pixel that marks the extremity of the segmented pixels.

        Args:
            current: coordinates of the current border position.
            previous: coordinates of the previous border position.
        """

        p_delta = (current[0] - previous[0], current[1] - previous[1])

        if p_delta == (0.0, 1.0) or p_delta == (0.5, 0.5) or p_delta == (1.0, 0.0):
            row = int(current[0] + 0.5)
            col = int(current[1])
        elif p_delta == (0.0, -1.0) or p_delta == (0.5, -0.5):
            row = int(current[0])
            col = int(current[1])
        elif p_delta == (-1, 0.0) or p_delta == (-0.5, -0.5):
            row = int(current[0])
            col = int(current[1] + 0.5)
        elif p_delta == (-0.5, 0.5):
            row = int(current[0] + 0.5)
            col = int(current[1] + 0.5)

        return row, col

    def _calculate_distance_from_topleft(self, sequence: Sequence[Tuple[int, int]]) -> int:
        """
        Each sequence of coordinates describes a boundary between foreground and background starting and ending at two sides
        of the bounding box. To order the sequences correctly, we compute the distance from the topleft of the bounding box
        around the perimeter in a clockwise direction.

        Args:
            sequence: list of border points coordinates.

        Returns:
            the distance round the perimeter of the bounding box from the top-left origin
        """
        distance: int
        first_coord = sequence[0]
        if first_coord[0] == 0:
            distance = first_coord[1]
        elif first_coord[1] == self.width - 1:
            distance = self.width + first_coord[0]
        elif first_coord[0] == self.height - 1:
            distance = 2 * self.width + self.height - first_coord[1]
        else:
            distance = 2 * (self.width + self.height) - first_coord[0]

        return distance

    def __call__(self, contours: List[np.ndarray]) -> np.ndarray:
        """
        Args:
            contours: list of (n, 2)-ndarrays, scipy-style clockwise line segments, with lines separating foreground/background.
                Each contour is an ndarray of shape (n, 2), consisting of n (row, column) coordinates along the contour.
        """
        pixels: List[Tuple[int, int]] = []
        sequences = []
        corners = [False, False, False, False]

        for group in contours:
            sequence: List[Tuple[int, int]] = []
            last_added = None
            prev = None
            corner = -1

            for i, coord in enumerate(group):
                if i == 0:
                    # originating from the top, so must be heading south east
                    if coord[0] == 0.0:
                        corner = 1
                        pixel = (0, int(coord[1] - 0.5))
                        if pixel[1] == self.width - 1:
                            corners[1] = True
                        elif pixel[1] == 0.0:
                            corners[0] = True
                    # originating from the left, so must be heading north east
                    elif coord[1] == 0.0:
                        corner = 0
                        pixel = (int(coord[0] + 0.5), 0)
                    # originating from the bottom, so must be heading north west
                    elif coord[0] == self.height - 1:
                        corner = 3
                        pixel = (int(coord[0]), int(coord[1] + 0.5))
                        if pixel[1] == self.width - 1:
                            corners[2] = True
                    # originating from the right, so must be heading south west
                    elif coord[1] == self.width - 1:
                        corner = 2
                        pixel = (int(coord[0] - 0.5), int(coord[1]))
                    sequence.append(pixel)
                    last_added = pixel
                elif i == len(group) - 1:
                    # add this point
                    pixel = self._generate_contour_coord(coord, prev)  # type: ignore
                    if pixel != last_added:
                        sequence.append(pixel)
                        last_added = pixel
                elif np.any(coord - prev != group[i + 1] - coord):
                    pixel = self._generate_contour_coord(coord, prev)  # type: ignore
                    if pixel != last_added:
                        sequence.append(pixel)
                        last_added = pixel

                # flag whether each corner has been crossed
                if i == len(group) - 1:
                    if corner == 0:
                        if coord[0] == 0:
                            corners[corner] = True
                    elif corner == 1:
                        if coord[1] == self.width - 1:
                            corners[corner] = True
                    elif corner == 2:
                        if coord[0] == self.height - 1:
                            corners[corner] = True
                    elif corner == 3:
                        if coord[1] == 0.0:
                            corners[corner] = True

                prev = coord
            dist = self._calculate_distance_from_topleft(sequence)

            sequences.append({"distance": dist, "sequence": sequence})

        # check whether we need to insert any missing corners
        if corners[0] is False:
            sequences.append({"distance": 0, "sequence": [(0, 0)]})
        if corners[1] is False:
            sequences.append({"distance": self.width, "sequence": [(0, self.width - 1)]})
        if corners[2] is False:
            sequences.append({"distance": self.width + self.height, "sequence": [(self.height - 1, self.width - 1)]})
        if corners[3] is False:
            sequences.append({"distance": 2 * self.width + self.height, "sequence": [(self.height - 1, 0)]})

        # join the sequences into a single contour
        # starting at top left and rotating clockwise
        sequences.sort(key=lambda x: x.get("distance"))  # type: ignore

        last = (-1, -1)
        for _sequence in sequences:
            if _sequence["sequence"][0] == last:  # type: ignore
                pixels.pop()
            if pixels:
                pixels = [*pixels, *_sequence["sequence"]]  # type: ignore
            else:
                pixels = _sequence["sequence"]  # type: ignore
            last = pixels[-1]

        if pixels[0] == last:
            pixels.pop(0)

        if pixels[0] == (0, 0):
            pixels.append(pixels.pop(0))

        return np.flip(convert_to_numpy(pixels, dtype=np.int32))  # type: ignore


class GenerateInstanceContour(Transform):
    """
    Generate contour for each instance in a 2D array. Use `GenerateSuccinctContour` to only include
    the pixels to which lines need to be drawn

    Args:
        points_num: assumed that the created contour does not form a contour if it does not contain more points
            than the specified value. Defaults to 3.
        level: optional. Value along which to find contours in the array. By default, the level is set
            to (max(image) + min(image)) / 2.

    """
    def __init__(self, points_num: int = 3, level: Optional[float] = None) -> None:
        self.level = level
        self.points_num = points_num

    def __call__(self, image: NdarrayOrTensor, offset: Optional[Sequence[int]] = (0, 0)) -> np.ndarray:
        """
        Args:
            image: instance-level segmentation result. Shape should be [C, H, W]
            offset: optional, offset of starting position of the instance in the array, default is (0, 0).
        """
        inst_contour_cv = find_contours(image, level=self.level)
        generate_contour = GenerateSuccinctContour(image.shape[0], image.shape[1])
        inst_contour = generate_contour(inst_contour_cv)

        # < `self.points_num` points don't make a contour, so skip, likely artifact too
        # as the contours obtained via approximation => too small or sthg
        if inst_contour.shape[0] < self.points_num:
            print(f"< {self.points_num} points don't make a contour, so skip")
            return False
        elif len(inst_contour.shape) != 2:
            print(f"{len(inst_contour.shape)} != 2, check for tricky shape")
            return False  # ! check for tricky shape
        else:
            inst_contour[:, 0] += offset[0]  # X
            inst_contour[:, 1] += offset[1]  # Y
            return inst_contour


class GenerateInstanceCentroid(Transform):
    """
    Generate instance centroid using `skimage.measure.centroid`.

    Args:
        dtype: the data type of output centroid.

    """
    def __init__(self, dtype: Optional[DtypeLike] = None) -> None:
        self.dtype = dtype

    def __call__(self, image: NdarrayOrTensor, offset: Union[Sequence[int], int] = 0) -> np.ndarray:
        """
        Args:
            image: instance-level segmentation result. Shape should be [1, H, W, [D]]
            offset: optional, offset of starting position of the instance in the array, default is 0 for each dim.

        """
        image = convert_to_numpy(image)
        image = image.squeeze(0) # squeeze channel dim
        ndim = len(image.shape)
        offset = ensure_tuple_rep(offset, ndim)

        inst_centroid = centroid(image)
        for i in range(ndim):
            inst_centroid[i] += offset[i]

        return convert_to_dst_type(inst_centroid, image, dtype=self.dtype)


class GenerateInstanceType(Transform):
    """
    Generate instance type and probability for each instance.
    """
    def __init__(self) -> None:
        super().__init__()

    def __call__(self, bbox, type_pred, seg_pred, instance_id):
        """
        Args:
            bbox: bounding box coordinates of the instance, shape is [channel, 2 * spatial dims].
            type_pred: pixel-level type prediction map after activation function.
            seg_pred: pixel-level segmentation prediction map after activation function.
            instance_id: get instance type from specified instance id.
        """

        rmin, rmax, cmin, cmax = bbox.flatten()
        seg_map_crop = seg_pred[0, rmin:rmax, cmin:cmax]
        type_map_crop = type_pred[0, rmin:rmax, cmin:cmax]

        seg_map_crop = seg_map_crop == instance_id
        inst_type = type_map_crop[seg_map_crop]  # type: ignore
        type_list = unique(inst_type)
        type_pixels = len(type_list)
        type_list = list(zip(type_list, type_pixels))
        type_list = sorted(type_list, key=lambda x: x[1], reverse=True)  # type: ignore
        inst_type = type_list[0][0]
        if inst_type == 0:  # ! pick the 2nd most dominant if exist
            if len(type_list) > 1:
                inst_type = type_list[1][0]
        type_dict = {v[0]: v[1] for v in type_list}
        type_prob = type_dict[inst_type] / (sum(seg_map_crop) + 1.0e-6)

        return int(inst_type), float(type_prob)
