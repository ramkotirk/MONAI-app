/*
Copyright 2020 MONAI Consortium
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

#include <torch/extension.h>
#include <math.h>

struct Indexer
{
public:
    Indexer(int dimensions, int64_t* sizes)
    {
        m_dimensions = dimensions;
        m_sizes = sizes;
        m_index = new int[dimensions]{0};
    }

    bool operator++(int)
    {
        for(int i = 0; i < m_dimensions; i++)
        {
            m_index[i] += 1;

            if(m_index[i] < m_sizes[i])
            {
                return true;
            }
            else
            {
                m_index[i] = 0;
            }
        }

        return false;
    }

    int& operator[](int dimensionIndex)
    {
        return m_index[dimensionIndex];
    }

private:
    int m_dimensions;
    int64_t* m_sizes;
    int* m_index;
};

torch::Tensor BilateralFilterCpu(torch::Tensor input, float spatialSigma, float colorSigma)
{
    // Prepare output tensor
    torch::Tensor output = torch::zeros_like(input);

    // Tensor descriptors.
    int batchCount = input.size(0);
    int channelCount = input.size(1);

    int batchStride = input.stride(0);
    int channelStride = input.stride(1);

    int spatialDimensionCount = input.dim() - 2;
    int64_t* spatialDimensionSizes = (int64_t*)input.sizes().data() + 2;
    int64_t* spatialDimensionStrides = (int64_t*)input.strides().data() + 2;

    // Raw tensor data pointers. 
    float* inputData = input.data_ptr<float>();
    float* outputData = output.data_ptr<float>();

    // Pre-calculate common values
    int windowSize = ceil(3 * spatialSigma);
    int halfWindowSize = 0.5f * windowSize;
    float spatialExpConstant = -1.0f / (2 * spatialSigma * spatialSigma);
    float colorExpConstant = -1.0f / (2 * colorSigma * colorSigma);

    // Kernel size array
    int64_t* kernelSize = new int64_t[spatialDimensionCount];

    for (int i = 0; i < spatialDimensionCount; i++)
    {
        kernelSize[i] = windowSize;
    }

    // Pre-calculate gaussian kernel in 1D.
    float* gaussianKernel = new float[windowSize];

    for (int i = 0; i < windowSize; i++)
    {
        int distance = i - halfWindowSize;
        gaussianKernel[i] = exp(distance * spatialExpConstant);
    }

    // Kernel aggregates used to calculate
    // the output value.
    float* valueSum = new float[channelCount];
    float weightSum = 0;

    // Looping over the batches
    for (int b = 0; b < batchCount; b++)
    {
        int batchOffset = b * batchStride;

        // Looping over all dimensions for the home element
        Indexer homeIndex = Indexer(spatialDimensionCount, spatialDimensionSizes);
        do // while(homeIndex++)
        {
            // Calculating indexing offset for the home element
            int homeOffset = batchOffset;

            for(int i = 0; i < spatialDimensionCount; i++)
            {
                homeOffset += homeIndex[i] * spatialDimensionStrides[i];
            }

            // Zero kernel aggregates.
            for(int i = 0; i < channelCount; i++)
            {
                valueSum[i] = 0;
            }

            weightSum = 0.0f;

            // Looping over all dimensions for the neighbour element
            Indexer kernelIndex = Indexer(spatialDimensionCount, kernelSize);
            do // while(kernelIndex++)
            {
                // Calculating buffer offset for the neighbour element
                // Index is clamped to the border in each dimension.
                int neighbourOffset = batchOffset;

                for(int i = 0; i < spatialDimensionCount; i++)
                {
                    int neighbourIndex = homeIndex[i] + kernelIndex[i] - halfWindowSize;
                    int neighbourIndexClamped = std::min((int)spatialDimensionSizes[i] - 1, std::max(0, neighbourIndex));
                    neighbourOffset += neighbourIndexClamped * spatialDimensionStrides[i];
                }


                // Euclidean color distance.
                float colorDistanceSquared = 0;

                for (int i = 0; i < channelCount; i++)
                {
                    float diff = inputData[homeOffset + i * channelStride] - inputData[neighbourOffset + i * channelStride];
                    colorDistanceSquared += diff * diff;
                }

                // Calculating and combining the spatial 
                // and color weights.
                float spatialWeight = 1;

                for (int i = 0; i < spatialDimensionCount; i++)
                {
                    spatialWeight *= gaussianKernel[kernelIndex[i]];
                }

                float colorWeight = exp(colorDistanceSquared * colorExpConstant);
                float totalWeight = spatialWeight * colorWeight;

                // Aggregating values.
                for (int i = 0; i < channelCount; i++)
                {
                    valueSum[i] += inputData[neighbourOffset + i * channelStride] * totalWeight;
                }

                weightSum += totalWeight;
            } 
            while(kernelIndex++);


            for (int i = 0; i < channelCount; i++)
            {
                outputData[homeOffset + i * channelStride] = valueSum[i] / weightSum;
            }
        } 
        while(homeIndex++);
    } 

    return output;
}
