import os
import sys
import unittest

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LIB = os.path.normpath(os.path.join(REPO, "lib"))


class SmokeTest(unittest.TestCase):
    def test_lib_dir_exists(self):
        self.assertTrue(os.path.isdir(LIB))

    def test_installer_present_in_lib(self):
        sys.path.insert(0, LIB)
        try:
            self.assertTrue(os.path.isfile(os.path.join(LIB, "install-pinned.sh")))
        finally:
            sys.path.remove(LIB)


if __name__ == "__main__":
    unittest.main()
