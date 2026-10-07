# FluidMCP Onboarding Tutorials

Interactive HTML tutorials and code flow diagrams for learning FluidMCP.

## ✅ Completed Deliverables

### Tutorials (HTML) - Interactive Browser-Based Learning

1. **[getting-started-quickstart-tutorial.html](tutorials/getting-started-quickstart-tutorial.html)** ✅
   - 7 lessons: Installation → Directory Structure → Hello World → Key Concepts → Use Cases → Next Steps
   - Full-featured with progress tracking

2. **[mcp-server-management-feature-tutorial.html](tutorials/mcp-server-management-feature-tutorial.html)** ✅
   - 4 lessons: Introduction → Configuration → REST API → GitHub Integration
   - Covers server lifecycle, direct config, GitHub clone, security allowlist

3. **[llm-models-feature-tutorial.html](tutorials/llm-models-feature-tutorial.html)** ✅
   - 4 lessons: Introduction → Configuration → REST API → Error Recovery
   - Covers vLLM, Ollama, Replicate comparison and setup

### Code Flow Diagrams (Markdown) - ASCII Architecture Diagrams

1. **[data-flow-diagram.md](code-flow/data-flow-diagram.md)** ✅
   - Traces data from HTTP request → validation → MongoDB → process spawn → response
   - 9 phases with swim-lane diagrams
   - Shows flat ↔ nested config transformations

2. **[api-request-sequence-diagram.md](code-flow/api-request-sequence-diagram.md)** ✅
   - 17-step sequence diagram with actors (Client, API, ServerManager, DB, Subprocess)
   - Includes error paths and transport-specific flows
   - Covers auth, validation, initialization

3. **[server-lifecycle-key-flow-diagram.md](code-flow/server-lifecycle-key-flow-diagram.md)** ✅
   - High-level 6-step flow: Request → Validate → Persist → Spawn → Initialize → Ready
   - Includes state transitions and time estimates
   - Entry point for understanding the system

## 📖 How to Use

### Interactive Tutorials
Open any HTML file in your browser to start the interactive learning experience:
```bash
# macOS
open tutorials/getting-started-quickstart-tutorial.html

# Linux
xdg-open tutorials/getting-started-quickstart-tutorial.html

# Windows
start tutorials/getting-started-quickstart-tutorial.html
```

Features:
- ✅ Interactive navigation with sidebar
- ✅ Progress tracking (stored in localStorage)
- ✅ Copy buttons for all code blocks
- ✅ Responsive design (mobile-friendly)
- ✅ Visual diagrams and tables

### Code Flow Diagrams
View markdown files directly in GitHub or any markdown viewer. These use ASCII art for maximum compatibility.

## 🎯 Learning Path

**For New Users:**
1. Start with `getting-started-quickstart-tutorial.html`
2. Then `mcp-server-management-feature-tutorial.html`
3. Then `llm-models-feature-tutorial.html`

**For Developers:**
1. Read `server-lifecycle-key-flow-diagram.md` for high-level overview
2. Deep dive with `api-request-sequence-diagram.md`
3. Understand data transformations with `data-flow-diagram.md`

## 📁 File Structure

```
onboarding-tutorials/
├── tutorials/
│   ├── getting-started-quickstart-tutorial.html      (7 lessons)
│   ├── mcp-server-management-feature-tutorial.html   (4 lessons)
│   └── llm-models-feature-tutorial.html              (4 lessons)
├── code-flow/
│   ├── data-flow-diagram.md
│   ├── api-request-sequence-diagram.md
│   └── server-lifecycle-key-flow-diagram.md
└── README.md (this file)
```

## 🔍 Related Resources

- **Full documentation:** [`/CLAUDE.md`](../../CLAUDE.md)
- **Onboarding docs:** [`/fluidmcp_onboarding/`](../fluidmcp_onboarding/)
- **Examples:** [`/examples/`](../../examples/)
- **Working PR with tutorials:** [#510](https://github.com/Fluid-AI/fluidmcp/pull/510)

## 💡 Notes on Tutorial Design

The tutorials use a simplified JavaScript template literal syntax:

```javascript
const lessons = [
  {
    content:`<p>HTML here</p>`  // Regular backtick for lesson content
  }
];

// In the forEach loop, escape ${} for template literals:
ni.innerHTML=`<div>\${variable}</div>`;  // Escaped \${} 
```

This pattern ensures JavaScript template variables render correctly instead of showing as literal `${text}`.
