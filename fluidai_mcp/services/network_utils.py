import os
import signal
import socket
import psutil
from pathlib import Path
import json
import subprocess
import sys
import threading
from loguru import logger


def is_port_in_use(port):
    '''
    Check if a port is in use.
    args :
        port (int): The port number to check.
    returns:
        bool: True if the port is in use, False otherwise.
    '''
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def get_pid_on_port(port):
    '''
    Get the PID of the process using a specific port.
    args :
        port (int): The port number to check.
    returns:
        int: The PID of the process using the port, or None if no process is found.
    '''
    for conn in psutil.net_connections():
        if conn.status == 'LISTEN' and conn.laddr.port == port:
            return conn.pid
    return None

def kill_process(pid):
    '''
    ends a process using its PID.
    args :
        pid (int): The PID of the process to kill.
    returns:
        None
    '''
    try:
        os.kill(pid, signal.SIGTERM)
        logger.info(f"Killed process {pid} running on port")
    except Exception as e:
        logger.error(f"Failed to kill process {pid}: {e}", exc_info=True)



def kill_process_on_port(port):
    """Kill the process running on the given port, if any.
    args :
        port (int): The port number to check.
    returns:
        bool: True if a process was killed, False otherwise.
    """
    pid = get_pid_on_port(port)
    if pid:
        kill_process(pid)
        logger.info(f"Existing process on port {port} killed")
        return True
    return False

def find_free_port(start=8100, end=9000, taken_ports=None):
    """Find an available port in the given range that is not already taken.
    args :
        start (int): The starting port number (inclusive).
        end (int): The ending port number (exclusive).
        taken_ports (set): A set of ports that are already taken.
    returns:
        int: An available port number.
    """
    taken_ports = taken_ports or set()
    for port in range(start, end):
        if port not in taken_ports:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("", port))
                    return port
                except OSError:
                    continue
    raise RuntimeError("No free ports available in the range")
