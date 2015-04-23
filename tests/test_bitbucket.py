"""

This is a real life test of the proxy's capabilities.

There is a private repository at https://bitbucket.org/lincheney/ssh-forward-proxy-test
which has an associated read-only SSH key which is stored in tests/ssh-forward-proxy-test-key

We will provide the private key to the proxy and attempt to git clone the repo
by modifying GIT_SSH to point to the proxy.

"""

import unittest
import os
import shlex
import subprocess
import shutil
import time
import sys

try:
    from shlex import quote as shell_quote
except ImportError:
    from pipes import quote as shell_quote

class BitBucketTest(unittest.TestCase):

    ROOT_DIR = os.path.abspath(os.path.join(__file__, '..', '..'))
    REPO_DIR = os.path.join(ROOT_DIR, 'tests', 'test-git-repo')
    SSH_KEY = os.path.join(ROOT_DIR, 'tests', 'ssh-forward-proxy-test-key')

    REPO_URL = 'git@bitbucket.org:lincheney/ssh-forward-proxy-test.git'

    GIT_PATH = os.path.join(REPO_DIR, '.git')
    README_PATH = os.path.join(REPO_DIR, 'README')
    README_TEXT = 'This is a test for ssh-forward-proxy.\n'

    def setUp(self):
        if os.path.exists(self.REPO_DIR):
            shutil.rmtree(self.REPO_DIR)
        self.env = os.environ.copy()

    def test_repo_forbidden(self):
        """
        make sure the repository can't be accessed normally
        """

        self.env['GIT_SSH'] = os.path.join(self.ROOT_DIR, 'tests', 'git_ssh_no_identity.sh')
        with self.assertRaises(subprocess.CalledProcessError):
            subprocess.check_call(['git', 'clone', self.REPO_URL, self.REPO_DIR], env=self.env)

    def test_repo_accessible_through_proxy(self):
        PORT = '4000'
        self.env['PROXY_ARGS'] = '-i ' + shell_quote(self.SSH_KEY)
        self.env['GIT_SSH'] = os.path.join(self.ROOT_DIR, 'tests', 'git_ssh_proxy.sh')
        self.env['PYTHONPATH'] = self.ROOT_DIR

        server = None
        try:
            # run the server
            server_cmd = os.path.join(self.ROOT_DIR, 'bin', 'simple-ssh-server.py')
            server = subprocess.Popen([sys.executable, server_cmd, PORT], env=self.env)
            # wait a second
            time.sleep(1)
            self.assertIsNone( server.poll() )

            # clone
            subprocess.check_call(['git', 'clone', self.REPO_URL, self.REPO_DIR], env=self.env)

            # check .git exists
            self.assertTrue( os.path.exists(self.GIT_PATH) )
            # check README exists
            self.assertTrue( os.path.exists(self.README_PATH) )
            # check README has correct contents
            with open(self.README_PATH) as f:
                readme = f.read()
            self.assertEqual(readme, self.README_TEXT)
        finally:
            if server:
                server.kill()
