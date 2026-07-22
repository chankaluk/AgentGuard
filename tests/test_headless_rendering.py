from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HeadlessRenderingTests(unittest.TestCase):
    def test_evaluation_plots_render_without_tk(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "plots")
            code = (
                "import sys,numpy as np;"
                f"sys.path.insert(0,{str(ROOT / 'scripts')!r});"
                f"sys.path.insert(0,{str(ROOT / 'src')!r});"
                "from evaluate import make_plots;"
                f"make_plots({{'threshold':0.5}},np.array([0.1,0.9]),"
                f"np.array([0,1]),__import__('pathlib').Path({str(output)!r}))"
            )
            environment = os.environ.copy()
            environment.pop("MPLBACKEND", None)
            environment["MPLCONFIGDIR"] = str(Path(directory, "mpl-cache"))
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((output / "score_distribution.png").is_file())


if __name__ == "__main__":
    unittest.main()
