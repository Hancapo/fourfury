from __future__ import annotations

import struct
import unittest

import fourfury.wdr as wdr_module
from fourfury import Rsc5Resource
from fourfury.wdr import (
    WdrVertexElement,
    WdrVertexElementType,
    WdrVertexLayout,
    WdrVertexSemantic,
    _WdrReader,
)


class NativeWdrTests(unittest.TestCase):
    def test_facade_decoder_state_remains_patchable_after_module_split(self) -> None:
        layout = WdrVertexLayout(
            fvf=1,
            fvf_size=12,
            flags=0,
            dynamic_order=0,
            channel_count=1,
            declaration_types=0,
            elements=(
                WdrVertexElement(
                    WdrVertexSemantic.POSITION,
                    WdrVertexElementType.FLOAT3,
                    0,
                ),
            ),
            _pointer=0,
        )
        reader = _WdrReader(Rsc5Resource(0, 0, b""))
        original = wdr_module._native_decode_wdr_vertices
        try:
            wdr_module._native_decode_wdr_vertices = (
                lambda *_: {int(WdrVertexSemantic.POSITION): ((1.0, 2.0, 3.0),)}
            )
            channels = reader.decode_vertex_channels(b"\0" * 12, 1, 12, layout)
        finally:
            wdr_module._native_decode_wdr_vertices = original

        self.assertEqual(
            channels[WdrVertexSemantic.POSITION],
            ((1.0, 2.0, 3.0),),
        )

    def test_native_vertex_columns_match_python_fallback(self) -> None:
        elements: list[WdrVertexElement] = []
        offset = 0
        for semantic, element_type in enumerate(WdrVertexElementType, start=0):
            if element_type is WdrVertexElementType.NOTHING:
                continue
            elements.append(
                WdrVertexElement(WdrVertexSemantic(semantic), element_type, offset)
            )
            offset += elements[-1].size
        layout = WdrVertexLayout(
            fvf=sum(1 << int(element.semantic) for element in elements),
            fvf_size=offset,
            flags=0,
            dynamic_order=0,
            channel_count=len(elements),
            declaration_types=0,
            elements=tuple(elements),
            _pointer=0,
        )
        data = bytearray(offset)
        values = {
            WdrVertexElementType.HALF2: (1.0, -2.0),
            WdrVertexElementType.FLOAT: (3.5,),
            WdrVertexElementType.HALF4: (1.0, 2.0, 3.0, 4.0),
            WdrVertexElementType.FLOAT_SINGLE: (-5.5,),
            WdrVertexElementType.FLOAT2: (6.0, 7.0),
            WdrVertexElementType.FLOAT3: (8.0, 9.0, 10.0),
            WdrVertexElementType.FLOAT4: (11.0, 12.0, 13.0, 14.0),
            WdrVertexElementType.UBYTE4: (1, 2, 3, 4),
            WdrVertexElementType.COLOR: (5, 6, 7, 8),
            WdrVertexElementType.DEC3N: (0,),
        }
        formats = {
            WdrVertexElementType.HALF2: "<2e",
            WdrVertexElementType.FLOAT: "<f",
            WdrVertexElementType.HALF4: "<4e",
            WdrVertexElementType.FLOAT_SINGLE: "<f",
            WdrVertexElementType.FLOAT2: "<2f",
            WdrVertexElementType.FLOAT3: "<3f",
            WdrVertexElementType.FLOAT4: "<4f",
            WdrVertexElementType.UBYTE4: "<4B",
            WdrVertexElementType.COLOR: "<4B",
            WdrVertexElementType.DEC3N: "<I",
        }
        for element in elements:
            struct.pack_into(
                formats[element.element_type],
                data,
                element.offset,
                *values[element.element_type],
            )

        reader = _WdrReader(Rsc5Resource(0, 0, b""))
        native_decoder = wdr_module._native_decode_wdr_vertices
        if native_decoder is None:
            self.skipTest("optional native extension is not built")
        native = reader.decode_vertex_channels(bytes(data), 1, offset, layout)
        try:
            wdr_module._native_decode_wdr_vertices = None
            fallback = reader.decode_vertex_channels(bytes(data), 1, offset, layout)
        finally:
            wdr_module._native_decode_wdr_vertices = native_decoder

        self.assertEqual(native, fallback)


if __name__ == "__main__":
    unittest.main()
