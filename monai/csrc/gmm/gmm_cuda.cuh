/*
Copyright 2020 - 2021 MONAI Consortium
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

#include <cuda.h>
#include <cuda_runtime.h>

#include "utils/tensor_description.h"

#define BLOCK_SIZE 32
#define TILE(SIZE, STRIDE) (((SIZE - 1)/STRIDE) + 1)

cudaError_t GMMAssign(int gmmN, const float *gmm, int gmm_pitch, const uchar4 *image, unsigned char *alpha, int width, int height);
cudaError_t GMMInitialize(int gmm_N, float *gmm, float *scratch_mem, int gmm_pitch, const uchar4 *image, unsigned char *alpha, int width, int height);
cudaError_t GMMUpdate(int gmm_N, float *gmm, float *scratch_mem, int gmm_pitch, const uchar4 *image, unsigned char *alpha, int width, int height);
cudaError_t GMMDataTerm(const uchar4 *image, int gmmN, const float *gmm, int gmm_pitch, float* output, int width, int height);

void INPUT(float* input, int* labels, int width, int height, int channel_stride, uchar4* image, unsigned char* trimap);

void ErrorCheck(const char* name)
{
    cudaDeviceSynchronize();
    py::print(name, ": ", cudaGetErrorString(cudaGetLastError()));
}

torch::Tensor GMM_Cuda(torch::Tensor input_tensor, torch::Tensor label_tensor, int mixture_count, int gaussians_per_mixture)
{
    //#################################


    TensorDescription desc = TensorDescription(input_tensor);

    int width = desc.sizes[0];
    int height = desc.sizes[1];

    torch::Tensor output = torch::empty({desc.batchCount, mixture_count, width, height}, torch::dtype(torch::kFloat32).device(torch::kCUDA));

    //#################################

    int gmms = mixture_count * gaussians_per_mixture;

    int blocks = TILE(width, BLOCK_SIZE) * TILE(height, BLOCK_SIZE);
    size_t gmm_pitch = 11 * sizeof(float);

    uchar4* d_image;
    cudaMalloc(&d_image, width * height * sizeof(float));
    
    unsigned char* d_trimap;
    cudaMalloc(&d_trimap, width * height * sizeof(unsigned char));

    unsigned char* d_alpha;
    cudaMalloc(&d_alpha, width * height * sizeof(unsigned char));
    
    float* d_scratch_mem;
    int scratch_gmm_size = blocks * gmm_pitch * gmms + blocks * 4;
    cudaMalloc(&d_scratch_mem, scratch_gmm_size);

    float* d_gmm;
    cudaMalloc(&d_gmm, gmm_pitch * gmms);

    //#################################

    INPUT(input_tensor.data_ptr<float>(), label_tensor.data_ptr<int>(), width, height, width * height, d_image, d_trimap);

    cudaMemcpyAsync(d_alpha, d_trimap, width * height * sizeof(unsigned char), cudaMemcpyDeviceToDevice);

    GMMInitialize(gmms, d_gmm, d_scratch_mem, gmm_pitch, d_image, d_alpha, width, height);

    GMMUpdate(gmms, d_gmm, d_scratch_mem, gmm_pitch, d_image, d_alpha, width, height);

    GMMDataTerm(d_image, gmms, d_gmm, gmm_pitch, output.data_ptr<float>(), width, height);

    return output;
}
