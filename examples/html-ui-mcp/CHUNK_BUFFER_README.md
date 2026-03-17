# HTML Chunk Buffer Middleware

Middleware that buffers HTML token fragments and emits complete, renderable tags with automatic noise filtering.

## Problem

Your agent streams HTML token-by-token with noise tokens:
```json
{"v": "<!", "i": ""}
{"v": "DOCTYPE", "i": ""}
{"v": " html", "i": ""}
{"v": "<!-- ▶ BUILDING: styles - reset -->", "i": ""}  ← NOISE
{"v": "   ", "i": ""}  ← NOISE (whitespace)
{"v": ">", "i": ""}
```

This breaks progressive rendering because the HTML is fragmented and contains noise.

## Solution

**Filters noise** and **buffers tokens** until complete tags are formed:
```json
{"v": "<!DOCTYPE html>", "i": ""}
```

## Features

✅ **Noise Filtering**: Automatically removes HTML comments (`<!-- -->`) and whitespace-only tokens  
✅ **Complete Tags**: Buffers from `<` to `>` for complete tags  
✅ **Style Blocks**: Buffers entire `<style>...</style>` as one chunk  
✅ **Text Pass-Through**: Text between tags flushes immediately  
✅ **Format Preservation**: Maintains `$||$` delimiter and JSON structure  
✅ **Agent Info**: Preserves agent metadata fields

## Usage

### As Command-Line Tool

```bash
# Pipe your streaming data through the buffer
cat your_stream.txt | python3 html_chunk_buffer.py

# Or redirect from file
python3 html_chunk_buffer.py < your_stream.txt
```

### As Python Module

```python
from html_chunk_buffer import process_stream

# Your incoming stream chunks
input_stream = [
    '{"agent": "Agent 1", "agent_section": "answer", "v": "<!", "i": ""}$||$',
    '{"v": "DOCTYPE", "i": ""}$||$',
    '{"v": " html", "i": ""}$||$',
    '{"v": ">\\n", "i": ""}$||$',
    # ... more chunks
]

# Process with buffering
for buffered_chunk in process_stream(input_stream):
    print(buffered_chunk, end="")
```

### Integration Example

If you have a streaming handler that receives chunks:

```python
from html_chunk_buffer import process_stream

def your_streaming_handler(raw_stream):
    """Your existing streaming handler"""
    
    # Wrap the raw stream with buffering
    buffered_stream = process_stream(raw_stream)
    
    # Forward buffered chunks to your UI
    for chunk in buffered_stream:
        send_to_ui(chunk)
```

## Input Format

Expects chunks in this format:

```json
{"agent": "Agent 1", "agent_section": "answer", "v": "<!", "i": ""}$||$
{"v": "DOCTYPE", "i": ""}$||$
{"v": " html", "i": ""}$||$
...
{"done": true}$||$
```

- **Delimiter**: `$||$` separates each chunk
- **v field**: Contains the HTML token fragment
- **i field**: Index/metadata (preserved)
- **agent fields**: Agent metadata (preserved)
- **done signal**: Flushes remaining buffer

## Output Format

Returns chunks in the **same format** with buffered content:

```json
{"agent": "Agent 1", "agent_section": "answer", "v": "<!DOCTYPE html>\n", "i": ""}$||$
{"v": "<html lang=\"en\">\n", "i": ""}$||$
{"v": "<head>\n", "i": ""}$||$
...
{"done": true}$||$
```

## Buffering Rules

### 0. Noise Filtering (NEW!)
Automatically discards:
- **HTML Comments**: Any token starting with `<!--`
- **Whitespace-Only**: Tokens containing only spaces, tabs, newlines

```
Input:  "<!-- BUILDING: styles -->"  "   "  "<style"  ">"
Output: "<style>" (noise tokens removed)
```

### 1. Complete Tags
Buffers from `<` until `>`:
```
Input:  "<!"  "DOCTYPE"  " html"  ">"
Output: "<!DOCTYPE html>"
```

### 2. Style Blocks
Buffers entire `<style>...</style>`:
```
Input:  "<style"  ">"  "body"  " {"  " margin"  ":"  " 0"  ";" " }"  "</style"  ">"
Output: "<style>body { margin: 0; }</style>"
```

### 3. Text Content
Flushes immediately if not starting with `<`:
```
Input:  "<h1>"  "Hello"  "</h1>"
Output: "<h1>"  "Hello"  "</h1>"
```

### 4. Multi-Attribute Tags
Buffers until tag closes:
```
Input:  "<input"  " type"  "=\"text\""  " id"  "=\"user\""  ">"
Output: "<input type=\"text\" id=\"user\">"
```

## Testing

Run the included test suite:

```bash
cd examples/html-ui-mcp
python3 test_chunk_buffer.py
```

**Expected Output:**
```
================================================================================
TEST 1: Basic Tag Buffering
✅ PASSED

TEST 2: Style Block Buffering
✅ PASSED

TEST 3: Text Immediate Flush
✅ PASSED

TEST 4: Multi-Attribute Tags
✅ PASSED

TEST 5: Full Stream Processing
✅ PASSED - Reduced 20 to 8 chunks

🎉 ALL TESTS PASSED!
================================================================================
```

## Real-World Example

**Before (Token-by-Token):**
- 1238 chunks transmitted
- Broken HTML fragments
- UI can't render progressively

**After (Complete Tags):**
- 143 chunks transmitted (89% reduction)
- Complete, valid HTML tags
- Progressive rendering works

## API Reference

### `HTMLChunkBuffer`

Main buffering class:

```python
buffer = HTMLChunkBuffer()

# Process a single chunk
result = buffer.process_chunk({"v": "<!", "i": ""})
if result:
    print(result["v"])  # "<!DOCTYPE html>"

# Flush remaining buffer
final = buffer.flush_final()
```

### `process_stream(input_stream)`

Process entire stream:

```python
for output_chunk in process_stream(input_stream):
    send_to_client(output_chunk)
```

**Parameters:**
- `input_stream`: Iterator of raw chunk strings (with `$||$`)

**Returns:**
- Iterator of buffered chunk strings (with `$||$`)

## Notes

- **Preserves Format**: Same JSON structure, delimiter, and fields
- **Stateful**: Tracks whether in tag, in style block, etc.
- **Pass-Through**: Non-HTML chunks (metadata, done signal) pass unchanged
- **No Validation**: Doesn't validate HTML correctness, only buffers
- **Thread-Safe**: Each `HTMLChunkBuffer` instance is independent

## Files

- `html_chunk_buffer.py` - Main buffering middleware
- `test_chunk_buffer.py` - Test suite
- `CHUNK_BUFFER_README.md` - This file

## License

MIT - Same as FluidMCP project
