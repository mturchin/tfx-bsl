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
"""TensorAdapter."""

from __future__ import absolute_import
from __future__ import division
# Standard __future__ imports
from __future__ import print_function

import abc
import collections

import numpy as np
import six
from tfx_bsl.arrow import array_util
from tfx_bsl.pyarrow_tf import pyarrow as pa
from tfx_bsl.pyarrow_tf import tensorflow as tf
from typing import Any, Dict, List, Text, Tuple, Union

from tensorflow_metadata.proto.v0 import schema_pb2

TensorRepresentations = Dict[Text, schema_pb2.TensorRepresentation]
# TODO(zhuo): Use typing.NamedCollections once python2 support is dropped.
TensorAdapterConfig = collections.namedtuple(
    "TensorAdapterConfig",
    [
        "arrow_schema",  # type is pa.Schema
        "tensor_representations",  # type is TensorRepresentations
    ])


class TensorAdapter(object):
  """A TensorAdapter converts a RecordBatch to a collection of TF Tensors.

  The conversion is determined by both the Arrow schema and the
  TensorRepresentations, which must be provided at the initialization time.
  Each TensorRepresentation contains the information needed to translates one
  or more columns in a RecordBatch of the given Arrow schema into a TF Tensor
  or CompositeTensor. They are contained in a Dict whose keys are
  the names of the tensors, which will be the keys of the Dict produced by
  ToBatchTensors().

  TypeSpecs() returns static TypeSpecs of those tensors by their names, i.e.
  if they have a shape, then the size of the first (batch) dimension is always
  unknown (None) because it depends on the size of the RecordBatch passed to
  ToBatchTensors().

  It is guaranteed that for any tensor_name in the given TensorRepresentations
  self.TypeSpecs()[tensor_name].is_compatible_with(
      self.ToBatchedTensors(...)[tensor_name])
  """

  __slots__ = ["_arrow_schema", "_type_handlers", "_type_specs"]

  def __init__(self, config: TensorAdapterConfig):
    self._arrow_schema = config.arrow_schema
    self._type_handlers = _BuildTypeHandlers(
        config.tensor_representations, config.arrow_schema)
    self._type_specs = {
        tensor_name: handler.type_spec
        for tensor_name, handler in self._type_handlers
    }

  def TypeSpecs(self) -> Dict[Text, tf.TypeSpec]:
    """Returns the TypeSpec for each tensor."""
    return self._type_specs

  def ToBatchTensors(self, record_batch: pa.RecordBatch) -> Dict[Text, Any]:
    """Returns a batch of tensors translated from record_batch."""
    if not record_batch.schema.equals(self._arrow_schema):
      raise ValueError("Expected same schema.")
    result = {}
    for tensor_name, handler in self._type_handlers:
      try:
        result[tensor_name] = handler.GetTensor(record_batch)
      except Exception as e:
        raise ValueError("Error raised when handling tensor {}: {}"
                         .format(tensor_name, e))

    return result


@six.add_metaclass(abc.ABCMeta)
class _TypeHandler(object):
  """Base class of all type handlers.

  A TypeHandler converts one or more columns in a RecordBatch to a TF Tensor
  or CompositeTensor according to a TensorRepresentation.

  All TypeHandlers are registered by TensorRepresentation types in
  _TYPE_HANDLER_MAP.
  """

  __slots__ = []

  @abc.abstractmethod
  def __init__(self, arrow_schema: pa.Schema,
               tensor_representation: schema_pb2.TensorRepresentation):
    """Initializer.

    It can be assumed that CanHandle(arrow_schema, tensor_representation) would
    return true.

    Args:
      arrow_schema: the Arrow Schema that all the RecordBatches that
        self.GetTensor() will take conform to.
      tensor_representation: the TensorRepresentation that determins the
        conversion.
    """

  @abc.abstractproperty
  def type_spec(self) -> tf.TypeSpec:
    """Returns the TypeSpec of the converted Tensor or CompositeTensor."""

  @abc.abstractmethod
  def GetTensor(self, record_batch: pa.RecordBatch) -> Any:
    """Converts the RecordBatch to Tensor or CompositeTensor.

    The result must be of the same (not only compatible) TypeSpec as
    self.type_spec.

    Args:
      record_batch: a RecordBatch that is of the same Schema as what was
        passed at initialization time.

    Returns:
      A Tensor or a CompositeTensor. Note that their types may vary depending
      on whether the TF eager mode is on.
    """

  @staticmethod
  @abc.abstractmethod
  def CanHandle(
      arrow_schema: pa.Schema,
      tensor_representation: schema_pb2.TensorRepresentation) -> bool:
    """Returns true if an instance of the handler can handle the combination."""


class _BaseDenseTensorHandler(_TypeHandler):
  """Base class of DenseTensorHandlers."""

  __slots__ = ["_column_index", "_dtype", "_shape", "_unbatched_flat_len"]

  def __init__(self, arrow_schema: pa.Schema,
               tensor_representation: schema_pb2.TensorRepresentation):
    super(_BaseDenseTensorHandler, self).__init__(arrow_schema,
                                                  tensor_representation)
    dense_rep = tensor_representation.dense_tensor
    column_name = dense_rep.column_name
    self._column_index = arrow_schema.get_field_index(column_name)
    _, value_type = _GetNestDepthAndValueType(arrow_schema[self._column_index])
    self._dtype = _ArrowTypeToTfDtype(value_type)
    unbatched_shape = [
        d.size for d in tensor_representation.dense_tensor.shape.dim
    ]
    self._shape = [None] + unbatched_shape
    self._unbatched_flat_len = int(np.prod(unbatched_shape, initial=1))

  @property
  def type_spec(self) -> tf.TypeSpec:
    return tf.TensorSpec(self._shape, self._dtype)

  def _ListArrayToTensor(
      self, list_array: pa.Array) -> Union[np.ndarray, tf.Tensor]:
    """Converts a ListArray to a dense tensor."""
    values = list_array.flatten()
    batch_size = len(list_array)
    expected_num_elements = batch_size * self._unbatched_flat_len
    if len(values) != expected_num_elements:
      raise ValueError(
          "Unable to convert ListArray {} to {}: size mismatch. expected {} "
          "elements but got {}".format(
              list_array, self.type_spec, expected_num_elements, len(values)))
    # TODO(zhuo): Cast StringArrays to BinaryArrays before calling np.asarray()
    # to avoid generating unicode objects which are wasteful to feed to
    # TensorFlow, once pyarrow requirement is bumped to >=0.15.
    actual_shape = list(self._shape)
    actual_shape[0] = batch_size
    values_np = np.asarray(values).reshape(actual_shape)
    if tf.executing_eagerly():
      return tf.convert_to_tensor(values_np)

    return values_np

  @staticmethod
  def BaseCanHandle(
      arrow_schema: pa.Schema,
      tensor_representation: schema_pb2.TensorRepresentation) -> bool:
    depth, value_type = _GetNestDepthAndValueType(
        arrow_schema.field_by_name(
            tensor_representation.dense_tensor.column_name))
    # Can only handle 1-nested lists.
    return depth == 1 and _IsSupportedArrowValueType(value_type)


class _DenseTensorHandler(_BaseDenseTensorHandler):
  """Handles conversion to dense."""

  __slots__ = []

  def GetTensor(
      self, record_batch: pa.RecordBatch) -> Union[np.ndarray, tf.Tensor]:
    column = record_batch.column(self._column_index)
    return self._ListArrayToTensor(column)

  @staticmethod
  def CanHandle(arrow_schema: pa.Schema,
                tensor_representation: schema_pb2.TensorRepresentation) -> bool:
    return (_BaseDenseTensorHandler.BaseCanHandle(arrow_schema,
                                                  tensor_representation) and
            not tensor_representation.dense_tensor.HasField("default_value"))


class _DefaultFillingDenseTensorHandler(_BaseDenseTensorHandler):
  """Handles conversion to dense with default filling."""

  __slots__ = ["_default_fill"]

  def __init__(self, arrow_schema: pa.Schema,
               tensor_representation: schema_pb2.TensorRepresentation):
    super(_DefaultFillingDenseTensorHandler, self).__init__(
        arrow_schema, tensor_representation)
    _, value_type = _GetNestDepthAndValueType(arrow_schema[self._column_index])
    self._default_fill = _GetDefaultFill(
        self._shape[1:], value_type,
        tensor_representation.dense_tensor.default_value)

  def GetTensor(
      self, record_batch: pa.RecordBatch) -> Union[np.ndarray, tf.Tensor]:
    column = record_batch.column(self._column_index)
    column = array_util.FillNullLists(column, self._default_fill)
    return self._ListArrayToTensor(column)

  @staticmethod
  def CanHandle(arrow_schema: pa.Schema,
                tensor_representation: schema_pb2.TensorRepresentation) -> bool:
    return (
        _BaseDenseTensorHandler.BaseCanHandle(
            arrow_schema, tensor_representation)
        and tensor_representation.dense_tensor.HasField("default_value"))


class _VarLenSparseTensorHandler(_TypeHandler):
  """Handles conversion to varlen sparse."""

  __slots__ = ["_column_index", "_dtype"]

  def __init__(self, arrow_schema: pa.Schema,
               tensor_representation: schema_pb2.TensorRepresentation):
    super(_VarLenSparseTensorHandler, self).__init__(
        arrow_schema, tensor_representation)
    column_name = tensor_representation.varlen_sparse_tensor.column_name
    self._column_index = arrow_schema.get_field_index(column_name)
    _, value_type = _GetNestDepthAndValueType(arrow_schema[self._column_index])
    self._dtype = _ArrowTypeToTfDtype(value_type)

  @property
  def type_spec(self) -> tf.TypeSpec:
    return tf.SparseTensorSpec(
        tf.TensorShape([None, None]), self._dtype)

  def GetTensor(self, record_batch: pa.RecordBatch) -> Any:
    array = record_batch.column(self._column_index)
    coo_array, dense_shape_array = array_util.CooFromListArray(array)
    dense_shape_np = dense_shape_array.to_numpy()
    values_np = np.asarray(array.flatten())
    coo_np = coo_array.to_numpy().reshape(values_np.size, 2)

    if tf.executing_eagerly():
      return tf.sparse.SparseTensor(
          indices=tf.convert_to_tensor(coo_np),
          dense_shape=tf.convert_to_tensor(dense_shape_np),
          values=tf.convert_to_tensor(values_np))
    return tf.compat.v1.SparseTensorValue(
        indices=coo_np, dense_shape=dense_shape_np, values=values_np)

  @staticmethod
  def CanHandle(arrow_schema: pa.Schema,
                tensor_representation: schema_pb2.TensorRepresentation) -> bool:
    depth, value_type = _GetNestDepthAndValueType(
        arrow_schema.field_by_name(
            tensor_representation.varlen_sparse_tensor.column_name))
    # Currently can only handle 1-nested lists, but can easily support
    # arbitrarily nested ListArrays.
    return depth == 1 and _IsSupportedArrowValueType(value_type)


# Mapping from TensorRepresentation's "kind" oneof field name to TypeHandler
# classes. Note that one kind may have multiple handlers and the first one
# whose CanHandle() returns true will be used.
_TYPE_HANDLER_MAP = {
    "dense_tensor": [_DenseTensorHandler, _DefaultFillingDenseTensorHandler],
    "varlen_sparse_tensor": [_VarLenSparseTensorHandler],
}


def _BuildTypeHandlers(
    tensor_representations: Dict[Text, schema_pb2.TensorRepresentation],
    arrow_schema: pa.Schema) -> List[Tuple[Text, _TypeHandler]]:
  """Builds type handlers according to TensorRepresentations."""
  result = []
  for tensor_name, rep in six.iteritems(tensor_representations):
    potential_handlers = _TYPE_HANDLER_MAP.get(rep.WhichOneof("kind"))
    if not potential_handlers:
      raise ValueError("Unable to handle tensor {} with rep {}".format(
          tensor_name, rep))
    found_handler = False
    for h in potential_handlers:
      if h.CanHandle(arrow_schema, rep):
        found_handler = True
        result.append((tensor_name, h(arrow_schema, rep)))
        break
    if not found_handler:
      raise ValueError("Unable to handle tensor {} with rep {} "
                       "against schema: {}".format(tensor_name, rep,
                                                   arrow_schema))

  return result


def _GetNestDepthAndValueType(
    arrow_field: pa.Field) -> Tuple[int, pa.DataType]:
  """Returns the depth of a nest list and its innermost value type."""
  arrow_type = arrow_field.type
  depth = 0
  while pa.types.is_list(arrow_type):
    depth += 1
    arrow_type = arrow_type.value_type

  return depth, arrow_type


def _IsSupportedArrowValueType(arrow_type: pa.DataType) -> bool:
  # TODO(zhuo): Also support StringArrays, once pyarrow requirements
  # is >=0.15 which allows to cast a StringArray to BinaryArray copy-free.
  # TODO(zhuo): Support LargeListArray, LargeBinaryArray, LargeStringArray
  # once pyarrow requirements is >=0.15.
  return (pa.types.is_integer(arrow_type) or
          pa.types.is_floating(arrow_type) or
          pa.types.is_binary(arrow_type))


def _ArrowTypeToTfDtype(arrow_type: pa.DataType) -> tf.DType:
  return tf.dtypes.as_dtype(arrow_type.to_pandas_dtype())


def _GetAllowedDefaultValue(
    value_type: pa.DataType,
    default_value_proto: schema_pb2.TensorRepresentation.DefaultValue
) -> Union[int, float, bytes]:
  """Returns the default value set in DefaultValue proto or raises."""
  kind = default_value_proto.WhichOneof("kind")
  if kind in ("int_value", "uint_value") and pa.types.is_integer(value_type):
    value = getattr(default_value_proto, kind)
    iinfo = np.iinfo(value_type.to_pandas_dtype())
    if value <= iinfo.max and value >= iinfo.min:
      return value
    else:
      raise ValueError("Integer default value out of range: {} is set for a "
                       "{} column".format(value, value_type))
  elif kind == "float_value" and pa.types.is_floating(value_type):
    return default_value_proto.float_value
  elif kind == "bytes_value" and pa.types.is_binary(value_type):
    return default_value_proto.bytes_value

  raise ValueError(
      "Incompatible default value: {} is set for a {} column".format(
          kind, value_type))


def _GetDefaultFill(
    unbatched_shape: List[int], value_type: pa.DataType,
    default_value_proto: schema_pb2.TensorRepresentation.DefaultValue
) -> pa.Array:
  """Returns an Array full of the default value given in the proto."""

  size = int(np.prod(unbatched_shape, initial=1))
  return pa.array([
      _GetAllowedDefaultValue(value_type, default_value_proto)] * size,
                  type=value_type)
