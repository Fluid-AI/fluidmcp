#!/usr/bin/env python3
"""
HTML Chunk Buffering Middleware

Receives streaming chunks in the format:
{"agent": "...", "agent_section": "answer", "v": "<!", "i": ""}$||$
{"v": "DOCTYPE", "i": ""}$||$
{"v": " html", "i": ""}$||$
...

Buffers HTML tokens and emits complete tags and style blocks.
"""

import json
import sys
from typing import Iterator, Optional


class HTMLChunkBuffer:
    """
    Buffers HTML tokens and emits complete tags.
    
    Rules:
    1. Append every "v" value to htmlBuffer
    2. Style block special handling - emit complete <style>...</style> as one chunk
    3. Complete tag flushing - emit from start to ">"
    4. On done, flush remaining buffer
    """
    
    def __init__(self):
        self.htmlBuffer = ""
    
    def process_chunk(self, chunk_data: dict) -> Optional[dict]:
        """
        Process a chunk and return modified chunk or None.
        
        Args:
            chunk_data: Parsed JSON chunk like {"v": "...", "i": ""}
            
        Returns:
            Modified chunk with buffered content, or None if still buffering
        """
        # Pass through chunks without "v" field unchanged
        if "v" not in chunk_data:
            return chunk_data
        
        v_value = chunk_data["v"]
        
        # Empty value, pass through
        if not v_value:
            return chunk_data
        
        # RULE 1: Append every "v" value to htmlBuffer
        self.htmlBuffer += v_value
        
        # RULE 2: Style block special handling (FIRST PRIORITY)
        # Check if we're in a style block
        if "<style" in self.htmlBuffer.lower():
            if "</style>" not in self.htmlBuffer.lower():
                # Still waiting for </style> - don't emit anything
                return None
            else:
                # Have complete style block - emit everything up to and including </style>
                style_end_idx = self.htmlBuffer.lower().find("</style>") + len("</style>")
                chunk = self.htmlBuffer[:style_end_idx]
                self.htmlBuffer = self.htmlBuffer[style_end_idx:]
                return {"v": chunk, "i": chunk_data.get("i", "")}
        
        # RULE 3: Complete tag flushing (runs after RULE 2)
        result = self._flush_complete_tag()
        if result:
            return {"v": result, "i": chunk_data.get("i", "")}
        
        # Still buffering
        return None
    
    def _flush_complete_tag(self) -> Optional[str]:
        """
        RULE 3: Complete tag flushing.
        
        While htmlBuffer contains ">":
          Find first ">"
          Check if there's a "<" before it
          If yes: extract from start to ">" and emit
          If no: emit text node before next "<"
        """
        if ">" not in self.htmlBuffer:
            return None
        
        first_gt = self.htmlBuffer.find(">")
        first_lt = self.htmlBuffer.find("<")
        
        # Check if there's a "<" before the ">"
        if first_lt != -1 and first_lt < first_gt:
            # Extract from start to and including ">"
            chunk = self.htmlBuffer[:first_gt + 1]
            self.htmlBuffer = self.htmlBuffer[first_gt + 1:]
            return chunk
        elif first_lt == -1 or first_lt > first_gt:
            # Text node before next tag
            if first_lt != -1:
                # Emit everything before the "<"
                chunk = self.htmlBuffer[:first_lt]
                self.htmlBuffer = self.htmlBuffer[first_lt:]
                return chunk
            else:
                # No more tags, emit remaining as text
                chunk = self.htmlBuffer
                self.htmlBuffer = ""
                return chunk
        
        return None
    
    def flush_final(self) -> Optional[str]:
        """
        RULE 4: On {"done": true}, flush any remaining buffer content.
        """
        if self.htmlBuffer:
            result = self.htmlBuffer
            self.htmlBuffer = ""
            return result
        return None


def process_stream(input_stream: Iterator[str]) -> Iterator[str]:
    """
    Process streaming chunks with HTML buffering.
    
    Args:
        input_stream: Iterator of raw chunk strings (with $||$ delimiter)
        
    Yields:
        Modified chunk strings with complete HTML tags
    """
    buffer = HTMLChunkBuffer()
    in_answer_section = False
    current_agent = None
    
    for line in input_stream:
        # Split by delimiter
        chunks = line.split("$||$")
        
        for chunk_str in chunks:
            chunk_str = chunk_str.strip()
            if not chunk_str:
                continue
            
            try:
                chunk_data = json.loads(chunk_str)
            except json.JSONDecodeError:
                # Can't parse, pass through unchanged
                yield chunk_str + "$||$"
                continue
            
            # Track agent info
            if "agent" in chunk_data:
                current_agent = chunk_data["agent"]
            
            # Track when we enter answer section
            if chunk_data.get("agent_section") == "answer":
                in_answer_section = True
            
            # Check for done signal
            if chunk_data.get("done"):
                # Flush any remaining buffer
                if in_answer_section:
                    final = buffer.flush_final()
                    if final:
                        output = {"v": final, "i": ""}
                        if current_agent:
                            output["agent"] = current_agent
                        yield json.dumps(output) + "$||$"
                
                # Pass through done signal
                yield json.dumps(chunk_data) + "$||$"
                in_answer_section = False
                continue
            
            # Check if this chunk has "v" field and we're in answer section
            if "v" in chunk_data and in_answer_section:
                # Process through buffer
                result = buffer.process_chunk(chunk_data)
                if result:
                    # Preserve agent info if present
                    output = {}
                    if "agent" in chunk_data:
                        output["agent"] = chunk_data["agent"]
                    if "agent_section" in chunk_data:
                        output["agent_section"] = chunk_data["agent_section"]
                    output["v"] = result["v"]
                    output["i"] = result["i"]
                    
                    yield json.dumps(output) + "$||$"
            else:
                # Not in answer section or no "v" field, pass through
                yield json.dumps(chunk_data) + "$||$"


def main():
    """
    Main entry point for command-line usage.
    
    Usage:
        cat input.txt | python html_chunk_buffer.py
        python html_chunk_buffer.py < input.txt
    """
    
    # Read from stdin
    for line in sys.stdin:
        # Process the line
        for output_chunk in process_stream([line]):
            print(output_chunk, end="", flush=True)


if __name__ == "__main__":
    main()
