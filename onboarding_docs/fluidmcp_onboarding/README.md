# FluidMCP Onboarding Documentation

Welcome to FluidMCP! This folder contains comprehensive onboarding materials for new developers.

---

## 📚 Documentation Index

### 1. [TECHNICAL_ONBOARDING.md](TECHNICAL_ONBOARDING.md)
**Primary onboarding document** - Start here!

Comprehensive technical guide covering:
- High-level architecture (frontend, gateway, MCP servers, MongoDB)
- Backend deep dive (entry points, startup flow, server management)
- MCP server model (definition, tools, communication protocol)
- Frontend structure (pages, components, state management)
- End-to-end flows (tool execution, chat, logs)
- Key features (chat system, dynamic forms, tool history)
- Important files and folders
- Developer workflow (setup, testing, deployment)

**Audience:** New developers joining the project  
**Reading Time:** 30-40 minutes  
**Format:** Structured sections with code examples and diagrams

---

### 2. [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
**Quick reference guide** - When you need fast answers

Concise cheat sheet with:
- Common commands (CLI, API, testing)
- File locations map
- Configuration format examples
- Debugging tips and common issues
- Port usage reference
- Environment variables
- Architecture diagrams (simplified)

**Audience:** Developers who already understand basics  
**Reading Time:** 5-10 minutes  
**Format:** Tables, code snippets, quick lookups

---

### 3. [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)
**Visual architecture reference**

ASCII diagrams showing:
- System overview (components and interactions)
- Server startup sequence
- MCP server lifecycle state machine
- Tool execution data flow
- LLM chat flow
- Configuration resolution flow
- JSON-RPC protocol examples
- Frontend state management hierarchy
- Security layers
- Monitoring architecture

**Audience:** Visual learners, architecture reviewers  
**Reading Time:** 15-20 minutes  
**Format:** ASCII diagrams with annotations

---

## 🎯 Recommended Reading Path

### For Complete Beginners

1. **Start:** Read [TECHNICAL_ONBOARDING.md](TECHNICAL_ONBOARDING.md) sections 1-2 (Overview & Architecture)
2. **Hands-On:** Run sample config: `fmcp run examples/sample-config.json --file --start-server`
3. **Explore UI:** Open http://localhost:8099, navigate pages
4. **Deep Dive:** Read [TECHNICAL_ONBOARDING.md](TECHNICAL_ONBOARDING.md) sections 3-6 (Backend, MCP, Frontend, Flows)
5. **Reference:** Bookmark [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for daily use
6. **Visual:** Review [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) for mental models

**Total Time:** 2-3 hours for complete onboarding

---

### For Experienced Developers

1. **Quick Start:** Read [QUICK_REFERENCE.md](QUICK_REFERENCE.md) (5 min)
2. **Run Sample:** `fmcp run examples/sample-config.json --file --start-server` (2 min)
3. **Explore Code:** Browse key files listed in Quick Reference (30 min)
4. **Reference Diagrams:** Use [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) as needed
5. **Deep Dive:** Read relevant sections of [TECHNICAL_ONBOARDING.md](TECHNICAL_ONBOARDING.md) as needed

**Total Time:** 1 hour to be productive

---

### For Frontend Developers

1. Read [TECHNICAL_ONBOARDING.md](TECHNICAL_ONBOARDING.md) section 5 (Frontend)
2. Read [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - "Frontend Development" section
3. Start backend: `fmcp serve --port 8099`
4. Start frontend: `cd fluidmcp/frontend && npm run dev`
5. Browse code:
   - [fluidmcp/frontend/src/App.tsx](../fluidmcp/frontend/src/App.tsx) - Routes
   - [fluidmcp/frontend/src/services/api.ts](../fluidmcp/frontend/src/services/api.ts) - API client
   - [fluidmcp/frontend/src/hooks/](../fluidmcp/frontend/src/hooks/) - Custom hooks
   - [fluidmcp/frontend/src/pages/](../fluidmcp/frontend/src/pages/) - Pages

**Focus:** React components, TypeScript types, API integration

---

### For Backend Developers

1. Read [TECHNICAL_ONBOARDING.md](TECHNICAL_ONBOARDING.md) sections 3-4 (Backend & MCP)
2. Read [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) - Protocol diagrams
3. Browse code:
   - [fluidmcp/cli/server.py](../fluidmcp/cli/server.py) - FastAPI entry
   - [fluidmcp/cli/api/management.py](../fluidmcp/cli/api/management.py) - API routes
   - [fluidmcp/cli/services/package_launcher.py](../fluidmcp/cli/services/package_launcher.py) - MCP launcher
   - [fluidmcp/cli/services/server_manager.py](../fluidmcp/cli/services/server_manager.py) - Lifecycle
4. Run tests: `pytest tests/test_server_manager.py -v`

**Focus:** FastAPI routes, MCP protocol, subprocess management, MongoDB

---

## 🔗 Additional Resources

### Core Documentation

Located in [../docs/](../docs/):
- [RAILWAY_DEPLOYMENT.md](../docs/RAILWAY_DEPLOYMENT.md) - Production deployment guide
- [REPLICATE_SUPPORT.md](../docs/REPLICATE_SUPPORT.md) - Cloud inference documentation
- [VLLM_ERROR_RECOVERY.md](../docs/VLLM_ERROR_RECOVERY.md) - Error handling for LLMs
- [FUNCTION_CALLING.md](../docs/FUNCTION_CALLING.md) - Function calling support
- [TROUBLESHOOTING.md](../docs/TROUBLESHOOTING.md) - Common issues and solutions
- [GITHUB_CLONE.md](../docs/GITHUB_CLONE.md) - GitHub integration guide

### Example Configurations

Located in [../examples/](../examples/):
- [sample-config.json](../examples/sample-config.json) - Basic MCP servers
- [replicate-inference.json](../examples/replicate-inference.json) - Cloud inference
- [vllm-with-error-recovery.json](../examples/vllm-with-error-recovery.json) - Local inference
- [vllm-omni-complete.json](../examples/vllm-omni-complete.json) - Multimodal setup
- [README.md](../examples/README.md) - Example testing guide

### Test Suite

Located in [../tests/](../tests/):
- 40+ test files covering all major features
- Unit tests, integration tests, security tests
- Manual test scripts in `tests/manual/`
- Run: `pytest` or `pytest tests/test_*.py`

### Architecture Guides

Located in [../Skills/](../Skills/):
- [code_flow/](../Skills/code_flow/) - Detailed code flow analysis
- [tutorial/](../Skills/tutorial/) - Concept and hands-on tutorials

---

## 🎓 Learning Objectives

After completing the onboarding materials, you should be able to:

✅ Understand the overall architecture (frontend, gateway, MCP servers)  
✅ Explain how MCP servers communicate via JSON-RPC over stdio  
✅ Run FluidMCP locally with sample configurations  
✅ Add a new MCP server via configuration or GitHub  
✅ Execute tools via the web UI or REST API  
✅ Navigate the frontend codebase and add new pages  
✅ Debug common issues using logs and metrics  
✅ Deploy FluidMCP to Railway or Docker  
✅ Write tests for new features  
✅ Understand security layers (CORS, auth, rate limiting)

---

## 🚀 First Tasks for New Developers

### Day 1: Setup & Exploration

1. Clone repository and install dependencies
2. Run sample config: `fmcp run examples/sample-config.json --file --start-server`
3. Open UI: http://localhost:8099
4. Navigate all pages (Dashboard, Tool Runner, LLM Playground, etc.)
5. Execute a tool via UI (e.g., filesystem → list_directory)
6. View logs in Server Details page
7. Run tests: `pytest`

### Day 2: Code Understanding

1. Read [TECHNICAL_ONBOARDING.md](TECHNICAL_ONBOARDING.md) completely
2. Browse key backend files:
   - [fluidmcp/cli/cli.py](../fluidmcp/cli/cli.py)
   - [fluidmcp/cli/server.py](../fluidmcp/cli/server.py)
   - [fluidmcp/cli/services/package_launcher.py](../fluidmcp/cli/services/package_launcher.py)
3. Browse key frontend files:
   - [fluidmcp/frontend/src/App.tsx](../fluidmcp/frontend/src/App.tsx)
   - [fluidmcp/frontend/src/services/api.ts](../fluidmcp/frontend/src/services/api.ts)
   - [fluidmcp/frontend/src/pages/Dashboard.tsx](../fluidmcp/frontend/src/pages/Dashboard.tsx)
4. Read test files to understand expected behavior

### Day 3: First Contribution

1. Pick a "good first issue" from GitHub
2. Create feature branch
3. Make changes (backend or frontend)
4. Write tests
5. Test manually with sample configs
6. Submit pull request

---

## 🤝 Getting Help

### Documentation

1. Check this onboarding folder first
2. Read [../docs/TROUBLESHOOTING.md](../docs/TROUBLESHOOTING.md) for common issues
3. Review [../CLAUDE.md](../CLAUDE.md) for quick command reference
4. Browse [../examples/README.md](../examples/README.md) for configuration examples

### Code Exploration

1. Use Swagger UI: http://localhost:8099/docs
2. Read test files for usage examples
3. Check inline code comments
4. Review GitHub issues and pull requests

### Community

- **GitHub Issues:** Report bugs or ask questions
- **Pull Requests:** Contribute code improvements
- **Discussions:** Ask for help or share ideas

---

## 📝 Document Maintenance

These onboarding documents should be updated when:

- Major architectural changes occur
- New features are added that change core workflows
- API endpoints are added/modified/removed
- Frontend pages or navigation changes
- Configuration formats change
- Deployment procedures change

**Last Updated:** March 24, 2026  
**Maintainer:** FluidMCP Development Team

---

**Ready to start?** Open [TECHNICAL_ONBOARDING.md](TECHNICAL_ONBOARDING.md) and begin your journey! 🚀
