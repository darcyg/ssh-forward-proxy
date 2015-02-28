import sys
import os
import socket
import select
import paramiko
import threading

try:
    import queue
except ImportError:
    import Queue as queue

import logging
import argparse

SSH_PORT = 22
logging.basicConfig(level=logging.DEBUG)

def make_client(host, port, username):
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    logging.info('Connecting to ssh host %s@%s:%d ...', username, host, port)
    client.connect(host, port, username=username)
    return client

class FakeSocket:
    """
    Fake socket to read from stdin and write to stdout
    conforming to the interface specified at
    http://docs.paramiko.org/en/1.15/api/transport.html
    """

    timeout = None
    def settimeout(self, timeout):
        self.timeout = timeout

    def send(self, string):
        if sys.stdout.closed:
            return 0
        return os.write(sys.stdout.fileno(), string)

    def recv(self, count):
        if sys.stdin.closed:
            return ''
        r, w, x = select.select([sys.stdin], [], [], self.timeout)
        if sys.stdin in r:
            return os.read(sys.stdin.fileno(), count)
        raise socket.timeout()

    def close(self):
        sys.stdin.close()
        sys.stdout.close()

class Pipe:
    def __init__(self, client, remote):
        self.client = client
        self.remote = remote

    def run(self, command):
        self.remote.exec_command(command)

        size = 1024
        while True:
            r, w, x = select.select([self.client, self.remote], [], [])

            if self.remote in r:
                content = self.remote.recv(size)
                if not content:
                    logging.debug('Output stream closed')
                    break
                self.client.sendall(content)

            if self.client in r:
                content = self.client.recv(size)
                if not content:
                    logger.debug('Input stream closed')
                    break
                self.remote.sendall(content)

        if self.remote.exit_status_ready():
            status = self.remote.recv_exit_status()
            self.client.send_exit_status(status)

        self.client.close()

class Proxy(paramiko.ServerInterface):
    timeout = 10
    host_key = paramiko.RSAKey(filename='server-key')

    def __init__(self, remote):
        self.username = None
        self.queue = queue.Queue()

        self.transport = paramiko.Transport(FakeSocket())
        self.transport.add_server_key(self.host_key)
        self.transport.start_server(server=self)

        try:
            channel, command = self.queue.get(self.timeout)
        except queue.Empty:
            logging.error('Client passed no commands')
            sys.exit(1)
        Pipe(channel, remote).run(command)
        self.transport.close()

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED

    def check_auth_none(self, username):
        self.username = username
        return paramiko.AUTH_SUCCESSFUL
    
    def get_allowed_auths(self, username):
        return 'none'

    def check_channel_exec_request(self, channel, command):
        self.queue.put((channel, command))
        return True

if __name__ == '__main__':
    host = sys.argv[1]
    port = int(sys.argv[2])
    user = sys.argv[3]
    remote_client = make_client(host, port, user)
    remote_channel = remote_client.get_transport().open_session()

    Proxy(remote_channel)
    remote_client.close()

