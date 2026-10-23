"""Validação isolada do entrypoint: não inicia Xvfb, pipeline ou Google Cloud."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RunJobTest(unittest.TestCase):
    def test_image_keeps_xvfb_wrapper_under_init(self):
        dockerfile = (ROOT / 'Dockerfile').read_text()
        self.assertIn('xvfb xauth tini', dockerfile)
        self.assertIn('ENTRYPOINT ["/usr/bin/tini", "--", "sh", "scripts/run_job.sh"]', dockerfile)

    def test_wrapper_forwards_args_and_emits_boot_without_running_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'xvfb-run'
            fake.write_text('#!/bin/sh\nprintf "ARG:%s\\n" "$@"\n')
            fake.chmod(0o755)
            result = subprocess.run(
                ['sh', str(ROOT / 'scripts/run_job.sh'), '--inspect'],
                env=os.environ | {'PATH': directory + os.pathsep + os.environ['PATH']},
                text=True, capture_output=True, timeout=10, check=True,
            )
        self.assertIn('wrapper_pid=', result.stderr)
        self.assertIn('ARG:--inspect', result.stdout)
        self.assertIn('ARG:/dev/stderr', result.stdout)
        self.assertIn('ARG:python', result.stdout)

    def test_wrapper_does_not_dump_tracebacks_periodically(self):
        # O dump periódico lê a pilha da thread principal fora do GIL e já derrubou a rotina com SIGSEGV.
        wrapper = (ROOT / 'scripts/run_job.sh').read_text()
        self.assertIn('faulthandler.enable()', wrapper)
        self.assertNotIn('dump_traceback_later', wrapper)


if __name__ == '__main__':
    unittest.main()