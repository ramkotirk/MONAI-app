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

import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from monai.config import KeysCollection
from monai.data.utils import correct_nifti_header_if_necessary
from monai.utils import ensure_tuple, optional_import

from .utils import is_supported_format

if TYPE_CHECKING:
    import itk  # type: ignore
    import nibabel as nib
    from itk import Image  # type: ignore
    from nibabel.nifti1 import Nifti1Image
    from PIL import Image as PILImage
else:
    itk, _ = optional_import("itk", allow_namespace_pkg=True)
    Image, _ = optional_import("itk", allow_namespace_pkg=True, name="Image")
    nib, _ = optional_import("nibabel")
    Nifti1Image, _ = optional_import("nibabel.nifti1", name="Nifti1Image")
    PILImage, _ = optional_import("PIL.Image")


class ImageReader(ABC):
    """Abstract class to define interface APIs to load image files.
    users need to call `read` to load image and then use `get_data`
    to get the image data and properties from meta data.

    """

    @abstractmethod
    def verify_suffix(self, filename: Union[Sequence[str], str]) -> bool:
        """
        Verify whether the specified file or files format is supported by current reader.

        Args:
            filename: file name or a list of file names to read.
                if a list of files, verify all the suffixes.

        """
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement this method.")

    @abstractmethod
    def read(self, data: Union[Sequence[str], str], **kwargs) -> Union[Sequence[Any], Any]:
        """
        Read image data from specified file or files.
        Note that it returns the raw data, so different readers return different image data type.

        Args:
            data: file name or a list of file names to read.
            kwargs: additional args for actual `read` API of 3rd party libs.

        """
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement this method.")

    @abstractmethod
    def get_data(self, img) -> Tuple[np.ndarray, Dict]:
        """
        Extract data array and meta data from loaded image and return them.
        This function must return 2 objects, first is numpy array of image data, second is dict of meta data.

        Args:
            img: an image object loaded from a image file or a list of image objects.

        """
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement this method.")


class ITKReader(ImageReader):
    """
    Load medical images based on ITK library.
    All the supported image formats can be found:
    https://github.com/InsightSoftwareConsortium/ITK/tree/master/Modules/IO
    The loaded data array will be in C order, for example, a 3D image will be `CDWH`.

    Args:
        kwargs: additional args for `itk.imread` API. more details about available args:
            https://github.com/InsightSoftwareConsortium/ITK/blob/master/Wrapping/Generators/Python/itkExtras.py

    """

    def __init__(self, **kwargs):
        super().__init__()
        self.kwargs = kwargs

    def verify_suffix(self, filename: Union[Sequence[str], str]) -> bool:
        """
        Verify whether the specified file or files format is supported by ITK reader.

        Args:
            filename: file name or a list of file names to read.
                if a list of files, verify all the suffixes.

        """
        return True

    def read(self, data: Union[Sequence[str], str], **kwargs):
        """
        Read image data from specified file or files.
        Note that the returned object is ITK image object or list of ITK image objects.

        Args:
            data: file name or a list of file names to read,
            kwargs: additional args for `itk.imread` API, will override `self.kwargs` for existing keys.
                More details about available args:
                https://github.com/InsightSoftwareConsortium/ITK/blob/master/Wrapping/Generators/Python/itkExtras.py

        """
        img_: List[Image] = list()

        filenames: Sequence[str] = ensure_tuple(data)
        kwargs_ = self.kwargs.copy()
        kwargs_.update(kwargs)
        for name in filenames:
            if os.path.isdir(name):
                # read DICOM series of 1 image in a folder, refer to: https://github.com/RSIP-Vision/medio
                names_generator = itk.GDCMSeriesFileNames.New()
                names_generator.SetUseSeriesDetails(True)
                names_generator.AddSeriesRestriction("0008|0021")  # Series Date
                names_generator.SetDirectory(name)
                series_uid = names_generator.GetSeriesUIDs()

                if len(series_uid) == 0:
                    raise FileNotFoundError(f"no DICOMs in: {name}.")
                if len(series_uid) > 1:
                    raise OSError(f"the directory: {name} contains more than one DICOM series.")

                series_identifier = series_uid[0]
                name = names_generator.GetFileNames(series_identifier)

            img_.append(itk.imread(name, **kwargs_))
        return img_ if len(filenames) > 1 else img_[0]

    def get_data(self, img):
        """
        Extract data array and meta data from loaded image and return them.
        This function returns 2 objects, first is numpy array of image data, second is dict of meta data.
        It constructs `affine`, `original_affine`, and `spatial_shape` and stores in meta dict.
        If loading a list of files, stack them together and add a new dimension as first dimension,
        and use the meta data of the first image to represent the stacked result.

        Args:
            img: a ITK image object loaded from a image file or a list of ITK image objects.

        """
        img_array: List[np.ndarray] = list()
        compatible_meta: Dict = None

        for i in ensure_tuple(img):
            header = self._get_meta_dict(i)
            header["original_affine"] = self._get_affine(i)
            header["affine"] = header["original_affine"].copy()
            header["spatial_shape"] = self._get_spatial_shape(i)
            img_array.append(self._get_array_data(i))

            if compatible_meta is None:
                compatible_meta = header
            else:
                if not np.allclose(header["affine"], compatible_meta["affine"]):
                    raise RuntimeError("affine matrix of all images should be same.")
                if not np.allclose(header["spatial_shape"], compatible_meta["spatial_shape"]):
                    raise RuntimeError("spatial_shape of all images should be same.")

        img_array_ = np.stack(img_array, axis=0) if len(img_array) > 1 else img_array[0]
        return img_array_, compatible_meta

    def _get_meta_dict(self, img) -> Dict:
        """
        Get all the meta data of the image and convert to dict type.

        Args:
            img: a ITK image object loaded from a image file.

        """
        img_meta_dict = img.GetMetaDataDictionary()
        meta_dict = dict()
        for key in img_meta_dict.GetKeys():
            # ignore deprecated, legacy members that cause issues
            if key.startswith("ITK_original_"):
                continue
            meta_dict[key] = img_meta_dict[key]
        meta_dict["origin"] = np.asarray(img.GetOrigin())
        meta_dict["spacing"] = np.asarray(img.GetSpacing())
        meta_dict["direction"] = itk.array_from_matrix(img.GetDirection())
        return meta_dict

    def _get_affine(self, img) -> np.ndarray:
        """
        Get or construct the affine matrix of the image, it can be used to correct
        spacing, orientation or execute spatial transforms.
        Construct Affine matrix based on direction, spacing, origin information.
        Refer to: https://github.com/RSIP-Vision/medio

        Args:
            img: a ITK image object loaded from a image file.

        """
        direction = itk.array_from_matrix(img.GetDirection())
        spacing = np.asarray(img.GetSpacing())
        origin = np.asarray(img.GetOrigin())

        direction = np.asarray(direction)
        affine = np.eye(direction.shape[0] + 1)
        affine[(slice(-1), slice(-1))] = direction @ np.diag(spacing)
        affine[(slice(-1), -1)] = origin
        return affine

    def _get_spatial_shape(self, img) -> Sequence:
        """
        Get the spatial shape of image data, it doesn't contain the channel dim.

        Args:
            img: a ITK image object loaded from a image file.

        """
        shape = list(itk.size(img))
        shape.reverse()
        return shape

    def _get_array_data(self, img) -> np.ndarray:
        """
        Get the raw array data of the image, converted to Numpy array.

        Args:
            img: a ITK image object loaded from a image file.

        """
        return itk.array_view_from_image(img, keep_axes=False)


class NibabelReader(ImageReader):
    """
    Load NIfTI format images based on Nibabel library.

    Args:
        as_closest_canonical: if True, load the image as closest to canonical axis format.
        kwargs: additional args for `nibabel.load` API. more details about available args:
            https://github.com/nipy/nibabel/blob/master/nibabel/loadsave.py

    """

    def __init__(self, as_closest_canonical: bool = False, **kwargs):
        super().__init__()
        self.as_closest_canonical = as_closest_canonical
        self.kwargs = kwargs

    def verify_suffix(self, filename: Union[Sequence[str], str]) -> bool:
        """
        Verify whether the specified file or files format is supported by Nibabel reader.

        Args:
            filename: file name or a list of file names to read.
                if a list of files, verify all the suffixes.

        """
        suffixes: Sequence[str] = ["nii", "nii.gz"]
        return is_supported_format(filename, suffixes)

    def read(self, data: Union[Sequence[str], str], **kwargs):
        """
        Read image data from specified file or files.
        Note that the returned object is Nibabel image object or list of Nibabel image objects.

        Args:
            data: file name or a list of file names to read.
            kwargs: additional args for `nibabel.load` API, will override `self.kwargs` for existing keys.
                More details about available args:
                https://github.com/nipy/nibabel/blob/master/nibabel/loadsave.py

        """
        img_: List[Nifti1Image] = list()

        filenames: Sequence[str] = ensure_tuple(data)
        kwargs_ = self.kwargs.copy()
        kwargs_.update(kwargs)
        for name in filenames:
            img = nib.load(name, **kwargs_)
            img = correct_nifti_header_if_necessary(img)
            img_.append(img)
        return img_ if len(filenames) > 1 else img_[0]

    def get_data(self, img):
        """
        Extract data array and meta data from loaded image and return them.
        This function returns 2 objects, first is numpy array of image data, second is dict of meta data.
        It constructs `affine`, `original_affine`, and `spatial_shape` and stores in meta dict.
        If loading a list of files, stack them together and add a new dimension as first dimension,
        and use the meta data of the first image to represent the stacked result.

        Args:
            img: a Nibabel image object loaded from a image file or a list of Nibabel image objects.

        """
        img_array: List[np.ndarray] = list()
        compatible_meta: Dict = None

        for i in ensure_tuple(img):
            header = self._get_meta_dict(i)
            header["original_affine"] = self._get_affine(i)
            header["affine"] = header["original_affine"].copy()
            if self.as_closest_canonical:
                i = nib.as_closest_canonical(i)
                header["affine"] = self._get_affine(i)
            header["as_closest_canonical"] = self.as_closest_canonical
            header["spatial_shape"] = self._get_spatial_shape(i)
            img_array.append(self._get_array_data(i))

            if compatible_meta is None:
                compatible_meta = header
            else:
                if not np.allclose(header["affine"], compatible_meta["affine"]):
                    raise RuntimeError("affine matrix of all images should be same.")
                if not np.allclose(header["spatial_shape"], compatible_meta["spatial_shape"]):
                    raise RuntimeError("spatial_shape of all images should be same.")

        img_array_ = np.stack(img_array, axis=0) if len(img_array) > 1 else img_array[0]
        return img_array_, compatible_meta

    def _get_meta_dict(self, img) -> Dict:
        """
        Get the all the meta data of the image and convert to dict type.

        Args:
            img: a Nibabel image object loaded from a image file.

        """
        return dict(img.header)

    def _get_affine(self, img) -> np.ndarray:
        """
        Get the affine matrix of the image, it can be used to correct
        spacing, orientation or execute spatial transforms.

        Args:
            img: a Nibabel image object loaded from a image file.

        """
        return img.affine

    def _get_spatial_shape(self, img) -> Sequence:
        """
        Get the spatial shape of image data, it doesn't contain the channel dim.

        Args:
            img: a Nibabel image object loaded from a image file.

        """
        ndim = img.header["dim"][0]
        spatial_rank = min(ndim, 3)
        return list(img.header["dim"][1 : spatial_rank + 1])

    def _get_array_data(self, img) -> np.ndarray:
        """
        Get the raw array data of the image, converted to Numpy array.

        Args:
            img: a Nibabel image object loaded from a image file.

        """
        return np.asarray(img.dataobj)


class NumpyReader(ImageReader):
    """
    Load NPY or NPZ format data based on Numpy library, they can be arrays or pickled objects.
    A typical usage is to load the `mask` data for classification task.
    It can load part of the npz file with specified `npz_keys`.

    Args:
        npz_keys: if loading npz file, only load the specified keys, if None, load all the items.
            stack the loaded items together to construct a new first dimension.
        kwargs: additional args for `numpy.load` API except `allow_pickle`. more details about available args:
            https://numpy.org/doc/stable/reference/generated/numpy.load.html

    """

    def __init__(self, npz_keys: Optional[KeysCollection] = None, **kwargs):
        super().__init__()
        if npz_keys is not None:
            npz_keys = ensure_tuple(npz_keys)
        self.npz_keys = npz_keys
        self.kwargs = kwargs

    def verify_suffix(self, filename: Union[Sequence[str], str]) -> bool:
        """
        Verify whether the specified file or files format is supported by Numpy reader.

        Args:
            filename: file name or a list of file names to read.
                if a list of files, verify all the suffixes.
        """
        suffixes: Sequence[str] = ["npz", "npy"]
        return is_supported_format(filename, suffixes)

    def read(self, data: Union[Sequence[str], str], **kwargs):
        """
        Read image data from specified file or files.
        Note that the returned object is Numpy array or list of Numpy arrays.

        Args:
            data: file name or a list of file names to read.
            kwargs: additional args for `numpy.load` API except `allow_pickle`, will override `self.kwargs` for existing keys.
                More details about available args:
                https://numpy.org/doc/stable/reference/generated/numpy.load.html

        """
        img_: List[Nifti1Image] = list()

        filenames: Sequence[str] = ensure_tuple(data)
        kwargs_ = self.kwargs.copy()
        kwargs_.update(kwargs)
        for name in filenames:
            img = np.load(name, allow_pickle=True, **kwargs_)
            if name.endswith(".npz"):
                # load expected items from NPZ file
                npz_keys = [f"arr_{i}" for i in range(len(img))] if self.npz_keys is None else self.npz_keys
                for k in npz_keys:
                    img_.append(img[k])
            else:
                img_.append(img)

        return img_ if len(img_) > 1 else img_[0]

    def get_data(self, img):
        """
        Extract data array and meta data from loaded data and return them.
        This function returns 2 objects, first is numpy array of image data, second is dict of meta data.
        It constructs `spatial_shape=data.shape` and stores in meta dict if the data is numpy array.
        If loading a list of files, stack them together and add a new dimension as first dimension,
        and use the meta data of the first image to represent the stacked result.

        Args:
            img: a Numpy array loaded from a file or a list of Numpy arrays.

        """
        img_array: List[np.ndarray] = list()
        compatible_meta: Dict = None
        if isinstance(img, np.ndarray):
            img = (img,)

        for i in ensure_tuple(img):
            header = dict()
            if isinstance(i, np.ndarray):
                header["spatial_shape"] = i.shape
            img_array.append(i)

            if compatible_meta is None:
                compatible_meta = header
            else:
                if not np.allclose(header["spatial_shape"], compatible_meta["spatial_shape"]):
                    raise RuntimeError("spatial_shape of all images should be same.")

        img_array_ = np.stack(img_array, axis=0) if len(img_array) > 1 else img_array[0]
        return img_array_, compatible_meta


class PILReader(ImageReader):
    """
    Load common 2D image format (supports PNG, JPG, BMP) file or files from provided path.

    Args:
        converter: additional function to convert the image data after `read()`.
            for example, use `converter=lambda image: image.convert("LA")` to convert image format.
        kwargs: additional args for `Image.open` API in `read()`, mode details about available args:
            https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.open
    """

    def __init__(self, converter: Optional[Callable] = None, **kwargs):
        super().__init__()
        self.converter = converter
        self.kwargs = kwargs

    def verify_suffix(self, filename: Union[Sequence[str], str]) -> bool:
        """
        Verify whether the specified file or files format is supported by PIL reader.

        Args:
            filename: file name or a list of file names to read.
                if a list of files, verify all the suffixes.
        """
        suffixes: Sequence[str] = ["png", "jpg", "bmp"]
        return is_supported_format(filename, suffixes)

    def read(self, data: Union[Sequence[str], str, np.ndarray], **kwargs):
        """
        Read image data from specified file or files.
        Note that the returned object is PIL image or list of PIL image.

        Args:
            data: file name or a list of file names to read.
            kwargs: additional args for `Image.open` API in `read()`, will override `self.kwargs` for existing keys.
                Mode details about available args:
                https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.open

        """
        img_: List[PILImage.Image] = list()

        filenames: Sequence[str] = ensure_tuple(data)
        kwargs_ = self.kwargs.copy()
        kwargs_.update(kwargs)
        for name in filenames:
            img = PILImage.open(name, **kwargs_)
            if callable(self.converter):
                img = self.converter(img)
            img_.append(img)

        return img_ if len(filenames) > 1 else img_[0]

    def get_data(self, img):
        """
        Extract data array and meta data from loaded data and return them.
        This function returns 2 objects, first is numpy array of image data, second is dict of meta data.
        It constructs `spatial_shape` and stores in meta dict.
        If loading a list of files, stack them together and add a new dimension as first dimension,
        and use the meta data of the first image to represent the stacked result.

        Args:
            img: a PIL Image object loaded from a file or a list of PIL Image objects.

        """
        img_array: List[np.ndarray] = list()
        compatible_meta: Dict = None

        for i in ensure_tuple(img):
            header = self._get_meta_dict(i)
            header["spatial_shape"] = self._get_spatial_shape(i)
            img_array.append(np.asarray(i))

            if compatible_meta is None:
                compatible_meta = header
            else:
                if not np.allclose(header["spatial_shape"], compatible_meta["spatial_shape"]):
                    raise RuntimeError("spatial_shape of all images should be same.")

        img_array_ = np.stack(img_array, axis=0) if len(img_array) > 1 else img_array[0]
        return img_array_, compatible_meta

    def _get_meta_dict(self, img) -> Dict:
        """
        Get the all the meta data of the image and convert to dict type.
        Args:
            img: a PIL Image object loaded from a image file.

        """
        meta = dict()
        meta["format"] = img.format
        meta["mode"] = img.mode
        meta["width"] = img.width
        meta["height"] = img.height
        meta["info"] = img.info
        return meta

    def _get_spatial_shape(self, img) -> Sequence:
        """
        Get the spatial shape of image data, it doesn't contain the channel dim.
        Args:
            img: a PIL Image object loaded from a image file.
        """
        return [img.width, img.height]
