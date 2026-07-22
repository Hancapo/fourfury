from __future__ import annotations

import unittest

import fourfury.wbn as wbn_module
from fourfury import WbnBvhGeometry, WbnComposite, WbnDocument

from test_wbn import _sample_wbn


_DECODER_NAMES = (
    "_native_decode_wbn_vertices",
    "_native_decode_wbn_polygons",
    "_native_decode_wbn_bvh_nodes",
    "_native_decode_wbn_bvh_subtrees",
)


class NativeWbnTests(unittest.TestCase):
    def test_native_and_python_decoders_are_losslessly_equivalent(self) -> None:
        if any(getattr(wbn_module, name) is None for name in _DECODER_NAMES):
            self.skipTest("the optional native WBN decoder is unavailable")

        source = _sample_wbn()
        native_document = WbnDocument.from_bytes(source)
        decoders = {name: getattr(wbn_module, name) for name in _DECODER_NAMES}
        try:
            for name in _DECODER_NAMES:
                setattr(wbn_module, name, None)
            python_document = WbnDocument.from_bytes(source)
        finally:
            for name, decoder in decoders.items():
                setattr(wbn_module, name, decoder)

        self.assertEqual(native_document.to_bytes(), source)
        self.assertEqual(python_document.to_bytes(), source)
        self.assertIsInstance(native_document.root, WbnComposite)
        self.assertIsInstance(python_document.root, WbnComposite)
        native_geometry = native_document.geometries[0]
        python_geometry = python_document.geometries[0]
        self.assertIsInstance(native_geometry, WbnBvhGeometry)
        self.assertIsInstance(python_geometry, WbnBvhGeometry)
        self.assertEqual(native_geometry.vertices, python_geometry.vertices)
        self.assertEqual(
            [polygon.to_bytes() for polygon in native_geometry.polygons],
            [polygon.to_bytes() for polygon in python_geometry.polygons],
        )
        assert isinstance(native_geometry, WbnBvhGeometry)
        assert isinstance(python_geometry, WbnBvhGeometry)
        assert native_geometry.bvh is not None
        assert python_geometry.bvh is not None
        self.assertEqual(
            [node.to_bytes() for node in native_geometry.bvh.nodes],
            [node.to_bytes() for node in python_geometry.bvh.nodes],
        )
        self.assertEqual(
            [subtree.to_bytes() for subtree in native_geometry.bvh.subtrees],
            [subtree.to_bytes() for subtree in python_geometry.bvh.subtrees],
        )

    def test_native_decoder_rejects_out_of_bounds_arrays(self) -> None:
        decoder = wbn_module._native_decode_wbn_vertices
        if decoder is None:
            self.skipTest("the optional native WBN decoder is unavailable")

        with self.assertRaisesRegex(ValueError, "outside the input buffer"):
            decoder(b"\0" * 5, 0, 1)


if __name__ == "__main__":
    unittest.main()
