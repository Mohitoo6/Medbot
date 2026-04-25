import sys
import pymupdf4llm
try:
    print("Extracting...")
    md_text = pymupdf4llm.to_markdown("Martindale-The-Complete-Drug-Reference_-36th-Edition (1).pdf", pages=[0,1,2])
    print("Success. String length:", len(md_text))
    print("Preview:", md_text[:200])
except Exception as e:
    print("Failed:", e)
