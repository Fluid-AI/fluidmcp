import os
import signal
import socket
import psutil
import platform
import subprocess
from pathlib import Path
import json
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
    try:
        # Try to bind to the port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('localhost', port))
            return False
    except OSError:
        return True

def get_pid_on_port_macos(port):
    """macOS-specific method to get PID on port using lsof"""
    try:
        # Use lsof command which works without special permissions
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'], 
            capture_output=True, 
            text=True, 
            check=False
        )
        if result.stdout.strip():
            return int(result.stdout.strip().split('\n')[0])
        return None
    except (subprocess.SubprocessError, ValueError):
        return None

def get_pid_on_port(port):
    """Get the PID of the process using the given port"""
    
    # Use macOS-specific method if on macOS
    if platform.system() == "Darwin":
        return get_pid_on_port_macos(port)
    
    # Original method for other platforms
    try:
        for conn in psutil.net_connections():
            if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                return conn.pid
    except (psutil.AccessDenied, PermissionError):
        # Fallback for permission issues
        return None
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
        print(f":boom: Killed process {pid} running on port.")
    except Exception as e:
        print(f":x: Failed to kill process {pid}: {e}")



def kill_process_on_port(port):
    """Kill the process running on the given port, if any.
    args :
        port (int): The port number to check.
    returns:
        bool: True if a process was killed, False otherwise.
    """
    pid = get_pid_on_port(port)
    if pid:
        print(f"🔄 Killing process {pid} on port {port}")
        
        # Use different methods based on OS
        if platform.system() == "Darwin":
            # macOS: Use kill command
            subprocess.run(['kill', '-9', str(pid)], check=False)
        else:
            kill_process(pid)
            print(f"Existing process on port {port} killed.")
        return True
    else:
        print(f"📍 No process found on port {port}")
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
