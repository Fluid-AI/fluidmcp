Here is the raw Markdown code. You can copy this block and paste it directly into your `README.md` file.

````markdown
# 📄 MCP Document Converter Server

A standalone **Model Context Protocol (MCP)** server designed for high-fidelity document conversion. It runs locally and handles complex document layouts (tables, code blocks, multi-column text) flawlessly without relying on external APIs.

## 🚀 Features

- **PDF ↔ Markdown**: Uses `pymupdf4llm` to extract content while preserving tables and layout structure.
- **DOCX ↔ Markdown**: Uses `Pandoc` for robust semantic structure conversion.
- **Professional PDF Generation**: Uses `WeasyPrint` with CSS styling to create clean, readable PDFs from Markdown.
- **Automated Workflow**: Smartly manages files using dedicated `Input/` and `Output/` directories.
- **Standalone**: No API keys required. Runs entirely on your local machine or container.

## 📂 Directory Structure

The server automatically creates the necessary folders when you run it:

```text
Custom_servers/doc-converter/
├── server.py           # Main server logic
├── requirements.txt    # Python dependencies
├── metadata.json       # FluidMCP configuration
├── Input/              # Drop your source files here
└── Output/             # Generated files appear here
````

## 🛠️ Prerequisites & Installation

### 1\. System Dependencies

This server relies on system-level tools for document processing. You must install these first:

**Linux (Debian/Ubuntu/Codespaces):**

```bash
sudo apt-get update
sudo apt-get install -y pandoc libpango-1.0-0 libpangoft2-1.0-0
```

**macOS (Homebrew):**

```bash
brew install pandoc weasyprint
```

### 2\. Python Dependencies

Install the required Python libraries:

```bash
pip install -r requirements.txt
```

## 🏃‍♂️ How to Run

You can run this server using the **FluidMCP CLI**.

1.  Navigate to the root of your project (where `fluidmcp` is installed).
2.  Run the server configuration:

<!-- end list -->

```bash
fluidmcp run custom_servers/doc-converter/metadata.json --file --start-server
```

> **Note:** Adjust the path to `metadata.json` if your folder structure is different.

## 📖 Usage Guide

Once the server is running (usually at `http://localhost:8099`), follow these steps:

### 1\. Prepare your File

Place the file you want to convert (e.g., `quarterly_report.pdf`) into the **`Input/`** folder inside the server directory.

### 2\. Call the Tool

Use an MCP Client (like Claude Desktop) or the built-in **Swagger UI** (`http://localhost:8099/docs`) to trigger a conversion.

**Example: Convert PDF to Markdown**

```json
{
  "name": "pdf_to_markdown",
  "arguments": {
    "input_path": "quarterly_report.pdf",
    "output_path": "report_extracted.md"
  }
}
```

**Example: Convert Markdown to PDF**

```json
{
  "name": "markdown_to_pdf",
  "arguments": {
    "input_path": "draft.md",
    "output_path": "final_report.pdf"
  }
}
```

### 3\. Retrieve Output

Check the **`Output/`** folder. Your converted file will be waiting there.

## 🔧 Troubleshooting

  * **Error: `No pandoc was found`**:
      * Ensure you ran the system dependency installation step (`sudo apt-get install pandoc`).
  * **Error: `File not found in Input directory`**:
      * Make sure you copied your source file into the `Input` folder *before* running the command.
      * The tool looks for filenames relative to the `Input` folder automatically.
