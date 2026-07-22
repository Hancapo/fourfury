from __future__ import annotations

import unittest

from fourfury import GtxdDocument, GtxdHierarchy, IdeDocument


class GtxdTests(unittest.TestCase):
    def test_reads_edits_and_preserves_txdp_ide_formatting(self) -> None:
        source = (
            "# Texture parents\r\n"
            "txdp\r\n"
            "child_a, parent_a\r\n"
            "child_b,parent_b\r\n"
            "end\r\n"
        )
        document = GtxdDocument.from_text(source)

        self.assertEqual(document.to_text(), source)
        self.assertEqual(document.parent_of("CHILD_A"), "parent_a")
        self.assertEqual(document.chain("child_b"), ("child_b", "parent_b"))

        document.dependencies[0].parent = "shared_parent"
        document.add_dependency("child_c", "parent_c")
        reparsed = GtxdDocument.from_bytes(document.to_bytes())

        self.assertEqual(reparsed.parent_of("child_a"), "shared_parent")
        self.assertEqual(reparsed.parent_of("child_c"), "parent_c")
        self.assertIn("child_b,parent_b\r\n", reparsed.to_text())

    def test_combines_txdp_sections_from_regular_ide_documents(self) -> None:
        first = IdeDocument.from_text("txdp\na, b\nend\n")
        second = IdeDocument.from_text("txdp\nb, c\nend\n")

        hierarchy = GtxdHierarchy.from_documents((first, second))

        self.assertEqual(hierarchy.chain("a"), ("a", "b", "c"))

    def test_rejects_cycles_and_malformed_dependencies(self) -> None:
        hierarchy = GtxdHierarchy({"a": "b", "b": "a"})
        with self.assertRaisesRegex(ValueError, "cyclic GTXD hierarchy"):
            hierarchy.chain("a")
        with self.assertRaisesRegex(ValueError, "requires child and parent"):
            GtxdDocument.from_text("txdp\nchild_only\nend\n")


if __name__ == "__main__":
    unittest.main()
