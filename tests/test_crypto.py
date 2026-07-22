from __future__ import annotations

import sys
import unittest

from fourfury import GTAIVCrypto


class CryptoTests(unittest.TestCase):
    def test_decrypts_aligned_prefix_and_preserves_tail(self) -> None:
        source = bytes(range(35))

        decrypted = GTAIVCrypto().decrypt(source)

        self.assertEqual(
            decrypted.hex(),
            "da89c89f5e55cc07bf865637678722c9"
            "ac5e53027bbb32916b205254619d3d60202122",
        )

    @unittest.skipUnless(sys.platform == "win32", "native AES is Windows-only")
    def test_native_aes_matches_the_public_crypto_api(self) -> None:
        try:
            from fourfury._native import aes16_decrypt, create_aes_context
        except ImportError:
            self.skipTest("optional native extension is not built")

        source = bytes(range(255)) * 257
        context = create_aes_context(GTAIVCrypto().aes_key)

        self.assertEqual(aes16_decrypt(context, bytes(range(35))).hex(), (
            "da89c89f5e55cc07bf865637678722c9"
            "ac5e53027bbb32916b205254619d3d60202122"
        ))
        self.assertEqual(aes16_decrypt(context, source), GTAIVCrypto().decrypt(source))


if __name__ == "__main__":
    unittest.main()
