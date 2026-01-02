# FluidMCP Documentation Index

Welcome to FluidMCP! This index helps you find the right documentation for your needs.

---

## 🚀 Getting Started

**New to FluidMCP?** Start here:

| Document | Time | Purpose |
|----------|------|---------|
| [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) | 2 min | Fastest way to get running |
| [HOW_TO_RUN.md](HOW_TO_RUN.md) | 10 min | Complete guide to running FluidMCP |
| [CLAUDE.md](CLAUDE.md) | 15 min | Project overview and architecture |

---

## 🔐 OAuth Authentication

**Want to add secure authentication?**

| Document | Time | Audience |
|----------|------|----------|
| [README_OAUTH.md](README_OAUTH.md) | 5 min | Quick overview with badges |
| [OAUTH_SETUP_QUICK_START.md](OAUTH_SETUP_QUICK_START.md) | 5 min | Step-by-step setup guide |
| [OAUTH_AUTHENTICATION_GUIDE.md](OAUTH_AUTHENTICATION_GUIDE.md) | 30 min | Complete guide (50+ pages) |
| [OAUTH_PRESENTATION.md](OAUTH_PRESENTATION.md) | 30 min | Presentation slides |

---

## 📤 Sharing Your Server

**Want others to access your FluidMCP server?**

| Document | Purpose |
|----------|---------|
| [SETUP_INSTRUCTIONS_FOR_SHARING.md](SETUP_INSTRUCTIONS_FOR_SHARING.md) | Guide for sharing with external users |
| [HOW_TO_RUN.md](HOW_TO_RUN.md) | Running in different environments |

---

## 🔧 Technical Documentation

**For developers and technical teams:**

| Document | Purpose |
|----------|---------|
| [REGISTRY_PACKAGE_AUTH.md](REGISTRY_PACKAGE_AUTH.md) | Securing registry packages with OAuth |
| [AUTH0_WILDCARD_SETUP.md](AUTH0_WILDCARD_SETUP.md) | Wildcard URL configuration |
| [../CLAUDE.md](../CLAUDE.md) | Architecture and development guide |

---

## 🛠️ Tools & Utilities

**Helper scripts for working with FluidMCP:**

| Script | Purpose |
|--------|---------|
| `print-auth0-urls.py` | Display OAuth URLs for your environment |
| `test-dynamic-oauth.py` | Run comprehensive test suite |

**Usage:**
```bash
# Get your OAuth URLs
python print-auth0-urls.py

# Run tests
python test-dynamic-oauth.py
```

---

## 📋 Quick Command Reference

### Basic Usage

```bash
# Run with example config
fluidmcp run examples/sample-config.json --file --start-server

# Run all installed packages
fluidmcp run all --start-server

# Run with OAuth
fluidmcp run all --start-server --auth0
```

### Docker

```bash
# Run without OAuth
docker run -p 8099:8099 fluidmcp

# Run with OAuth
docker run -p 8099:8099 --env-file .env fluidmcp
```

### Helper Commands

```bash
# List packages
fluidmcp list

# Get help
fluidmcp --help

# Get OAuth URLs
python print-auth0-urls.py
```

---

## 🎯 By Use Case

### I want to...

#### Test FluidMCP locally (5 minutes)
1. Read: [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md)
2. Run: `fluidmcp run examples/sample-config.json --file --start-server`
3. Access: http://localhost:8099/docs

#### Add OAuth authentication (15 minutes)
1. Read: [OAUTH_SETUP_QUICK_START.md](OAUTH_SETUP_QUICK_START.md)
2. Run: `python print-auth0-urls.py`
3. Set up Auth0 account
4. Run: `fluidmcp run all --start-server --auth0`

#### Deploy to production (30 minutes)
1. Read: [OAUTH_AUTHENTICATION_GUIDE.md](OAUTH_AUTHENTICATION_GUIDE.md) - Production Deployment section
2. Choose deployment method (Docker, Kubernetes, etc.)
3. Configure environment variables
4. Deploy!

#### Share with my team (10 minutes)
1. Read: [SETUP_INSTRUCTIONS_FOR_SHARING.md](SETUP_INSTRUCTIONS_FOR_SHARING.md)
2. Set up OAuth
3. Make port public (if using Codespaces)
4. Share URL with team

#### Understand the architecture (30 minutes)
1. Read: [CLAUDE.md](CLAUDE.md) - Architecture section
2. Read: [DYNAMIC_OAUTH_CHANGES.md](DYNAMIC_OAUTH_CHANGES.md) - How It Works
3. Explore: `fluidai_mcp/` directory

#### Present to stakeholders (1 hour)
1. Read: [OAUTH_PRESENTATION.md](OAUTH_PRESENTATION.md)
2. Review: [OAUTH_AUTHENTICATION_GUIDE.md](OAUTH_AUTHENTICATION_GUIDE.md) - Results & Impact
3. Prepare demo using [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md)

---

## 📚 Examples

All examples are in the `examples/` directory:

```
examples/
├── sample-config.json              # Basic config with filesystem & memory
├── sample-metadata.json            # Package metadata example
├── sample-config-with-api-keys.json  # Config with API keys
└── README.md                       # Testing guide
```

---

## 🐛 Troubleshooting

Common issues and solutions:

| Issue | Solution |
|-------|----------|
| Port in use | [HOW_TO_RUN.md](HOW_TO_RUN.md#issue-1-port-already-in-use) |
| OAuth not working | [OAUTH_SETUP_QUICK_START.md](OAUTH_SETUP_QUICK_START.md#troubleshooting) |
| Codespaces port not accessible | [SETUP_INSTRUCTIONS_FOR_SHARING.md](SETUP_INSTRUCTIONS_FOR_SHARING.md#port-not-accessible) |
| Callback URL mismatch | [HOW_TO_RUN.md](HOW_TO_RUN.md#issue-4-callback-url-mismatch) |

---

## 🎓 Learning Path

### Beginner
1. ⏱️ 2 min: [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md)
2. ⏱️ 10 min: [HOW_TO_RUN.md](HOW_TO_RUN.md) - Basic Usage
3. ⏱️ 15 min: Try examples in `examples/` directory

### Intermediate
1. ⏱️ 15 min: [OAUTH_SETUP_QUICK_START.md](OAUTH_SETUP_QUICK_START.md)
2. ⏱️ 30 min: [HOW_TO_RUN.md](HOW_TO_RUN.md) - Docker Deployment
3. ⏱️ 20 min: [SETUP_INSTRUCTIONS_FOR_SHARING.md](SETUP_INSTRUCTIONS_FOR_SHARING.md)

### Advanced
1. ⏱️ 60 min: [OAUTH_AUTHENTICATION_GUIDE.md](OAUTH_AUTHENTICATION_GUIDE.md)
2. ⏱️ 30 min: [DYNAMIC_OAUTH_CHANGES.md](DYNAMIC_OAUTH_CHANGES.md)
3. ⏱️ 45 min: [HOW_TO_RUN.md](HOW_TO_RUN.md) - Production Deployment

---

## 📊 Document Summary

| Document | Pages | Time | Type |
|----------|-------|------|------|
| [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) | 2 | 2 min | Quick Reference |
| [HOW_TO_RUN.md](HOW_TO_RUN.md) | 25 | 30 min | How-To Guide |
| [README_OAUTH.md](README_OAUTH.md) | 12 | 15 min | Overview |
| [OAUTH_SETUP_QUICK_START.md](OAUTH_SETUP_QUICK_START.md) | 8 | 10 min | Tutorial |
| [OAUTH_AUTHENTICATION_GUIDE.md](OAUTH_AUTHENTICATION_GUIDE.md) | 50+ | 2 hours | Complete Guide |
| [OAUTH_PRESENTATION.md](OAUTH_PRESENTATION.md) | 40+ | 1 hour | Presentation |
| [SETUP_INSTRUCTIONS_FOR_SHARING.md](SETUP_INSTRUCTIONS_FOR_SHARING.md) | 10 | 15 min | Tutorial |
| [DYNAMIC_OAUTH_CHANGES.md](DYNAMIC_OAUTH_CHANGES.md) | 15 | 30 min | Technical Spec |
| [CLAUDE.md](CLAUDE.md) | 10 | 20 min | Reference |

---

## 🎯 Quick Links

### Most Used
- ⚡ [Start in 2 minutes](QUICK_START_GUIDE.md)
- 🔐 [Add OAuth in 5 minutes](OAUTH_SETUP_QUICK_START.md)
- 🚀 [Deploy to production](OAUTH_AUTHENTICATION_GUIDE.md#production-deployment)

### For Different Audiences
- 👨‍💻 **Developers**: [HOW_TO_RUN.md](HOW_TO_RUN.md), [DYNAMIC_OAUTH_CHANGES.md](DYNAMIC_OAUTH_CHANGES.md)
- 👔 **Managers**: [OAUTH_PRESENTATION.md](OAUTH_PRESENTATION.md), [README_OAUTH.md](README_OAUTH.md)
- 👥 **End Users**: [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md), [OAUTH_SETUP_QUICK_START.md](OAUTH_SETUP_QUICK_START.md)
- 🏢 **Enterprise**: [OAUTH_AUTHENTICATION_GUIDE.md](OAUTH_AUTHENTICATION_GUIDE.md)

---

## 💡 Tips

- **Start simple**: Run without OAuth first to understand basics
- **Use helper scripts**: `print-auth0-urls.py` shows your URLs
- **Check examples**: The `examples/` directory has working configs
- **Run tests**: `python test-dynamic-oauth.py` verifies everything works
- **Read troubleshooting**: Common issues are already documented

---

## 🆘 Need Help?

1. **Search this index** - Find the right document
2. **Check examples** - Working code in `examples/`
3. **Run tests** - `python test-dynamic-oauth.py`
4. **Read troubleshooting** - Each guide has a troubleshooting section
5. **Check GitHub issues** - Someone might have had the same problem

---

## 📝 Contributing

Want to improve the documentation?

1. Read the relevant guide
2. Make your changes
3. Test with `python test-dynamic-oauth.py`
4. Submit a pull request

---

## ✨ Features by Version

### v2.0.0 (Current)
- ✅ OAuth 2.0 authentication
- ✅ Automatic environment detection
- ✅ Dynamic URL generation
- ✅ Multi-provider support
- ✅ Production-ready deployment

### v1.0.0
- Basic MCP server orchestration
- Configuration file support
- Package registry integration

---

**Last Updated**: December 31, 2025
**Current Version**: 2.0.0
**Status**: ✅ Production Ready

---

**Start here**: [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) 🚀
