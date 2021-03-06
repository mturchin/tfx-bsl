// Copyright 2019 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
#ifndef TFX_BSL_CC_ARROW_ARRAY_UTIL_H_
#define TFX_BSL_CC_ARROW_ARRAY_UTIL_H_

#include <cstddef>
#include <memory>

#include "tfx_bsl/cc/util/status.h"

namespace arrow {
class Array;
}  // namespace arrow

namespace tfx_bsl {

// Get lengths of elements from list-alike `array` (including binary arrays and
// string arrays) in an int32 array.
// Note that null and empty elements both are of length 0 and the returned array
// does not have any null. For example
// [[1,2,3], [], None, [4,5]] => [3, 0, 0, 2]
Status GetElementLengths(
    const arrow::Array& array,
    std::shared_ptr<arrow::Array>* list_lengths_array);

// Makes a int32 array of the same length as flattened `list_array`.
// returned_array[i] == j means i-th element in flattened `list_array`
// came from j-th list in `list_array`.
// For example [[1,2,3], [], None, [4,5]] => [0, 0, 0, 3, 3]
Status GetFlattenedArrayParentIndices(
    const arrow::Array& array,
    std::shared_ptr<arrow::Array>* parent_indices_array);

// Makes a uint8 array of the same length as `array`.
// returned_array[i] == True iff array[i] is null.
// Note that this returned array can be converted to a numpy bool array
// copy-free.
Status GetArrayNullBitmapAsByteArray(
    const arrow::Array& array,
    std::shared_ptr<arrow::Array>* byte_array);

// Returns the total byte size of a BinaryArray (note that StringArray is a
// subclass of that so is also accepted here) i.e. the length of the
// concatenation of all the binary strings in the list), in a Python Long.
// It might be a good idea to make this a pyarrow API.
Status GetBinaryArrayTotalByteSize(const arrow::Array& array,
                                   size_t* total_byte_size);

// Get counts of values in the array. Returns a struct array <values, counts>.
Status ValueCounts(
    const std::shared_ptr<arrow::Array>& array,
    std::shared_ptr<arrow::Array>* values_and_counts_array);

// Makes an Arrow ListArray from parent indices and values.
// For example, if num_parents = 6, parent_indices = [0, 1, 1, 3, 3] and
// values_array_py is (an arrow Array of) [0, 1, 2, 3, 4], then the result will
// be a ListArray of integers: [[0], [1, 2], None, [3, 4], None].
// `num_parents` must be a Python integer (int or long) and it must be greater
// than or equal to max(parent_indices) + 1.
// `parent_indices` must be a int64 1-D numpy array and the indices must be
// sorted in increasing order.
// `values_array` must be an arrow Array and its length must equal to the
//  length of `parent_indices`.
Status MakeListArrayFromParentIndicesAndValues(
    size_t num_parents,
    const std::shared_ptr<arrow::Array>& parent_indices,
    const std::shared_ptr<arrow::Array>& values_array,
    std::shared_ptr<arrow::Array>* output_list_array);

// Converts a ListArray to a COO (coordinate list) represented sparse tensor.
// `list_array` should be a ListArray<InnerArray> where InnerArray is
// ListArray<InnerArray> or any primitive array or binary array (i.e. nested
// lists are supported). Two arrays are produced:
// `coo_array` is an Int64Array that contains the coordinates of flattened
// values of `list_array`. If `list_array` is N-nested (ListArray<primitive> is
// 1-nested), each coordinate will contain N + 1 numbers.
// `coo_array`[(i*N):(i*(N+1))] contains the coordinates of the i-th value.
// `dense_shape_array` is an Int64Array that contains the size of the
// bounding-box of `list_array`.
// Note that nulls and empty lists are not distinguished in the COO form.
// For example:
// if given ListArray [[1, 2], [], [3], None]
// `coo_array` would be: [0, 1,  0, 2,  2, 1]
// `dense_shape_array` would be: [4, 2]
Status CooFromListArray(
    const std::shared_ptr<arrow::Array>& list_array,
    std::shared_ptr<arrow::Array>* coo_array,
    std::shared_ptr<arrow::Array>* dense_shape_array);

// Fills nulls in a `list_array` with `fill_with`. the type of `fill_with` must
// equal to the value type of `list_array`.
Status FillNullLists(const std::shared_ptr<arrow::Array>& list_array,
                     const std::shared_ptr<arrow::Array>& fill_with,
                     std::shared_ptr<arrow::Array>* filled);

}  // namespace tfx_bsl
#endif  // TFX_BSL_CC_ARROW_ARRAY_UTIL_H_
