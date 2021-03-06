# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for tfx_bsl.tfxio.tensor_adapter."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import six
from tfx_bsl.pyarrow_tf import pyarrow as pa
from tfx_bsl.pyarrow_tf import tensorflow as tf
from tfx_bsl.tfxio import tensor_adapter

from google.protobuf import text_format
from absl.testing import absltest
from absl.testing import parameterized
from tensorflow.python.framework import test_util  # pylint: disable=g-direct-tensorflow-import
from tensorflow_metadata.proto.v0 import schema_pb2


_ALL_SUPPORTED_INT_VALUE_TYPES = [
    pa.int8(), pa.int16(), pa.int32(), pa.int64(),
    pa.uint8(), pa.uint16(), pa.uint32(), pa.uint64(),
]
_ALL_SUPPORTED_FLOATING_VALUE_TYPES = [pa.float32(), pa.float64()]
_ALL_SUPPORTED_STRING_VALUE_TYPES = [pa.binary()]
_ALL_SUPPORTED_VALUE_TYPES = (
    _ALL_SUPPORTED_INT_VALUE_TYPES + _ALL_SUPPORTED_FLOATING_VALUE_TYPES +
    _ALL_SUPPORTED_STRING_VALUE_TYPES)
_ARROW_TYPE_TO_TF_TYPE = {
    pa.int8(): tf.int8,
    pa.int16(): tf.int16,
    pa.int32(): tf.int32,
    pa.int64(): tf.int64,
    pa.uint8(): tf.uint8,
    pa.uint16(): tf.uint16,
    pa.uint32(): tf.uint32,
    pa.uint64(): tf.uint64,
    pa.float32(): tf.float32,
    pa.float64(): tf.float64,
    pa.binary(): tf.string,
}
_ARROW_TYPE_TO_NP_TYPE = {
    pa.int8(): np.dtype("int8"),
    pa.int16(): np.dtype("int16"),
    pa.int32(): np.dtype("int32"),
    pa.int64(): np.dtype("int64"),
    pa.uint8(): np.dtype("uint8"),
    pa.uint16(): np.dtype("uint16"),
    pa.uint32(): np.dtype("uint32"),
    pa.uint64(): np.dtype("uint64"),
    pa.float32(): np.dtype("float32"),
    pa.float64(): np.dtype("float64"),
    pa.binary(): np.dtype("object"),
}


def _MakeDenseTensorFromListArrayTestCases():
  result = []
  tensor_representation_textpb = """
  dense_tensor {
    column_name: "input"
    shape {
      dim {
        size: 4
      }
    }
  }
  """
  for t in _ALL_SUPPORTED_VALUE_TYPES:
    expected_type_spec = tf.TensorSpec([None, 4], _ARROW_TYPE_TO_TF_TYPE[t])

    if pa.types.is_integer(t):
      values = [[1, 2, 3, 4], [5, 6, 7, 8]]
    elif pa.types.is_floating(t):
      values = [[1.0, 2.0, 4.0, 8.0], [-1.0, -2.0, -4.0, -8.0]]
    else:
      values = [[b"a", b"b", b"c", b"d"], [b"e", b"f", b"g", b"h"]]

    arrow_array = pa.array(values, type=pa.list_(t))
    if tf.executing_eagerly():
      expected_output = tf.constant(values, dtype=_ARROW_TYPE_TO_TF_TYPE[t])
    else:
      expected_output = np.array(values, dtype=_ARROW_TYPE_TO_NP_TYPE[t])

    result.append({
        "testcase_name": "dense_from_list_array_{}".format(t),
        "tensor_representation_textpb": tensor_representation_textpb,
        "arrow_array": arrow_array,
        "expected_output": expected_output,
        "expected_type_spec": expected_type_spec,
    })

  return result


def _MakeIntDefaultFilledDenseTensorFromListArrayTestCases():
  tensor_representation_textpb = """
  dense_tensor {
    column_name: "input"
    shape {
      dim {
        size: 2
      }
      dim {
        size: 2
      }
    }
    default_value {
      int_value: 2
    }
  }
  """
  result = []
  for t in _ALL_SUPPORTED_INT_VALUE_TYPES:
    arrow_array = pa.array([None, [1, 2, 3, 4], None], type=pa.list_(t))
    if tf.executing_eagerly():
      expected_output = tf.constant(
          [[2, 2, 2, 2], [1, 2, 3, 4], [2, 2, 2, 2]],
          dtype=_ARROW_TYPE_TO_TF_TYPE[t],
          shape=(3, 2, 2))
    else:
      expected_output = np.array(
          [2, 2, 2, 2, 1, 2, 3, 4, 2, 2, 2, 2],
          dtype=_ARROW_TYPE_TO_NP_TYPE[t]).reshape((3, 2, 2))
    result.append({
        "testcase_name": "default_filled_dense_from_list_array_{}".format(t),
        "tensor_representation_textpb": tensor_representation_textpb,
        "arrow_array": arrow_array,
        "expected_output": expected_output,
        "expected_type_spec": tf.TensorSpec([None, 2, 2],
                                            _ARROW_TYPE_TO_TF_TYPE[t])
    })
  return result


def _MakeFloatingDefaultFilledDenseTensorFromListArrayTestCases():
  tensor_representation_textpb = """
  dense_tensor {
    column_name: "input"
    shape {
      dim {
        size: 2
      }
      dim {
        size: 1
      }
    }
    default_value {
      float_value: -1
    }
  }
  """
  result = []
  for t in _ALL_SUPPORTED_FLOATING_VALUE_TYPES:
    arrow_array = pa.array([None, [1, 2], None], type=pa.list_(t))
    if tf.executing_eagerly():
      expected_output = tf.constant([[-1, -1], [1, 2], [-1, -1]],
                                    dtype=_ARROW_TYPE_TO_TF_TYPE[t],
                                    shape=(3, 2, 1))
    else:
      expected_output = np.array(
          [-1, -1, 1, 2, -1, -1],
          dtype=_ARROW_TYPE_TO_NP_TYPE[t]).reshape((3, 2, 1))
    result.append({
        "testcase_name": "default_filled_dense_from_list_array_{}".format(t),
        "tensor_representation_textpb": tensor_representation_textpb,
        "arrow_array": arrow_array,
        "expected_output": expected_output,
        "expected_type_spec": tf.TensorSpec([None, 2, 1],
                                            dtype=_ARROW_TYPE_TO_TF_TYPE[t])
    })
  return result


def _MakeStringDefaultFilledDenseTensorFromListArrayTestCases():
  tensor_representation_textpb = """
  dense_tensor {
    column_name: "input"
    shape {
    }
    default_value {
      bytes_value: "nil"
    }
  }
  """
  result = []
  for t in _ALL_SUPPORTED_STRING_VALUE_TYPES:
    arrow_array = pa.array([None, ["hello"], None], type=pa.list_(t))
    if tf.executing_eagerly():
      expected_output = tf.constant(["nil", "hello", "nil"],
                                    dtype=_ARROW_TYPE_TO_TF_TYPE[t])
    else:
      expected_output = np.array([b"nil", b"hello", b"nil"],
                                 dtype=_ARROW_TYPE_TO_NP_TYPE[t])
    result.append({
        "testcase_name": "default_filled_dense_from_list_array_{}".format(t),
        "tensor_representation_textpb": tensor_representation_textpb,
        "arrow_array": arrow_array,
        "expected_output": expected_output,
        "expected_type_spec": tf.TensorSpec([None], _ARROW_TYPE_TO_TF_TYPE[t])
    })
  return result


def _MakeVarLenSparseTensorFromListArrayTestCases():
  tensor_representation_textpb = """
  varlen_sparse_tensor {
    column_name: "input"
  }
  """
  result = []
  for t in _ALL_SUPPORTED_VALUE_TYPES:
    if pa.types.is_integer(t):
      values = [[1, 2], None, [3], [], [5]]
      expected_values = [1, 2, 3, 5]
    elif pa.types.is_floating(t):
      values = [[1.0, 2.0], None, [3.0], [], [5.0]]
      expected_values = [1.0, 2.0, 3.0, 5.0]
    else:
      values = [["a", "b"], None, ["c"], [], ["d"]]
      expected_values = [b"a", b"b", b"c", b"d"]
    expected_sparse_indices = [[0, 0], [0, 1], [2, 0], [4, 0]]
    expected_dense_shape = [5, 2]
    if tf.executing_eagerly():
      expected_output = tf.sparse.SparseTensor(
          indices=expected_sparse_indices,
          dense_shape=expected_dense_shape,
          values=tf.constant(expected_values,
                             dtype=_ARROW_TYPE_TO_TF_TYPE[t]))
    else:
      expected_output = tf.compat.v1.SparseTensorValue(
          indices=np.array(expected_sparse_indices, dtype=np.int64),
          dense_shape=np.array(expected_dense_shape, dtype=np.int64),
          values=np.array(expected_values, dtype=_ARROW_TYPE_TO_NP_TYPE[t]))
    result.append({
        "testcase_name":
            "varlen_sparse_from_list_array_{}".format(t),
        "tensor_representation_textpb":
            tensor_representation_textpb,
        "arrow_array":
            pa.array(values, type=pa.list_(t)),
        "expected_output":
            expected_output,
        "expected_type_spec":
            tf.SparseTensorSpec(tf.TensorShape([None, None]),
                                _ARROW_TYPE_TO_TF_TYPE[t])
    })

  return result


_ONE_TENSOR_TEST_CASES = (
    _MakeDenseTensorFromListArrayTestCases() +
    _MakeIntDefaultFilledDenseTensorFromListArrayTestCases() +
    _MakeFloatingDefaultFilledDenseTensorFromListArrayTestCases() +
    _MakeStringDefaultFilledDenseTensorFromListArrayTestCases() +
    _MakeVarLenSparseTensorFromListArrayTestCases()
)
_INVALID_DEFAULT_VALUE_TEST_CASES = [
    dict(
        testcase_name="default_value_not_set",
        value_type=pa.int64(),
        default_value_pbtxt="",
        exception_regexp="Incompatible default value"),
    dict(
        testcase_name="mismatch_type",
        value_type=pa.binary(),
        default_value_pbtxt="float_value: 1.0",
        exception_regexp="Incompatible default value",
    ),
    dict(
        testcase_name="integer_out_of_range_int64_uint64max",
        value_type=pa.int64(),
        default_value_pbtxt="uint_value: 0xffffffffffffffff",
        exception_regexp="Integer default value out of range",
    ),
    dict(
        testcase_name="integer_out_of_range_int32_int64max",
        value_type=pa.int32(),
        default_value_pbtxt="int_value: 0x7fffffffffffffff",
        exception_regexp="Integer default value out of range",
    ),
]


class TensorAdapterTest(parameterized.TestCase, tf.test.TestCase):

  def assertSparseAllEqual(self, a, b):
    self.assertAllEqual(a.indices, b.indices)
    self.assertAllEqual(a.values, b.values)
    self.assertAllEqual(a.dense_shape, b.dense_shape)

  @parameterized.named_parameters(*_ONE_TENSOR_TEST_CASES)
  @test_util.run_in_graph_and_eager_modes
  def testOneTensorFromOneColumn(self, tensor_representation_textpb,
                                 arrow_array, expected_type_spec,
                                 expected_output):

    tensor_representation = text_format.Parse(tensor_representation_textpb,
                                              schema_pb2.TensorRepresentation())
    column_name = None
    if tensor_representation.HasField("dense_tensor"):
      column_name = tensor_representation.dense_tensor.column_name
    if tensor_representation.HasField("varlen_sparse_tensor"):
      column_name = tensor_representation.varlen_sparse_tensor.column_name

    record_batch = pa.RecordBatch.from_arrays([arrow_array], [column_name])
    adapter = tensor_adapter.TensorAdapter(
        tensor_adapter.TensorAdapterConfig(record_batch.schema,
                                           {"output": tensor_representation}))
    self.assertEqual(expected_type_spec, adapter.TypeSpecs()["output"])
    converted = adapter.ToBatchTensors(record_batch)
    self.assertLen(converted, 1)
    self.assertIn("output", converted)
    actual_output = converted["output"]
    if tf.executing_eagerly():
      self.assertTrue(
          expected_type_spec.is_compatible_with(actual_output),
          "{} is not compatible with spec {}".format(
              actual_output, expected_type_spec))
    if isinstance(expected_output, (tf.SparseTensor,
                                    tf.compat.v1.SparseTensorValue)):
      self.assertIsInstance(actual_output,
                            (tf.SparseTensor, tf.compat.v1.SparseTensorValue))
      self.assertSparseAllEqual(expected_output, actual_output)
    else:
      self.assertAllEqual(expected_output, actual_output)

  @test_util.run_in_graph_and_eager_modes
  def testMultipleColumns(self):
    record_batch = pa.RecordBatch.from_arrays([
        pa.array([[1], [], [2, 3], None], type=pa.list_(pa.int64())),
        pa.array([[1.0, 2.0], [2.0, 3.0], [3.0, 4.0], [4.0, 5.0]],
                 type=pa.list_(pa.float32())),
        pa.array([None, [b"a", b"b"], [b"c", b"d"], None],
                 type=pa.list_(pa.binary())),
        pa.array([[b"w"], [b"x"], [b"y"], [b"z"]], type=pa.list_(pa.binary())),
    ], [
        "int64_ragged",
        "float_dense",
        "bytes_ragged",
        "bytes_dense",
    ])

    tensor_representations = {
        "int64_varlen_sparse":
            text_format.Parse(
                """
        varlen_sparse_tensor {
          column_name: "int64_ragged"
        }
        """, schema_pb2.TensorRepresentation()),
        "float_dense":
            text_format.Parse(
                """
        dense_tensor {
          column_name: "float_dense"
          shape {
            dim {
              size: 2
            }
            dim {
              size: 1
            }
          }
        }""", schema_pb2.TensorRepresentation()),
        "bytes_varlen_sparse":
            text_format.Parse(
                """
        varlen_sparse_tensor {
          column_name: "bytes_ragged"
        }
        """, schema_pb2.TensorRepresentation()),
        "bytes_dense":
            text_format.Parse(
                """
        dense_tensor {
          column_name: "bytes_dense"
          shape {
          }
        }
        """, schema_pb2.TensorRepresentation()),
        "bytes_default_filled_dense":
            text_format.Parse(
                """
        dense_tensor {
          column_name: "bytes_ragged"
          shape {
            dim {
              size: 2
            }
          }
          default_value {
            bytes_value: "kk"
          }
        }
        """, schema_pb2.TensorRepresentation()),
    }

    adapter = tensor_adapter.TensorAdapter(
        tensor_adapter.TensorAdapterConfig(
            record_batch.schema, tensor_representations))
    type_specs = adapter.TypeSpecs()
    self.assertEqual(
        type_specs, {
            "int64_varlen_sparse":
                tf.SparseTensorSpec(shape=[None, None], dtype=tf.int64),
            "bytes_varlen_sparse":
                tf.SparseTensorSpec(shape=[None, None], dtype=tf.string),
            "float_dense":
                tf.TensorSpec(shape=[None, 2, 1], dtype=tf.float32),
            "bytes_dense":
                tf.TensorSpec(shape=[None], dtype=tf.string),
            "bytes_default_filled_dense":
                tf.TensorSpec(shape=[None, 2], dtype=tf.string),
        })

    tensors = adapter.ToBatchTensors(record_batch)
    self.assertLen(tensors, len(type_specs))
    self.assertSparseAllEqual(
        tf.SparseTensor(
            values=tf.constant([1, 2, 3], dtype=tf.int64),
            dense_shape=tf.constant([4, 2], dtype=tf.int64),
            indices=tf.constant([[0, 0], [2, 0], [2, 1]], dtype=tf.int64)),
        tensors["int64_varlen_sparse"])
    self.assertSparseAllEqual(
        tf.SparseTensor(
            values=tf.constant([b"a", b"b", b"c", b"d"]),
            dense_shape=tf.constant([4, 2], dtype=tf.int64),
            indices=tf.constant([[1, 0], [1, 1], [2, 0], [2, 1]],
                                dtype=tf.int64)),
        tensors["bytes_varlen_sparse"])
    self.assertAllEqual(
        tf.constant(
            [[[1.0], [2.0]], [[2.0], [3.0]], [[3.0], [4.0]], [[4.0], [5.0]]],
            dtype=tf.float32),
        tensors["float_dense"])
    self.assertAllEqual(
        tf.constant([b"w", b"x", b"y", b"z"]), tensors["bytes_dense"])
    self.assertAllEqual(
        tf.constant([[b"kk", b"kk"], [b"a", b"b"], [b"c", b"d"],
                     [b"kk", b"kk"]]), tensors["bytes_default_filled_dense"])

    if tf.executing_eagerly():
      for name, spec in six.iteritems(type_specs):
        self.assertTrue(
            spec.is_compatible_with(tensors[name]),
            "{} is not compatible with spec {}".format(tensors[name], spec))

  def testRaiseOnUnsupportedTensorRepresentation(self):
    with self.assertRaisesRegexp(ValueError, "Unable to handle tensor"):
      tensor_adapter.TensorAdapter(
          tensor_adapter.TensorAdapterConfig(
              pa.schema([pa.field("a", pa.list_(pa.int64()))]),
              {"tensor": schema_pb2.TensorRepresentation()}))

  def testRaiseOnNoMatchingHandler(self):
    with self.assertRaisesRegexp(ValueError, "Unable to handle tensor"):
      tensor_adapter.TensorAdapter(
          tensor_adapter.TensorAdapterConfig(
              # nested lists are not supported now.
              pa.schema([pa.field("unsupported_column",
                                  pa.list_(pa.list_(pa.int64())))]),
              {
                  "tensor":
                      text_format.Parse(
                          """
                  dense_tensor {
                    column_name: "unsupported_column"
                    shape: {}
                  }
                  """, schema_pb2.TensorRepresentation())
              }))

  @parameterized.named_parameters(*_INVALID_DEFAULT_VALUE_TEST_CASES)
  def testRaiseOnInvalidDefaultValue(self, value_type, default_value_pbtxt,
                                     exception_regexp):
    with self.assertRaisesRegexp(ValueError, exception_regexp):
      tensor_representation = text_format.Parse("""
                  dense_tensor {
                    column_name: "column"
                    shape {}
                  }""", schema_pb2.TensorRepresentation())
      tensor_representation.dense_tensor.default_value.CopyFrom(
          text_format.Parse(default_value_pbtxt,
                            schema_pb2.TensorRepresentation.DefaultValue()))
      tensor_adapter.TensorAdapter(
          tensor_adapter.TensorAdapterConfig(
              pa.schema([pa.field("column", pa.list_(value_type))]),
              {"tensor": tensor_representation}))


if __name__ == "__main__":
  absltest.main()
