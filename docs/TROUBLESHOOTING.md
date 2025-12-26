FluidMCP Troubleshooting Guide

This document lists common errors encountered while using the FluidMCP CLI, explains why they occur, and provides practical steps to resolve them.

FluidMCP errors generally fall into five categories:
    1. Configuration resolution errors
    2. Server startup failures
    3. Port conflicts
    4. GitHub authentication issues
    5. Missing system dependencies

Understanding these failure modes will help users debug issues quickly and confidently

1. Common Error Messages and Their Solutions

    ERROR: Package not found: <package>

        Cause
        - The package is not installed
        - The package name or version is incorrect
        - The installation directory is missing or corrupted

        How to Fix
        - List installed packages:
            fluidmcp list

        - Verify the package name and version
        - Reinstall the package:
            fluidmcp install <author/package@version>

        Check the installation directory (MCP_INSTALLATION_DIR)


    ERROR: No installations found.

        Cause
        - No MCP packages have been installed yet
        - The installation directory does not exist

        How to Fix
        - Install at least one package:
        - fluidmcp install <package>

        Ensure the installation directory is accessible


    ERROR: No metadata.json found at <path>

        Cause
        - The package installation is incomplete
        - metadata.json was deleted or corrupted

        How to Fix
        - Reinstall the package
        - Verify the package directory structure


    ERROR: Invalid configuration in <file>

        Cause
            - The JSON file is malformed
            - Required fields (such as mcpServers) are missing
            - The configuration schema is incorrect

        How to Fix
            - Validate the JSON syntax (use a JSON linter)
            - Compare the file against a known valid sample
            - Ensure mcpServers is present and correctly structured


    Warning: Unknown format for server '<name>'

        Cause
        - A server entry does not match any supported configuration format
        - The server definition is neither a package string, GitHub config, nor direct command config

        How to Fix
        - Verify the server entry format
        - Ensure it follows one of the supported configuration styles
        - Warnings do not always stop execution, but affected servers may be skipped.
        

2. Debugging Server Startup Failures       

    ERROR: Failed to launch MCP server

        Cause
        - Invalid or missing metadata
        - Runtime errors inside the server code
        - Missing dependencies required by the server

        How to Debug
        - Inspect metadata.json for the server
        - Try running the server command manually
        - Check logs printed during startup
        - Verify required dependencies are installed


    ERROR: Error running servers

        Cause
        - Configuration resolution failed
        - One or more servers failed during startup
        - Runtime exceptions occurred while launching servers

        How to Fix
        - Identify whether the error is:
            - Configuration-related (file, package, S3)
            - Runtime-related (server process, dependencies)
        - Fix the root cause and rerun:
            fluidmcp run <package>


3. Port Conflict Resolution

    ERROR: Port <port> is already in use

        Cause
        - Another process is already using the required port
        - A previously launched server is still running

        How FluidMCP Handles This
        - Detects the conflict automatically
        - Prompts user to kill the existing process
        - Supports forced reload with a flag

        How to Fix
        - Use force reload:
            fluidmcp run <package> --force-reload

        - Or manually stop the process using the port

        Default Ports
        - Client FastAPI server: 8090 (GitHub command)
        - SuperGateway: 8111 (run command)


4. GitHub Authentication Issues

    ERROR: GitHub token missing for server '<name>'

        Cause
        - No GitHub token provided
        - Required environment variables are missing

        How to Fix
        - Provide a GitHub Personal Access Token (PAT) using one of:
            - CLI flag:
                --github-token <TOKEN>

        - Environment variables:
            - FMCP_GITHUB_TOKEN
            - GITHUB_TOKEN

        Token Requirements
        - Must have read access to the repository
        - Required for private repositories


    ERROR: Error preparing GitHub server '<name>'

        Cause
        - Repository clone failure
        - Invalid repository URL
        - Metadata extraction failed
        - Network or permission issues

        How to Fix
        - Verify repository URL and branch
        - Ensure the token has correct permissions
        - Check network connectivity
        - Retry after fixing the configuration


5. Missing Dependencies (Implicit Errors)

    FluidMCP does not explicitly check for system dependencies.
    Failures appear as runtime or OS-level errors.

    Common Symptoms
        [Errno 2] No such file or directory: 'node'
        command not found

    Required Dependencies
    - Node.js
    - npm
    - Python
    - uv

    How to Fix
    - Install the missing dependency
    - Ensure it is available in your system PATH
    - Restart your terminal after installation


6. S3 Configuration and Sync Issues

    ERROR: Invalid configuration from S3

        Cause
        - The downloaded S3 file is invalid
        - The file does not follow the metadata schema

        How to Fix
        - Verify the contents of the S3 file
        - Ensure it includes a valid mcpServers section


    ERROR: Failed to load s3_metadata_all.json

        Cause
        - Corrupted or missing S3 metadata file
        - Download or permission failure

        How to Fix
        - Check AWS credentials:
            S3_BUCKET_NAME
            S3_ACCESS_KEY
            S3_SECRET_KEY
            S3_REGION

        - Ensure the bucket and object exist
        - Re-run in master mode to regenerate metadata

7. Understanding Warnings vs Errors

    Warnings
    - Printed using print(...)
    - Execution continues
    - Affected servers may be skipped

    Errors
    - Trigger sys.exit(1)
    - Stop execution immediately
    I- f execution stops, always check the first error message printed — it usually indicates the root cause.

8. General Debugging Checklist

    If something goes wrong:

    1. Identify the command used (install, run, github, etc.)

    2. Read the first error message carefully

    3. Determine the source:
        Package
        File
        GitHub
        S3

    4. Verify:
        metadata.json
        Environment variables
        Installed dependencies

    5. Retry after fixing the issue


9. Final Note
    Most FluidMCP issues fall into configuration errors or missing prerequisites.
    Once those are resolved, server startup is typically smooth.