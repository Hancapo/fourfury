from __future__ import annotations

import struct
from collections.abc import Callable

from ..rsc import RSC5_PHYSICAL_BASE, RSC5_VIRTUAL_BASE, Rsc5Resource
from ..wtd import read_rsc5_texture_dictionary
from .constants import (
    WDR_DRAWABLE_SIZE,
    WDR_GEOMETRY_SIZE,
    WDR_INDEX_BUFFER_SIZE,
    WDR_LIGHT_SIZE,
    WDR_LOD_SIZE,
    WDR_MODEL_SIZE,
    WDR_SHADER_SIZE,
    WDR_VERTEX_BUFFER_SIZE,
)
from .geometry import (
    VertexValue,
    WdrDrawableLod,
    WdrDrawableModel,
    WdrGeometry,
    WdrIndexBuffer,
    WdrLodLevel,
    WdrVertex,
    WdrVertexBuffer,
    WdrVertexElement,
    WdrVertexElementType,
    WdrVertexLayout,
    WdrVertexSemantic,
    _ELEMENT_SIZES,
)
from .material import (
    WdrShader,
    WdrShaderGroup,
    WdrShaderParameter,
    WdrTextureReference,
)
from .math import WdrMatrix4, WdrVector3, WdrVector4
from .scene import (
    WdrBone,
    WdrBoneFlags,
    WdrBoneId,
    WdrDrawable,
    WdrLight,
    WdrLightFlags,
    WdrLightType,
    WdrLightTypeFlags,
    WdrSkeleton,
)

try:
    from .._native import decode_wdr_vertices as _native_decode_wdr_vertices
except ImportError:
    _native_decode_wdr_vertices = None


class _WdrReader:
    def __init__(
        self,
        resource: Rsc5Resource,
        native_decoder_provider: Callable[[], object | None] | None = None,
    ) -> None:
        self.resource = resource
        self._native_decoder_provider = (
            native_decoder_provider
            if native_decoder_provider is not None
            else lambda: _native_decode_wdr_vertices
        )
        self.layouts: dict[int, WdrVertexLayout] = {}
        self.vertex_buffers: dict[int, WdrVertexBuffer] = {}
        self.index_buffers: dict[int, WdrIndexBuffer] = {}
        self.geometries: dict[int, WdrGeometry] = {}
        self.models: dict[int, WdrDrawableModel] = {}
        self.lods: dict[int, WdrDrawableLod] = {}
        self.shaders: dict[int, WdrShader] = {}
        self.textures: dict[int, WdrTextureReference] = {}

    def _allocation(self, pointer: int) -> tuple[bytes, int, str]:
        base = pointer & 0xF0000000
        offset = pointer & 0x0FFFFFFF
        if base == RSC5_VIRTUAL_BASE:
            return self.resource.virtual_data, offset, "virtual"
        if base == RSC5_PHYSICAL_BASE:
            return self.resource.physical_data, offset, "physical"
        raise ValueError(f"invalid RSC5 pointer: {pointer:#x}")

    def read(self, pointer: int, size: int, label: str) -> bytes:
        if pointer == 0:
            raise ValueError(f"null pointer for {label}")
        data, offset, allocation = self._allocation(pointer)
        if size < 0 or offset + size > len(data):
            raise ValueError(f"{label} exceeds the RSC5 {allocation} allocation")
        return data[offset : offset + size]

    def unpack(self, pointer: int, format_string: str, label: str) -> tuple[object, ...]:
        size = struct.calcsize(format_string)
        return struct.unpack(format_string, self.read(pointer, size, label))

    def string(self, pointer: int) -> str:
        if pointer == 0:
            return ""
        data, offset, allocation = self._allocation(pointer)
        end = data.find(b"\0", offset)
        if end < 0:
            raise ValueError(f"unterminated WDR string in the {allocation} allocation")
        return data[offset:end].decode("utf-8", errors="replace")

    def vector3(self, pointer: int, label: str) -> WdrVector3:
        return WdrVector3(*self.unpack(pointer, "<3f", label))  # type: ignore[arg-type]

    def vector4(self, pointer: int, label: str) -> WdrVector4:
        return WdrVector4(*self.unpack(pointer, "<4f", label))  # type: ignore[arg-type]

    def matrix4(self, pointer: int, label: str) -> WdrMatrix4:
        return WdrMatrix4(self.unpack(pointer, "<16f", label))  # type: ignore[arg-type]

    def pointer_array(self, header_pointer: int, label: str) -> tuple[int, ...]:
        array_pointer, count, capacity = self.unpack(header_pointer, "<IHH", f"{label} header")
        if capacity < count:
            raise ValueError(f"{label} count exceeds its capacity")
        if count == 0:
            return ()
        return self.unpack(array_pointer, f"<{count}I", label)  # type: ignore[arg-type]

    def plain_array(
        self,
        header_pointer: int,
        format_code: str,
        item_size: int,
        label: str,
    ) -> tuple[object, ...]:
        array_pointer, count, capacity = self.unpack(header_pointer, "<IHH", f"{label} header")
        if capacity < count:
            raise ValueError(f"{label} count exceeds its capacity")
        if count == 0:
            return ()
        if struct.calcsize(f"<{format_code}") != item_size:
            raise ValueError(f"invalid item size for {label}")
        return self.unpack(array_pointer, f"<{count}{format_code}", label)

    def parse_layout(self, pointer: int) -> WdrVertexLayout:
        if pointer in self.layouts:
            return self.layouts[pointer]
        fvf, fvf_size, flags, dynamic_order, channel_count, declaration_types = self.unpack(
            pointer, "<IBBBBQ", "WDR vertex layout"
        )
        elements: list[WdrVertexElement] = []
        offset = 0
        for semantic_value in range(16):
            if not fvf & (1 << semantic_value):
                continue
            type_value = (declaration_types >> (semantic_value * 4)) & 0xF
            try:
                element_type = WdrVertexElementType(type_value)
                size = _ELEMENT_SIZES[element_type]
            except (ValueError, KeyError) as exc:
                raise ValueError(
                    f"unsupported WDR vertex element type {type_value} for semantic {semantic_value}"
                ) from exc
            elements.append(
                WdrVertexElement(WdrVertexSemantic(semantic_value), element_type, offset)
            )
            offset += size
        if len(elements) != channel_count:
            raise ValueError(
                f"WDR vertex layout declares {channel_count} channels but its FVF describes {len(elements)}"
            )
        if offset > fvf_size:
            raise ValueError(f"WDR vertex elements exceed their {fvf_size}-byte FVF size")
        layout = WdrVertexLayout(
            int(fvf),
            int(fvf_size),
            int(flags),
            int(dynamic_order),
            int(channel_count),
            int(declaration_types),
            tuple(elements),
            pointer,
        )
        self.layouts[pointer] = layout
        return layout

    @staticmethod
    def _decode_dec3n(value: int) -> tuple[float, float, float, float]:
        result: list[float] = []
        for shift in (0, 10, 20):
            component = (value >> shift) & 0x3FF
            signed = component if component < 0x200 else component - 0x400
            result.append(max(-1.0, signed / 511.0))
        w_bits = (value >> 30) & 0x3
        result.append(-1.0 if w_bits == 3 else float(w_bits))
        return tuple(result)  # type: ignore[return-value]

    def decode_vertex_attributes(
        self,
        data: bytes,
        base: int,
        layout: WdrVertexLayout,
    ) -> dict[WdrVertexSemantic, VertexValue]:
        attributes: dict[WdrVertexSemantic, VertexValue] = {}
        for element in layout.elements:
            offset = base + element.offset
            element_type = element.element_type
            if element_type == WdrVertexElementType.HALF2:
                value: VertexValue = struct.unpack_from("<2e", data, offset)
            elif element_type == WdrVertexElementType.HALF4:
                value = struct.unpack_from("<4e", data, offset)
            elif element_type in (WdrVertexElementType.FLOAT, WdrVertexElementType.FLOAT_SINGLE):
                value = struct.unpack_from("<f", data, offset)[0]
            elif element_type == WdrVertexElementType.FLOAT2:
                value = struct.unpack_from("<2f", data, offset)
            elif element_type == WdrVertexElementType.FLOAT3:
                value = struct.unpack_from("<3f", data, offset)
            elif element_type == WdrVertexElementType.FLOAT4:
                value = struct.unpack_from("<4f", data, offset)
            elif element_type in (WdrVertexElementType.UBYTE4, WdrVertexElementType.COLOR):
                value = struct.unpack_from("<4B", data, offset)
            elif element_type == WdrVertexElementType.DEC3N:
                value = self._decode_dec3n(struct.unpack_from("<I", data, offset)[0])
            else:  # pragma: no cover - parse_layout rejects these first
                raise ValueError(f"unsupported WDR vertex element type: {element_type}")
            attributes[element.semantic] = value
        return attributes

    def decode_vertex(self, data: bytes, base: int, layout: WdrVertexLayout) -> WdrVertex:
        attributes = self.decode_vertex_attributes(data, base, layout)
        return WdrVertex(attributes)

    def decode_vertex_channels(
        self,
        data: bytes,
        vertex_count: int,
        stride: int,
        layout: WdrVertexLayout,
    ) -> dict[WdrVertexSemantic, tuple[VertexValue, ...]]:
        native_decoder = self._native_decoder_provider()
        if native_decoder is not None:
            decoded = native_decoder(
                data,
                vertex_count,
                stride,
                tuple(
                    (int(element.semantic), int(element.element_type), element.offset)
                    for element in layout.elements
                ),
            )
            return {
                WdrVertexSemantic(int(semantic)): tuple(values)
                for semantic, values in decoded.items()
            }

        channels: dict[WdrVertexSemantic, list[VertexValue]] = {
            element.semantic: [] for element in layout.elements
        }
        for index in range(vertex_count):
            attributes = self.decode_vertex_attributes(data, index * stride, layout)
            for semantic, value in attributes.items():
                channels[semantic].append(value)
        return {semantic: tuple(values) for semantic, values in channels.items()}

    def parse_vertex_buffer(self, pointer: int) -> WdrVertexBuffer:
        if pointer in self.vertex_buffers:
            return self.vertex_buffers[pointer]
        raw = self.read(pointer, WDR_VERTEX_BUFFER_SIZE, "WDR vertex buffer")
        vertex_count = struct.unpack_from("<H", raw, 4)[0]
        locked, flags = struct.unpack_from("<2B", raw, 6)
        locked_data_pointer = struct.unpack_from("<I", raw, 8)[0]
        stride = struct.unpack_from("<I", raw, 12)[0]
        layout_pointer = struct.unpack_from("<I", raw, 16)[0]
        lock_thread_id = struct.unpack_from("<I", raw, 20)[0]
        vertex_data_pointer = struct.unpack_from("<I", raw, 24)[0]
        d3d_vertex_buffer = struct.unpack_from("<I", raw, 28)[0]
        layout = self.parse_layout(layout_pointer)
        if layout.stride != stride:
            raise ValueError(
                f"WDR vertex buffer stride {stride} does not match layout stride {layout.stride}"
            )
        data_size = vertex_count * stride
        locked_data = (
            b"" if locked_data_pointer == 0
            else self.read(locked_data_pointer, data_size, "WDR locked vertex data")
        )
        if vertex_data_pointer == locked_data_pointer:
            vertex_data = locked_data
        else:
            vertex_data = (
                b"" if vertex_data_pointer == 0
                else self.read(vertex_data_pointer, data_size, "WDR vertex data")
            )
        primary = locked_data or vertex_data
        attribute_channels = (
            self.decode_vertex_channels(primary, vertex_count, stride, layout)
            if primary
            else {}
        )
        buffer = WdrVertexBuffer(
            vertex_count=vertex_count,
            locked=locked,
            flags=flags,
            stride=stride,
            layout=layout,
            locked_data=locked_data,
            lock_thread_id=lock_thread_id,
            vertex_data=vertex_data,
            d3d_vertex_buffer=d3d_vertex_buffer,
            attribute_channels=attribute_channels,
            _pointer=pointer,
        )
        self.vertex_buffers[pointer] = buffer
        return buffer

    def parse_index_buffer(self, pointer: int) -> WdrIndexBuffer:
        if pointer in self.index_buffers:
            return self.index_buffers[pointer]
        raw = self.read(pointer, WDR_INDEX_BUFFER_SIZE, "WDR index buffer")
        count, data_pointer = struct.unpack_from("<II", raw, 4)
        indices = () if count == 0 else self.unpack(
            data_pointer, f"<{count}H", "WDR index data"
        )
        reserved = struct.unpack_from("<9I", raw, 12)
        buffer = WdrIndexBuffer(indices, reserved, pointer)  # type: ignore[arg-type]
        self.index_buffers[pointer] = buffer
        return buffer

    def parse_geometry(self, pointer: int) -> WdrGeometry:
        if pointer in self.geometries:
            return self.geometries[pointer]
        raw = self.read(pointer, WDR_GEOMETRY_SIZE, "WDR geometry")
        reserved_header = struct.unpack_from("<2I", raw, 4)
        vertex_buffer_pointers = struct.unpack_from("<4I", raw, 12)
        index_buffer_pointers = struct.unpack_from("<4I", raw, 28)
        index_count, face_count = struct.unpack_from("<II", raw, 44)
        vertex_count, primitive_type = struct.unpack_from("<HH", raw, 52)
        bone_ids_pointer, vertex_stride, bone_ids_count = struct.unpack_from("<IHH", raw, 56)
        reserved_tail = struct.unpack_from("<4I", raw, 64)
        vertex_buffers = tuple(
            None if item == 0 else self.parse_vertex_buffer(item)
            for item in vertex_buffer_pointers
        )
        index_buffers = tuple(
            None if item == 0 else self.parse_index_buffer(item)
            for item in index_buffer_pointers
        )
        vertex_buffer = vertex_buffers[0]
        index_buffer = index_buffers[0]
        if vertex_count == 0 and vertex_buffer is not None:
            vertex_count = vertex_buffer.vertex_count
        if vertex_buffer is not None and vertex_buffer.vertex_count != vertex_count:
            raise ValueError("WDR geometry vertex count does not match its vertex buffer")
        if vertex_buffer is not None and vertex_buffer.stride != vertex_stride:
            raise ValueError("WDR geometry vertex stride does not match its vertex buffer")
        if index_buffer is not None and len(index_buffer.indices) < index_count:
            raise ValueError("WDR geometry index count exceeds its index buffer")
        bone_ids = () if bone_ids_count == 0 else self.unpack(
            bone_ids_pointer, f"<{bone_ids_count}H", "WDR geometry bone palette"
        )
        geometry = WdrGeometry(
            vertex_buffers,  # type: ignore[arg-type]
            index_buffers,  # type: ignore[arg-type]
            index_count,
            face_count,
            vertex_count,
            primitive_type,
            tuple(int(value) for value in bone_ids),
            vertex_stride,
            reserved_header,
            reserved_tail,
            _pointer=pointer,
        )
        self.geometries[pointer] = geometry
        return geometry

    def parse_model(self, pointer: int) -> WdrDrawableModel:
        if pointer in self.models:
            return self.models[pointer]
        raw = self.read(pointer, WDR_MODEL_SIZE, "WDR drawable model")
        geometry_pointers = self.pointer_array(pointer + 4, "WDR model geometry pointers")
        bounds_pointer, shader_mapping_pointer = struct.unpack_from("<2I", raw, 12)
        matrix_count, flags, model_type, matrix_index, stride, skin_flag = struct.unpack_from(
            "<6B", raw, 20
        )
        geometry_count = struct.unpack_from("<H", raw, 26)[0]
        reserved = struct.unpack_from("<I", raw, 28)[0]
        if len(geometry_pointers) != geometry_count:
            raise ValueError("WDR model geometry count does not match its pointer array")
        geometries = tuple(self.parse_geometry(item) for item in geometry_pointers)
        raw_bound_count = geometry_count + 1 if geometry_count > 1 else geometry_count
        raw_bounds = () if raw_bound_count == 0 or bounds_pointer == 0 else tuple(
            self.vector4(bounds_pointer + index * 16, "WDR model geometry bound")
            for index in range(raw_bound_count)
        )
        if not raw_bounds:
            bounding_sphere = None
            bounds = tuple(None for _ in range(geometry_count))
        elif geometry_count > 1:
            bounding_sphere = raw_bounds[0]
            bounds = raw_bounds[1:]
        else:
            bounding_sphere = raw_bounds[0]
            bounds = raw_bounds
        shader_mappings = () if geometry_count == 0 else (
            tuple(0 for _ in range(geometry_count)) if shader_mapping_pointer == 0 else self.unpack(
                shader_mapping_pointer, f"<{geometry_count}H", "WDR shader mappings"
            )
        )
        for index, geometry in enumerate(geometries):
            geometry.shader_index = int(shader_mappings[index])
            geometry.bounding_sphere = bounds[index]
        model = WdrDrawableModel(
            geometries,
            bounding_sphere,
            bounds,
            tuple(int(value) for value in shader_mappings),
            matrix_count,
            flags,
            model_type,
            matrix_index,
            stride,
            skin_flag,
            reserved,
            pointer,
        )
        self.models[pointer] = model
        return model

    def parse_lod(self, pointer: int, level: WdrLodLevel, distance: float) -> WdrDrawableLod:
        if pointer in self.lods:
            lod = self.lods[pointer]
            lod.level = level
            lod.distance = distance
            return lod
        raw = self.read(pointer, WDR_LOD_SIZE, "WDR drawable LOD")
        model_pointers = self.pointer_array(pointer, "WDR LOD model pointers")
        reserved = struct.unpack_from("<2I", raw, 8)
        lod = WdrDrawableLod(
            level,
            distance,
            tuple(self.parse_model(item) for item in model_pointers),
            reserved,
            pointer,
        )
        self.lods[pointer] = lod
        return lod

    def parse_texture_reference(self, pointer: int) -> WdrTextureReference:
        if pointer in self.textures:
            return self.textures[pointer]
        raw = self.read(pointer, 28, "WDR texture reference")
        file_name_pointer = struct.unpack_from("<I", raw, 20)[0]
        file_name = self.string(file_name_pointer)
        name = file_name.removeprefix("pack:/").removesuffix(".dds")
        texture = WdrTextureReference(file_name, name, pointer)
        self.textures[pointer] = texture
        return texture

    def parse_shader(self, pointer: int) -> WdrShader:
        if pointer in self.shaders:
            return self.shaders[pointer]
        raw = self.read(pointer, WDR_SHADER_SIZE, "WDR shader")
        block_map_address = struct.unpack_from("<I", raw, 4)[0]
        version, draw_bucket, usage_count = struct.unpack_from("<3B", raw, 8)
        shader_index = struct.unpack_from("<H", raw, 14)[0]
        parameter_data_pointer = struct.unpack_from("<I", raw, 20)[0]
        parameter_count = struct.unpack_from("<I", raw, 28)[0]
        parameter_types_pointer = struct.unpack_from("<I", raw, 36)[0]
        name_hash = struct.unpack_from("<I", raw, 40)[0]
        parameter_names_pointer = struct.unpack_from("<I", raw, 52)[0]
        name_pointer, file_name_pointer = struct.unpack_from("<2I", raw, 68)
        reserved = (
            raw[11],
            struct.unpack_from("<H", raw, 12)[0],
            struct.unpack_from("<I", raw, 16)[0],
            struct.unpack_from("<I", raw, 24)[0],
            struct.unpack_from("<I", raw, 32)[0],
            struct.unpack_from("<I", raw, 44)[0],
            struct.unpack_from("<I", raw, 48)[0],
            struct.unpack_from("<I", raw, 56)[0],
            struct.unpack_from("<I", raw, 60)[0],
            struct.unpack_from("<I", raw, 64)[0],
            *struct.unpack_from("<5I", raw, 76),
        )
        parameter_pointers = () if parameter_count == 0 else self.unpack(
            parameter_data_pointer, f"<{parameter_count}I", "WDR shader parameter pointers"
        )
        parameter_types = () if parameter_count == 0 else self.unpack(
            parameter_types_pointer, f"<{parameter_count}B", "WDR shader parameter types"
        )
        parameter_hashes = () if parameter_count == 0 else self.unpack(
            parameter_names_pointer, f"<{parameter_count}I", "WDR shader parameter hashes"
        )
        parameters: list[WdrShaderParameter] = []
        for index in range(parameter_count):
            parameter_pointer = int(parameter_pointers[index])
            parameter_type = int(parameter_types[index])
            parameter_hash = int(parameter_hashes[index])
            if parameter_type == 0:
                texture = (
                    None if parameter_pointer == 0
                    else self.parse_texture_reference(parameter_pointer)
                )
                parameters.append(WdrShaderParameter(parameter_hash, parameter_type, texture=texture))
            elif parameter_type == 1:
                value = self.vector4(parameter_pointer, "WDR shader vector parameter")
                parameters.append(WdrShaderParameter(parameter_hash, parameter_type, value=value))
            else:
                values = tuple(
                    self.vector4(
                        parameter_pointer + item * 16,
                        "WDR shader vector array parameter",
                    )
                    for item in range(parameter_type)
                )
                parameters.append(WdrShaderParameter(parameter_hash, parameter_type, value=values))
        shader = WdrShader(
            self.string(name_pointer),
            self.string(file_name_pointer),
            name_hash,
            block_map_address,
            version,
            draw_bucket,
            usage_count,
            shader_index,
            tuple(parameters),
            reserved,
            pointer,
        )
        self.shaders[pointer] = shader
        return shader

    def parse_shader_group(self, pointer: int) -> WdrShaderGroup:
        raw = self.read(pointer, 80, "WDR shader group")
        texture_dictionary_pointer = struct.unpack_from("<I", raw, 4)[0]
        shader_pointers = self.pointer_array(pointer + 8, "WDR shader pointers")
        usage_values = self.plain_array(
            pointer + 64, "I", 4, "WDR vertex declaration usage flags"
        )
        reserved = struct.unpack_from("<12I", raw, 16)
        reserved_data = self.plain_array(pointer + 72, "I", 4, "WDR shader group reserved data")
        return WdrShaderGroup(
            tuple(self.parse_shader(item) for item in shader_pointers),
            texture_dictionary_pointer,
            tuple(int(value) for value in usage_values),
            reserved,
            tuple(int(value) for value in reserved_data),
            (
                read_rsc5_texture_dictionary(self.resource, texture_dictionary_pointer)
                if texture_dictionary_pointer else None
            ),
            pointer,
        )

    def parse_skeleton(self, pointer: int) -> WdrSkeleton:
        raw = self.read(pointer, 64, "WDR skeleton")
        (
            bones_pointer,
            parent_indices_pointer,
            cumulative_inverse_pointer,
            cumulative_pointer,
            default_transforms_pointer,
        ) = struct.unpack_from("<5I", raw, 0)
        (
            bone_count,
            translation_dof_count,
            rotation_dof_count,
            scale_dof_count,
        ) = struct.unpack_from("<4H", raw, 20)
        flags = struct.unpack_from("<I", raw, 28)[0]
        bone_ids_pointer, bone_id_count, bone_id_capacity = self.unpack(
            pointer + 32, "<IHH", "WDR bone ID map header"
        )
        if bone_id_capacity < bone_id_count:
            raise ValueError("WDR bone ID map count exceeds its capacity")
        bone_ids = tuple(
            WdrBoneId(*self.unpack(
                bone_ids_pointer + index * 4, "<HH", "WDR bone ID map entry"
            ))
            for index in range(bone_id_count)
        ) if bone_id_count else ()
        reference_count, signature, *reserved = struct.unpack_from("<6I", raw, 40)
        parent_indices = (
            tuple(-1 for _ in range(bone_count))
            if parent_indices_pointer == 0 else tuple(int(value) for value in self.unpack(
                parent_indices_pointer, f"<{bone_count}i", "WDR skeleton parent indices"
            ))
        )

        def read_matrices(array_pointer: int, label: str) -> tuple[WdrMatrix4, ...]:
            if array_pointer == 0:
                return tuple(WdrMatrix4.identity() for _ in range(bone_count))
            return tuple(
                self.matrix4(array_pointer + index * 64, label)
                for index in range(bone_count)
            )

        cumulative_inverse = read_matrices(
            cumulative_inverse_pointer, "WDR cumulative inverse joint scale orientation"
        )
        cumulative = read_matrices(
            cumulative_pointer, "WDR cumulative joint scale orientation"
        )
        default_transforms = read_matrices(
            default_transforms_pointer, "WDR default bone transform"
        )
        pointer_to_index = {
            bones_pointer + index * 224: index for index in range(bone_count)
        }
        bones: list[WdrBone] = []
        for index in range(bone_count):
            bone_pointer = bones_pointer + index * 224
            bone_raw = self.read(bone_pointer, 224, "WDR bone")
            name_pointer = struct.unpack_from("<I", bone_raw, 0)[0]
            bone_flags = struct.unpack_from("<I", bone_raw, 4)[0]
            sibling_pointer, child_pointer, parent_pointer = struct.unpack_from("<3I", bone_raw, 8)
            stored_index, bone_id, mirror_index, reserved_short = struct.unpack_from(
                "<4H", bone_raw, 20
            )
            reserved_value = struct.unpack_from("<I", bone_raw, 28)[0]
            parent_index = parent_indices[index]
            if bone_id == 0 or not 0 <= parent_index < bone_count:
                parent_index = None
            bones.append(
                WdrBone(
                    self.string(name_pointer),
                    stored_index,
                    bone_id,
                    mirror_index,
                    WdrBoneFlags(bone_flags),
                    parent_index,
                    pointer_to_index.get(child_pointer),
                    pointer_to_index.get(sibling_pointer),
                    self.vector4(bone_pointer + 32, "WDR bone original position"),
                    self.vector4(bone_pointer + 48, "WDR bone original Euler rotation"),
                    self.vector4(bone_pointer + 64, "WDR bone original rotation"),
                    self.vector4(bone_pointer + 80, "WDR bone original scale"),
                    self.vector4(bone_pointer + 96, "WDR bone absolute position"),
                    self.vector4(bone_pointer + 112, "WDR bone absolute Euler rotation"),
                    self.vector4(bone_pointer + 128, "WDR bone scale orientation"),
                    self.vector4(bone_pointer + 144, "WDR bone minimum translation"),
                    self.vector4(bone_pointer + 160, "WDR bone maximum translation"),
                    self.vector4(bone_pointer + 176, "WDR bone minimum rotation"),
                    self.vector4(bone_pointer + 192, "WDR bone maximum rotation"),
                    self.vector4(bone_pointer + 208, "WDR bone reserved vector"),
                    reserved_short,
                    reserved_value,
                    cumulative_inverse[index],
                    cumulative[index],
                    default_transforms[index],
                    bone_pointer,
                )
            )

        completed: set[int] = set()
        active: set[int] = set()

        def update_transform(index: int) -> WdrMatrix4:
            bone = bones[index]
            if index in completed:
                return bone.absolute_transform
            if index in active:
                raise ValueError("cyclic WDR skeleton parent hierarchy")
            active.add(index)
            bone.local_transform = WdrMatrix4.transformation(
                WdrVector3(1.0, 1.0, 1.0),
                bone.original_rotation,
                WdrVector3(*tuple(bone.original_position)[:3]),
            )
            bone.absolute_transform = (
                bone.local_transform
                if bone.parent_index is None
                else bone.local_transform @ update_transform(bone.parent_index)
            )
            bone.inverse_bind_transform = bone.absolute_transform.inverse()
            bone.skin_transform = bone.inverse_bind_transform @ bone.absolute_transform
            active.remove(index)
            completed.add(index)
            return bone.absolute_transform

        for index in range(bone_count):
            update_transform(index)

        return WdrSkeleton(
            tuple(bones),
            bone_ids,
            parent_indices,
            cumulative_inverse,
            cumulative,
            default_transforms,
            translation_dof_count,
            rotation_dof_count,
            scale_dof_count,
            flags,
            reference_count,
            signature,
            tuple(reserved),  # type: ignore[arg-type]
            pointer,
        )

    def parse_light(self, pointer: int) -> WdrLight:
        raw = self.read(pointer, WDR_LIGHT_SIZE, "WDR light")
        position = WdrVector3(*struct.unpack_from("<3f", raw, 4))
        direction = WdrVector3(*struct.unpack_from("<3f", raw, 16))
        tangent = WdrVector3(*struct.unpack_from("<3f", raw, 28))
        color = struct.unpack_from("<4B", raw, 40)
        values = struct.unpack_from("<8f", raw, 44)
        flags, corona_hash, luminosity_hash = struct.unpack_from("<3I", raw, 76)
        flashiness = raw[88]
        reserved_1 = struct.unpack_from("<H", raw, 89)[0]
        light_type_value = raw[91]
        try:
            light_type: WdrLightType | int = WdrLightType(light_type_value)
        except ValueError:
            light_type = light_type_value
        corona_hdr_multiplier, fade_distance, shadow_fade_distance = struct.unpack_from(
            "<3f", raw, 92
        )
        bone_id = struct.unpack_from("<H", raw, 104)[0]
        reserved_2 = struct.unpack_from("<H", raw, 106)[0]
        return WdrLight(
            position,
            direction,
            tangent,
            color,
            *values,
            WdrLightFlags(flags),
            corona_hash,
            luminosity_hash,
            WdrLightTypeFlags(flashiness),
            light_type,
            corona_hdr_multiplier,
            fade_distance,
            shadow_fade_distance,
            bone_id,
            reserved_1,
            reserved_2,
        )

    def parse_drawable(
        self,
        pointer: int = RSC5_VIRTUAL_BASE,
        *,
        has_lights: bool = True,
    ) -> WdrDrawable:
        size = WDR_DRAWABLE_SIZE if has_lights else 116
        label = "WDR drawable" if has_lights else "fragment drawable base"
        raw = self.read(pointer, size, label)
        shader_group_pointer, skeleton_pointer = struct.unpack_from("<2I", raw, 8)
        bounding_center = WdrVector4(*struct.unpack_from("<4f", raw, 16))
        bounding_box_minimum = WdrVector4(*struct.unpack_from("<4f", raw, 32))
        bounding_box_maximum = WdrVector4(*struct.unpack_from("<4f", raw, 48))
        lod_pointers = struct.unpack_from("<4I", raw, 64)
        lod_distances = struct.unpack_from("<4f", raw, 80)
        draw_bucket_masks = struct.unpack_from("<4i", raw, 96)
        bounding_sphere_radius = struct.unpack_from("<f", raw, 112)[0]
        shader_group = (
            None if shader_group_pointer == 0 else self.parse_shader_group(shader_group_pointer)
        )
        skeleton = None if skeleton_pointer == 0 else self.parse_skeleton(skeleton_pointer)
        lods: list[WdrDrawableLod | None] = []
        for level in WdrLodLevel:
            lod_pointer = lod_pointers[level]
            lods.append(
                None if lod_pointer == 0
                else self.parse_lod(lod_pointer, level, lod_distances[level])
            )
        if shader_group is not None:
            for lod in lods:
                if lod is None:
                    continue
                for geometry in lod.geometries:
                    if geometry.shader_index < len(shader_group.shaders):
                        geometry.shader = shader_group.shaders[geometry.shader_index]
        if has_lights:
            lights_pointer, light_count, light_capacity = struct.unpack_from("<IHH", raw, 128)
            if light_capacity < light_count:
                raise ValueError("WDR light count exceeds its capacity")
            lights = tuple(
                self.parse_light(lights_pointer + index * WDR_LIGHT_SIZE)
                for index in range(light_count)
            ) if light_count else ()
            reserved = (
                *struct.unpack_from("<3I", raw, 116),
                *struct.unpack_from("<2I", raw, 136),
            )
        else:
            lights = ()
            reserved = ()
        return WdrDrawable(
            bounding_center,
            bounding_box_minimum,
            bounding_box_maximum,
            bounding_sphere_radius,
            tuple(lods),
            draw_bucket_masks,
            shader_group,
            skeleton,
            lights,
            reserved,
        )
