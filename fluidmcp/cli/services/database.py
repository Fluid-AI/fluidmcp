"""
MongoDB database layer for FluidMCP server state persistence.

This module provides async database operations using motor (async MongoDB driver)
for storing server configurations, runtime instances, and logs.
"""
import os
import certifi
from typing import Optional, Dict, Any, List
from typing import Optional, Dict, Any, List, Deque
from datetime import datetime
from collections import deque
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError, ConnectionFailure
from loguru import logger


class LogBuffer:
    """In-memory buffer for failed log writes with retry mechanism."""

    def __init__(self, max_size: int = 100):
        """Initialize log buffer."""
        self.buffer: Deque[Dict[str, Any]] = deque(maxlen=max_size)
        self.failed_count = 0
        self.success_count = 0

    def add(self, log_entry: Dict[str, Any]):
        """Add failed log entry to buffer."""
        self.buffer.append(log_entry)
        self.failed_count += 1

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all buffered entries and clear buffer."""
        entries = list(self.buffer)
        self.buffer.clear()
        return entries

    def size(self) -> int:
        """Get current buffer size."""
        return len(self.buffer)

    def get_stats(self) -> Dict[str, int]:
        """Get buffer statistics."""
        return {
            "buffered": len(self.buffer),
            "failed_total": self.failed_count,
            "success_total": self.success_count
        }


class DatabaseManager:
    """Manages MongoDB connection and operations for FluidMCP state."""

    def __init__(self, mongodb_uri: Optional[str] = None, database_name: str = "fluidmcp"):
        """
        Initialize MongoDB connection.

        Args:
            mongodb_uri: MongoDB connection string (defaults to env var or localhost)
            database_name: Database name to use (default: fluidmcp)
        """
        self.mongodb_uri = mongodb_uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.database_name = database_name
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self._change_streams_supported: Optional[bool] = None
        self._log_buffer = LogBuffer(max_size=100)
        self._retry_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """
        Establish MongoDB connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Get timeout values from environment or use defaults
            server_timeout = int(os.getenv("FMCP_MONGODB_SERVER_TIMEOUT", "30000"))
            connect_timeout = int(os.getenv("FMCP_MONGODB_CONNECT_TIMEOUT", "10000"))
            socket_timeout = int(os.getenv("FMCP_MONGODB_SOCKET_TIMEOUT", "45000"))

            # TLS certificate validation - secure by default
            allow_invalid_certs = os.getenv("FMCP_MONGODB_ALLOW_INVALID_CERTS", "false").lower() == "true"

            if allow_invalid_certs:
                logger.warning("⚠️  WARNING: TLS certificate validation DISABLED for MongoDB!")
                logger.warning("⚠️  This is a SECURITY RISK - vulnerable to man-in-the-middle attacks!")
                logger.warning("⚠️  Only use FMCP_MONGODB_ALLOW_INVALID_CERTS=true for development!")

            self.client = AsyncIOMotorClient(
                self.mongodb_uri,
                serverSelectionTimeoutMS=server_timeout,
                connectTimeoutMS=connect_timeout,
                socketTimeoutMS=socket_timeout,
                tlsAllowInvalidCertificates=allow_invalid_certs
            )

            logger.debug(f"MongoDB timeouts: server={server_timeout}ms, connect={connect_timeout}ms, socket={socket_timeout}ms")
            self.db = self.client[self.database_name]

            # Test connection
            await self.client.admin.command('ping')
            logger.info(f"Connected to MongoDB at {self.mongodb_uri}")

            # Check if change streams are supported (requires replica set)
            try:
                server_info = await self.client.server_info()
                version = server_info.get('version', '0.0.0')
                major_version = int(version.split('.')[0])

                # Change streams require MongoDB 3.6+ AND replica set
                if major_version >= 4:
                    # Check if replica set is configured
                    try:
                        status = await self.client.admin.command('replSetGetStatus')
                        self._change_streams_supported = True
                        logger.info("MongoDB change streams supported (replica set detected)")
                    except Exception:
                        self._change_streams_supported = False
                        logger.warning("MongoDB change streams NOT supported (standalone instance)")
                else:
                    self._change_streams_supported = False
                    logger.warning(f"MongoDB version {version} < 4.0, change streams not supported")
            except Exception as e:
                self._change_streams_supported = False
                logger.warning(f"Could not determine change stream support: {e}")

            return True

        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            return False

    async def init_db(self) -> bool:
        """
        Initialize database with collections and indexes.

        Returns:
            True if initialization successful
        """
        if not await self.connect():
            return False

        try:
            # Create indexes on servers collection
            await self.db.servers.create_index("id", unique=True)
            logger.info("Created unique index on servers.id")

            # Create indexes on server_instances collection
            await self.db.server_instances.create_index("server_id")
            logger.info("Created index on server_instances.server_id")

            # Create compound index on server_logs for efficient queries
            await self.db.server_logs.create_index([("server_name", 1), ("timestamp", -1)])
            logger.info("Created compound index on server_logs")

            # Create capped collection for logs (100MB max, auto-removes oldest)
            try:
                # Check if collection exists
                collections = await self.db.list_collection_names()
                if "server_logs" not in collections:
                    await self.db.create_collection(
                        "server_logs",
                        capped=True,
                        size=104857600  # 100MB
                    )
                    logger.info("Created capped collection for server_logs")
            except Exception as e:
                logger.warning(f"Could not create capped collection (may already exist): {e}")

            logger.info("Database initialization complete")
            return True

        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            return False

    def supports_change_streams(self) -> bool:
        """Check if MongoDB instance supports change streams."""
        return self._change_streams_supported is True

    # ==================== Schema Conversion Helpers ====================

    def _flatten_config_for_backend(self, nested_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert nested MongoDB format to flat backend format.

        MongoDB stores configs with nested mcp_config, but backend expects flat format
        for process spawning (command, args, env at root level).

        Args:
            nested_config: Config from MongoDB with mcp_config nested structure

        Returns:
            Flat config dict for backend consumption (command/args/env at root + metadata)
        """
        if not nested_config:
            return nested_config

        # Make a copy to avoid modifying original
        flat_config = dict(nested_config)

        # Extract mcp_config fields to root level for backend process spawning
        if "mcp_config" in flat_config:
            mcp = flat_config.pop("mcp_config")
            # Put command/args/env at root level (backend needs this for subprocess)
            if "command" in mcp:
                flat_config["command"] = mcp["command"]
            if "args" in mcp:
                flat_config["args"] = mcp["args"]
            if "env" in mcp:
                flat_config["env"] = mcp["env"]

        return flat_config

    def _nest_config_for_storage(self, flat_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert flat backend format to nested MongoDB format (PDF spec).

        Backend uses flat format (command, args, env at root), but we store
        in nested format (mcp_config: {command, args, env}) per PDF spec.

        Also adds new PDF fields with defaults.

        Args:
            flat_config: Config from backend with flat structure

        Returns:
            Nested config dict for MongoDB storage
        """
        if not flat_config:
            return flat_config

        # Make a copy to avoid modifying original
        nested_config = dict(flat_config)

        # Move command/args/env into mcp_config nested structure
        mcp_config = {}
        if "command" in nested_config:
            mcp_config["command"] = nested_config.pop("command")
        if "args" in nested_config:
            mcp_config["args"] = nested_config.pop("args")
        if "env" in nested_config:
            mcp_config["env"] = nested_config.pop("env")

        if mcp_config:
            nested_config["mcp_config"] = mcp_config

        # Add new PDF spec fields with defaults
        nested_config.setdefault("description", "")
        nested_config.setdefault("enabled", True)
        nested_config.setdefault("restart_window_sec", 300)
        nested_config.setdefault("tools", [])
        nested_config.setdefault("created_by", None)

        return nested_config

    # ==================== Server Configuration Operations ====================

    async def save_server_config(self, config: Dict[str, Any]) -> bool:
        """
        Save or update server configuration.

        Args:
            config: Server configuration dict with keys:
                - id (required): Unique server identifier (URL-friendly)
                - name (required): Human-readable display name
                - command, args, env (flat format from backend)
                - working_dir, install_path, restart_policy, max_restarts
                - description, enabled, tools, created_by (optional)

        Returns:
            True if saved successfully
        """
        try:
            # Convert flat format to nested MongoDB format (PDF spec)
            config = self._nest_config_for_storage(config)

            config["updated_at"] = datetime.utcnow()

            # Remove created_at from config to avoid conflict with $setOnInsert
            update_config = {k: v for k, v in config.items() if k != "created_at"}

            # Upsert: update if exists, insert if not
            result = await self.db.servers.update_one(
                {"id": config["id"]},
                {
                    "$set": update_config,
                    "$setOnInsert": {"created_at": datetime.utcnow()}
                },
                upsert=True
            )

            logger.debug(f"Saved server config: {config['id']} ({config.get('name', 'unknown')})")
            return True

        except DuplicateKeyError:
            logger.error(f"Server with id '{config['id']}' already exists")
            return False
        except Exception as e:
            logger.error(f"Error saving server config: {e}")
            return False

    async def get_server_config(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve server configuration by id.

        Args:
            id: Server identifier

        Returns:
            Server config dict in flat format (for backend compatibility)
        """
        try:
            config = await self.db.servers.find_one({"id": id}, {"_id": 0})  # Exclude MongoDB _id

            # Convert nested MongoDB format to flat format for backend
            if config:
                config = self._flatten_config_for_backend(config)

            return config
        except Exception as e:
            logger.error(f"Error retrieving server config: {e}")
            return None

    async def list_server_configs(self, filter_dict: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        List all server configurations.

        Args:
            filter_dict: Optional MongoDB filter

        Returns:
            List of server config dicts in flat format (for backend compatibility)
        """
        try:
            filter_dict = filter_dict or {}
            cursor = self.db.servers.find(filter_dict, {"_id": 0})  # Exclude MongoDB _id
            configs = await cursor.to_list(length=None)

            # Convert all configs from nested to flat format for backend
            configs = [self._flatten_config_for_backend(c) for c in configs]

            return configs
        except Exception as e:
            logger.error(f"Error listing server configs: {e}")
            return []

    async def delete_server_config(self, id: str) -> bool:
        """
        Delete server configuration.

        Args:
            id: Server identifier

        Returns:
            True if deleted successfully
        """
        try:
            result = await self.db.servers.delete_one({"id": id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting server config: {e}")
            return False

    # ==================== Server Instance Operations ====================

    async def save_instance_state(self, instance: Dict[str, Any]) -> bool:
        """
        Save server instance runtime state.

        Args:
            instance: Instance state dict with keys:
                - server_id (required): Server identifier
                - state, pid, start_time, stop_time, exit_code
                - restart_count, last_health_check, health_check_failures
                - host, port, last_error (PDF spec fields)
                - started_by (optional): User who started this instance

        Returns:
            True if saved successfully
        """
        try:
            # Add PDF spec fields with defaults
            instance.setdefault("host", "localhost")
            instance.setdefault("port", None)
            instance.setdefault("last_error", None)
            instance.setdefault("started_by", None)

            instance["updated_at"] = datetime.utcnow()

            # Support both server_id (new) and server_name (old) for backward compatibility
            server_key = instance.get("server_id", instance.get("server_name"))

            result = await self.db.server_instances.update_one(
                {"server_id": server_key},
                {"$set": instance},
                upsert=True
            )

            logger.debug(f"Saved instance state: {server_key}")
            return True

        except Exception as e:
            logger.error(f"Error saving instance state: {e}")
            return False

    async def get_instance_state(self, server_id: str) -> Optional[Dict[str, Any]]:
        """
        Get server instance runtime state.

        Args:
            server_id: Server identifier

        Returns:
            Instance state dict or None if not found
        """
        try:
            # Support both server_id (new) and server_name (old) for backward compatibility
            instance = await self.db.server_instances.find_one(
                {"$or": [{"server_id": server_id}, {"server_name": server_id}]},
                {"_id": 0}  # Exclude MongoDB _id
            )
            return instance
        except Exception as e:
            logger.error(f"Error retrieving instance state: {e}")
            return None

    async def list_instances_by_state(self, state: str) -> List[Dict[str, Any]]:
        """
        List all instances with given state.

        Args:
            state: State to filter by (e.g., 'running', 'stopped', 'failed')

        Returns:
            List of instance dicts
        """
        try:
            cursor = self.db.server_instances.find({"state": state})
            instances = await cursor.to_list(length=None)
            return instances
        except Exception as e:
            logger.error(f"Error listing instances by state: {e}")
            return []

    # ==================== Log Operations ====================

    async def save_log_entry(self, server_name: str, stream: str, content: str) -> bool:
        """
        Save a log entry with automatic buffering on failure.

        Args:
            server_name: Server name
            stream: 'stdout' or 'stderr'
            content: Log content

        Returns:
            True if saved successfully
        """
        log_entry = {
            "server_name": server_name,
            "timestamp": datetime.utcnow(),
            "stream": stream,
            "content": content
        }

        try:
            await self.db.server_logs.insert_one(log_entry)
            self._log_buffer.success_count += 1
            return True

        except Exception as e:
            # Buffer the failed log entry for retry
            self._log_buffer.add(log_entry)
            logger.error(f"Error saving log entry (buffered for retry): {e}")
            logger.debug(f"Buffer status: {self._log_buffer.get_stats()}")

            # Start retry task if not already running
            if self._retry_task is None or self._retry_task.done():
                self._retry_task = asyncio.create_task(self._retry_failed_logs())

            return False

    async def _retry_failed_logs(self):
        """Periodic retry of buffered log entries."""
        await asyncio.sleep(30)  # Wait 30 seconds before retry

        if self._log_buffer.size() == 0:
            return

        logger.info(f"Retrying {self._log_buffer.size()} buffered log entries...")

        entries = self._log_buffer.get_all()
        retry_failed = []

        for entry in entries:
            try:
                await self.db.server_logs.insert_one(entry)
                self._log_buffer.success_count += 1
            except Exception as e:
                logger.warning(f"Retry failed for log entry: {e}")
                retry_failed.append(entry)

        # Re-buffer entries that still failed
        for entry in retry_failed:
            self._log_buffer.add(entry)

        success_count = len(entries) - len(retry_failed)
        logger.info(f"Retry complete: {success_count}/{len(entries)} succeeded")

        # Schedule another retry if there are still failures
        if len(retry_failed) > 0:
            self._retry_task = asyncio.create_task(self._retry_failed_logs())

    def get_log_stats(self) -> Dict[str, Any]:
        """Get logging statistics including buffer status."""
        stats = self._log_buffer.get_stats()
        total = stats["success_total"] + stats["failed_total"]
        success_rate = (stats["success_total"] / total * 100) if total > 0 else 100.0

        return {
            **stats,
            "success_rate": round(success_rate, 2)
        }

    async def get_logs(
        self,
        server_name: str,
        lines: int = 100,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve logs for a server.

        Args:
            server_name: Server name
            lines: Number of recent lines to retrieve
            since: Optional timestamp to filter logs after

        Returns:
            List of log entry dicts
        """
        try:
            filter_dict = {"server_name": server_name}

            if since:
                filter_dict["timestamp"] = {"$gte": since}

            # Sort by timestamp descending, limit to N lines
            cursor = self.db.server_logs.find(filter_dict).sort("timestamp", -1).limit(lines)
            logs = await cursor.to_list(length=lines)

            # Reverse to get chronological order
            logs.reverse()

            return logs

        except Exception as e:
            logger.error(f"Error retrieving logs: {e}")
            return []

    async def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("Closed MongoDB connection")
