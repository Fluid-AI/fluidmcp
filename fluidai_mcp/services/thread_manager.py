# services/thread_manager.py
import threading
import socket
import time
from typing import Dict, Set
from pathlib import Path
from loguru import logger

class ThreadSafePortAllocator:
    """
    Manages port allocation across multiple threads to prevent conflicts.
    Uses a lock to ensure only one thread can allocate a port at a time.
    """
    
    def __init__(self, start: int = 8100, end: int = 8200):
        """
        Initialize the port allocator with a range of ports.
        
        Args:
            start (int): Starting port number (inclusive)
            end (int): Ending port number (exclusive)
        """
        self.start = start  # First port in range
        self.end = end      # Last port in range (exclusive)
        self.allocated_ports: Set[int] = set()  # Track which ports are taken
        self.lock = threading.Lock()  # Ensures thread-safe access
        logger.info(f"Port allocator initialized: range {start}-{end-1}")
    
    def get_next_port(self) -> int:
        """
        Find and allocate the next available port in a thread-safe manner.
        
        Returns:
            int: An available port number
            
        Raises:
            RuntimeError: If no ports are available in the range
        """
        # Lock ensures only one thread can execute this block at a time
        with self.lock:
            # Try each port in the range
            for port in range(self.start, self.end):
                # Skip if we've already allocated this port
                if port not in self.allocated_ports:
                    # Double-check the port is actually free on the system
                    if self._is_port_free(port):
                        # Mark this port as allocated
                        self.allocated_ports.add(port)
                        logger.debug(f"Allocated port {port}")
                        return port
            
            # If we get here, no ports were available
            raise RuntimeError(f"No free ports available in range {self.start}-{self.end-1}")
    
    def release_port(self, port: int):
        """
        Release a port back to the available pool.
        
        Args:
            port (int): Port number to release
        """
        # Lock ensures thread-safe modification of allocated_ports set
        with self.lock:
            # Remove from allocated set (discard doesn't raise error if not present)
            self.allocated_ports.discard(port)
            logger.debug(f"Released port {port}")
    
    def _is_port_free(self, port: int) -> bool:
        """
        Check if a specific port is actually free on the system.
        
        Args:
            port (int): Port number to check
            
        Returns:
            bool: True if port is free, False if occupied
        """
        try:
            # Try to bind to the port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", port))  # Bind to all interfaces on this port
                return True  # If binding succeeds, port is free
        except OSError:
            # If binding fails, port is already in use
            return False


class MCPServerThread(threading.Thread):
    """
    A thread that runs a single MCP server with its own FastAPI instance.
    Each thread is isolated and has its own logging context.
    """
    
    def __init__(self, package_name: str, dest_dir: Path, port: int):
        """
        Initialize the MCP server thread.
        
        Args:
            package_name (str): Name of the MCP package
            dest_dir (Path): Directory containing the MCP server files
            port (int): Port number for this server's FastAPI instance
        """
        # Initialize the thread with a descriptive name
        super().__init__(name=f"MCP-{package_name}", daemon=True)
        
        # Store configuration
        self.package_name = package_name
        self.dest_dir = dest_dir
        self.port = port
        
        # Per-thread logging context - adds package name and port to all log messages
        self.logger = logger.bind(
            thread_name=self.name,           # Thread identifier
            package_name=package_name,       # MCP package name
            port=port,                       # Port number
            thread_id=threading.get_ident() # System thread ID
        )
        
        # Placeholders for resources we'll create
        self.mcp_process = None      # Will hold subprocess.Popen object
        self.mini_fastapi = None     # Will hold FastAPI instance
        self.shutdown_requested = False  # Flag for graceful shutdown
        
        self.logger.info(f"Initialized MCP server thread for {package_name} on port {port}")
    
    def run(self):
        """
        Main thread execution method. This runs in the separate thread.
        Contains the complete lifecycle of the MCP server.
        """
        try:
            self.logger.info("Starting MCP server thread execution")
            
            # Step 1: Launch MCP server and get router using existing function
            self.logger.info("Launching MCP server...")
            package_name, router, process = self._launch_mcp_subprocess()
            
            if not package_name or not router or not process:
                self.logger.error("Failed to launch MCP server")
                return
            
            # Store the process and router for later use
            self.mcp_process = process
            self.router = router
            
            # Step 2: Create mini-FastAPI and include the router
            self.logger.info("Creating mini-FastAPI instance...")
            self.mini_fastapi = self._create_mini_fastapi()
            
            if not self.mini_fastapi:
                self.logger.error("Failed to create mini-FastAPI")
                return
            
            # Step 3: Run the FastAPI server (this blocks until shutdown)
            self.logger.info(f"Starting FastAPI server on port {self.port}")
            import uvicorn
            uvicorn.run(
                self.mini_fastapi, 
                host="0.0.0.0", 
                port=self.port,
                log_level="warning"  # Reduce uvicorn noise in logs
            )
            
        except Exception as e:
            # Log any unhandled exceptions
            self.logger.error(f"Thread execution failed: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            # Always clean up resources when thread exits
            self._cleanup()
    
    def _launch_mcp_subprocess(self):
        """
        Launch the MCP server using the modified existing function.
        The existing function now returns (package_name, router, process).
        
        Returns:
            tuple: (package_name, router, process) if successful, (None, None, None) if failed
        """
        try:
            # Import the MODIFIED existing function that now returns the process
            from fluidai_mcp.services.package_launcher import launch_mcp_using_fastapi_proxy
            
            self.logger.info("Launching MCP server using existing function")
            
            # The modified function now returns (package_name, router, process)
            package_name, router, process = launch_mcp_using_fastapi_proxy(self.dest_dir)
            
            if package_name and router and process:
                self.logger.info(f"Successfully launched MCP server: {package_name} with PID: {process.pid}")
                # Store the process for cleanup
                self.mcp_process = process
                return package_name, router, process
            else:
                self.logger.error("Failed to launch MCP server")
                return None, None, None
                
        except Exception as e:
            self.logger.error(f"Error launching MCP server: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None, None, None
    
    def _initialize_mcp_server(self) -> bool:
        """
        MCP server initialization is already handled by the existing launch function.
        
        Returns:
            bool: True (initialization handled by existing function)
        """
        # The existing launch_mcp_using_fastapi_proxy already handles initialization
        # via initialize_mcp_server_with_logging() call
        self.logger.debug("MCP server initialization completed by existing launch function")
        return True
    
    def _create_mini_fastapi(self):
        """
        Create a FastAPI instance using the router from the existing function.
        The router was already created by _launch_mcp_subprocess().
        
        Returns:
            FastAPI: Configured FastAPI instance with MCP endpoints
        """
        try:
            from fastapi import FastAPI
            
            # We already have the router from _launch_mcp_subprocess()
            if not hasattr(self, 'router') or not self.router:
                self.logger.error("No router available from launch function")
                return None
            
            # Create FastAPI app and include the existing router
            app = FastAPI(
                title=f"MCP Server - {self.package_name}",
                description=f"Individual FastAPI instance for {self.package_name}",
                version="1.0.0"
            )
            
            # Include the router created by the existing launch function
            # This router already has all the MCP endpoints properly configured
            app.include_router(self.router, tags=[self.package_name])
            
            # Add health check endpoint specific to this thread
            @app.get("/health")
            def health_check():
                """Health check endpoint for this MCP server thread"""
                return {
                    "status": "healthy",
                    "package_name": self.package_name,
                    "port": self.port,
                    "thread_name": self.name,
                    "process_alive": self.mcp_process and self.mcp_process.poll() is None,
                    "process_pid": self.mcp_process.pid if self.mcp_process else None
                }
            
            self.logger.info(f"Mini-FastAPI instance created for {self.package_name} using existing router")
            return app
            
        except Exception as e:
            self.logger.error(f"Error creating mini-FastAPI: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def _cleanup(self):
        """
        Clean up resources when thread is shutting down.
        """
        self.logger.info("Cleaning up thread resources...")
        
        # Terminate MCP subprocess if it exists
        if self.mcp_process:
            try:
                self.mcp_process.terminate()
                self.mcp_process.wait(timeout=5)  # Wait up to 5 seconds
                self.logger.info("MCP subprocess terminated")
            except Exception as e:
                self.logger.error(f"Error terminating MCP subprocess: {e}")
        
        self.logger.info("Thread cleanup completed")
    
    def shutdown(self):
        """
        Request graceful shutdown of this thread.
        """
        self.logger.info("Shutdown requested")
        self.shutdown_requested = True


class MCPThreadManager:
    """
    Manages multiple MCP server threads.
    Provides a simple interface to start, monitor, and stop MCP servers.
    """
    
    def __init__(self, port_start: int = 8100, port_end: int = 8200):
        """
        Initialize the thread manager.
        
        Args:
            port_start (int): Starting port for allocation
            port_end (int): Ending port for allocation (exclusive)
        """
        # Port allocator for assigning unique ports to each thread
        self.port_allocator = ThreadSafePortAllocator(port_start, port_end)
        
        # Dictionary to track all active threads: package_name -> MCPServerThread
        self.threads: Dict[str, MCPServerThread] = {}
        
        # Registry mapping package names to their service URLs
        self.service_registry: Dict[str, str] = {}
        
        # Set up logging for the manager
        self.logger = logger.bind(component="ThreadManager")
        
        self.logger.info(f"Thread manager initialized with port range {port_start}-{port_end-1}")
    
    def start_mcp_thread(self, package_name: str, dest_dir: Path) -> bool:
        """
        Start a new MCP server thread.
        
        Args:
            package_name (str): Name of the MCP package
            dest_dir (Path): Directory containing MCP server files
            
        Returns:
            bool: True if thread started successfully, False otherwise
        """
        try:
            # Check if thread already exists for this package
            if package_name in self.threads:
                self.logger.warning(f"Thread for {package_name} already exists")
                return False
            
            # Allocate a port for this thread
            port = self.port_allocator.get_next_port()
            
            # Create and start the thread
            thread = MCPServerThread(package_name, dest_dir, port)
            thread.start()
            
            # Store references
            self.threads[package_name] = thread
            self.service_registry[package_name] = f"http://localhost:{port}"
            
            self.logger.info(f"Started thread for {package_name} on port {port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start thread for {package_name}: {e}")
            return False
    
    def stop_mcp_thread(self, package_name: str) -> bool:
        """
        Stop a specific MCP server thread.
        
        Args:
            package_name (str): Name of the package to stop
            
        Returns:
            bool: True if stopped successfully, False otherwise
        """
        if package_name not in self.threads:
            self.logger.warning(f"No thread found for {package_name}")
            return False
        
        try:
            thread = self.threads[package_name]
            
            # Request graceful shutdown
            thread.shutdown()
            
            # Wait for thread to finish (with timeout)
            thread.join(timeout=10)
            
            # Release the port
            self.port_allocator.release_port(thread.port)
            
            # Clean up references
            del self.threads[package_name]
            del self.service_registry[package_name]
            
            self.logger.info(f"Stopped thread for {package_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping thread for {package_name}: {e}")
            return False
    
    def stop_all_threads(self):
        """
        Stop all MCP server threads gracefully.
        """
        self.logger.info(f"Stopping all {len(self.threads)} threads...")
        
        # Get list of package names to avoid dictionary modification during iteration
        package_names = list(self.threads.keys())
        
        # Stop each thread
        for package_name in package_names:
            self.stop_mcp_thread(package_name)
        
        self.logger.info("All threads stopped")
    
    def get_service_url(self, package_name: str) -> str:
        """
        Get the service URL for a specific package.
        
        Args:
            package_name (str): Name of the package
            
        Returns:
            str: Service URL, or None if package not found
        """
        return self.service_registry.get(package_name)
    
    def get_all_services(self) -> Dict[str, str]:
        """
        Get all active services.
        
        Returns:
            Dict[str, str]: Dictionary mapping package names to service URLs
        """
        return self.service_registry.copy()
    
    def is_thread_alive(self, package_name: str) -> bool:
        """
        Check if a specific thread is still running.
        
        Args:
            package_name (str): Name of the package to check
            
        Returns:
            bool: True if thread is alive, False otherwise
        """
        if package_name not in self.threads:
            return False
        
        return self.threads[package_name].is_alive()
    
    def get_thread_count(self) -> int:
        """
        Get the number of active threads.
        
        Returns:
            int: Number of active threads
        """
        return len(self.threads)
    
    def restart_mcp_thread(self, package_name: str, dest_dir: Path) -> bool:
        """Restart thread with new port and update routing"""
        
        # 1. Get old thread info
        old_thread = self.threads.get(package_name)
        old_port = old_thread.port if old_thread else None
        
        logger.info(f"🔄 RAILWAY DEBUG: Restarting {package_name} (old port: {old_port})")
        
        # 2. Clean up old thread
        if package_name in self.threads:
            del self.threads[package_name]
            logger.info(f"🗑️ RAILWAY DEBUG: Removed dead thread for {package_name}")
        
        # 3. Start new thread (this gets a new port automatically)
        launch_new_thread = self.start_mcp_thread(package_name, dest_dir)
        
        if launch_new_thread:
            new_port = self.threads[package_name].port
            new_service_url = f"http://localhost:{new_port}"
            
            # 4. Update service registry (THIS IS THE KEY!)
            self.service_registry[package_name] = new_service_url
            
            logger.info(f"✅ RAILWAY DEBUG: {package_name} restarted on new port {new_port}")
            logger.info(f"🔗 RAILWAY DEBUG: Service URL updated to {new_service_url}")
            
            # 5. Release old port for future use
            if old_port:
                self.port_allocator.release_port(old_port)
                logger.info(f"🔄 RAILWAY DEBUG: Released old port {old_port}")
            
            return True
        else:
            logger.error(f"❌ RAILWAY DEBUG: Failed to restart {package_name}")
            return False